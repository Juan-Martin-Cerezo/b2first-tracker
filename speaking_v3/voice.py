#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voice layer for Speaking v3: STT (Gemini), TTS (Gemini + disk cache), ffmpeg.

Rules:
- Examiner and Partner ALWAYS have distinct voices.
- Disk TTS cache (`data/speaking_v3/tts_cache/`) caches ONLY fixed/scripted
  lines (greeting, instructions, transitions, canonical retries) — NEVER user
  audio and NEVER dynamic lines containing user-specific speech.
- Without `B2_SPK_GOOGLE_KEY` (and outside explicit test mode
  `B2_SPK_TEST_MODE=1`), returns `"speech_not_configured"` clearly — never
  simulates audio.
- User audio is never saved to disk.
"""
import base64
import binascii
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request

import store
from speaking_v3 import tone, validation

EXAMINER_VOICE = "Charon"
DEFAULT_PARTNER_VOICE = "Kore"
DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_STT_MODEL = "gemini-2.5-flash"
DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_SAMPLE_RATE = 24000
TTS_CACHE_MAX = 120
AUDIO_MAX_BYTES = 5 * 1024 * 1024

_TTS_LOCK = threading.Lock()


def is_test_mode():
    """True ONLY when explicitly enabled for offline automated tests."""
    return (os.environ.get("B2_SPK_TEST_MODE") or "").strip().lower() in ("1", "true", "yes")


def google_api_key():
    return (os.environ.get("B2_SPK_GOOGLE_KEY") or "").strip()


def gemini_base():
    val = (os.environ.get("B2_SPK_TURN_BASE") or DEFAULT_GEMINI_BASE).strip().rstrip("/")
    return val or DEFAULT_GEMINI_BASE


def stt_model():
    val = (os.environ.get("B2_SPK_TURN_MODEL") or DEFAULT_STT_MODEL).strip()
    return val or DEFAULT_STT_MODEL


def tts_model():
    val = (os.environ.get("B2_SPK_TTS_MODEL") or DEFAULT_TTS_MODEL).strip()
    return val or DEFAULT_TTS_MODEL


def wrap_pcm_as_wav(pcm_bytes, sample_rate=TTS_SAMPLE_RATE):
    """Wrap mono 16-bit PCM bytes in a standard RIFF/WAVE header."""
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm_bytes), b"WAVE", b"fmt ", 16, 1, 1,
        sample_rate, sample_rate * 2, 2, 16, b"data", len(pcm_bytes),
    ) + pcm_bytes


def synthetic_wav(text, voice):
    """Offline test-mode WAV generator (ONLY called when B2_SPK_TEST_MODE=1).

    Produces a tiny valid RIFF/WAVE clip whose tone frequency differs between
    examiner and partner voices, so tests can verify valid audio & distinct
    voices without network access.
    """
    rate = 16000
    dur_s = 0.08
    n_samples = int(rate * dur_s)
    freq = 260.0 if voice == EXAMINER_VOICE else 440.0
    amp = 6000
    samples = [
        int(amp * math.sin(2.0 * math.pi * freq * i / rate))
        for i in range(n_samples)
    ]
    pcm = struct.pack(f"<{n_samples}h", *samples)
    return wrap_pcm_as_wav(pcm, sample_rate=rate)


# ---------------------------------------------------------------------------
# Audio normalisation (ffmpeg in-memory pipe, never writes user audio to disk)
# ---------------------------------------------------------------------------
def normalize_audio(audio_bytes, mime):
    """Normalise candidate audio to 16 kHz mono WAV in memory if ffmpeg exists.

    Returns ``(bytes, mime)``. Never writes audio to disk.
    """
    if not audio_bytes:
        return b"", "audio/wav"
    clean_mime = (mime or "audio/wav").strip().lower().split(";", 1)[0]
    if clean_mime in ("audio/wav", "audio/x-wav", "audio/wave") and audio_bytes[:4] == b"RIFF":
        return audio_bytes, "audio/wav"
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return audio_bytes, clean_mime or "audio/wav"
    try:
        proc = subprocess.run(
            [
                ffmpeg_bin, "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1",
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout and proc.stdout[:4] == b"RIFF":
            return proc.stdout, "audio/wav"
    except (OSError, subprocess.SubprocessError):
        pass
    return audio_bytes, clean_mime or "audio/wav"


def is_wav_silent(audio_bytes):
    """Return True if a RIFF/WAVE buffer is empty or near-silent PCM."""
    if not audio_bytes or len(audio_bytes) < 48:
        return True
    if audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        return False
    idx = audio_bytes.find(b"data")
    if idx < 0 or idx + 8 > len(audio_bytes):
        return True
    size = struct.unpack("<I", audio_bytes[idx + 4:idx + 8])[0]
    pcm = audio_bytes[idx + 8:idx + 8 + size]
    if len(pcm) < 64:
        return True
    step = max(2, (len(pcm) // 2 // 400) * 2)
    peak = 0
    for off in range(0, len(pcm) - 1, step):
        val = abs(struct.unpack("<h", pcm[off:off + 2])[0])
        if val > peak:
            peak = val
    return peak < 40


# ---------------------------------------------------------------------------
# Gemini REST helper
# ---------------------------------------------------------------------------
def _gemini_post(model, payload, api_key, timeout=20, max_bytes=4 * 1024 * 1024):
    url = f"{gemini_base()}/models/{model}:generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes + 1)
    except TimeoutError:
        return None, "upstream_timeout"
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None, "upstream_failed"
    if len(raw) > max_bytes:
        return None, "upstream_failed"
    try:
        obj = json.loads(raw.decode("utf-8"))
        return (obj, None) if isinstance(obj, dict) else (None, "upstream_failed")
    except (ValueError, UnicodeDecodeError):
        return None, "upstream_failed"


def _gemini_text(body):
    try:
        parts = body["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    return "".join(
        p.get("text", "") for p in parts
        if isinstance(p, dict) and isinstance(p.get("text"), str)
    ).strip()


# ---------------------------------------------------------------------------
# TTS Disk Cache (fixed/scripted lines ONLY)
# ---------------------------------------------------------------------------
def _tts_cache_dir():
    return os.path.join(store.data_dir(), "speaking_v3", "tts_cache")


def _tts_cache_path(text, voice):
    digest = hashlib.sha256(f"{voice}\x00{text}".encode("utf-8")).hexdigest()
    return os.path.join(_tts_cache_dir(), f"{digest}.wav")


def _tts_cache_get(text, voice):
    path = _tts_cache_path(text, voice)
    try:
        with open(path, "rb") as fh:
            data = fh.read(4 * 1024 * 1024 + 1)
        if not data or len(data) > 4 * 1024 * 1024:
            return None
        os.utime(path, None)
        return data
    except OSError:
        return None


def _tts_cache_put(text, voice, wav_bytes):
    d = _tts_cache_dir()
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        os.chmod(d, 0o700)
        tmp = os.path.join(d, ".tmp-" + secrets.token_hex(8))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(wav_bytes)
        dst = _tts_cache_path(text, voice)
        os.replace(tmp, dst)
        os.chmod(dst, 0o600)
        entries = [
            (e.stat().st_mtime, e.path)
            for e in os.scandir(d)
            if e.is_file() and e.name.endswith(".wav")
        ]
        if len(entries) > TTS_CACHE_MAX:
            entries.sort()
            for _mt, p in entries[:-TTS_CACHE_MAX]:
                try:
                    os.remove(p)
                except OSError:
                    pass
    except OSError:
        pass


def synthesize_speech(text, role="examiner", partner_voice=None, cacheable=False):
    """Synthesise speech to WAV bytes.

    Returns ``(wav_bytes, error)``.
    - Examiner uses EXAMINER_VOICE; partner uses `partner_voice` (distinct!).
    - In test mode (`B2_SPK_TEST_MODE=1`), returns deterministic synthetic WAV.
    - Without `B2_SPK_GOOGLE_KEY` (outside test mode), returns
      ``(None, "speech_not_configured")`` — never simulates audio!
    """
    if role == "partner":
        voice = partner_voice or DEFAULT_PARTNER_VOICE
        if voice == EXAMINER_VOICE:
            voice = DEFAULT_PARTNER_VOICE
    else:
        voice = EXAMINER_VOICE

    clean_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean_text:
        return None, "empty_tts_text"

    if is_test_mode():
        if cacheable:
            with _TTS_LOCK:
                hit = _tts_cache_get(clean_text, voice)
            if hit is not None:
                return hit, None
            wav = synthetic_wav(clean_text, voice)
            with _TTS_LOCK:
                _tts_cache_put(clean_text, voice, wav)
            return wav, None
        return synthetic_wav(clean_text, voice), None

    api_key = google_api_key()
    if not api_key:
        return None, "speech_not_configured"

    if cacheable:
        with _TTS_LOCK:
            hit = _tts_cache_get(clean_text, voice)
        if hit is not None:
            return hit, None

    payload = {
        "contents": [{"parts": [{"text": clean_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }
    body, err = _gemini_post(tts_model(), payload, api_key, timeout=20)
    if err:
        return None, err
    try:
        parts = body["candidates"][0]["content"]["parts"]
        b64 = next(
            p["inlineData"]["data"]
            for p in parts
            if isinstance(p, dict) and isinstance(p.get("inlineData"), dict)
            and isinstance(p["inlineData"].get("data"), str)
        )
        pcm = base64.b64decode(b64, validate=False)
    except (KeyError, IndexError, StopIteration, TypeError, ValueError, binascii.Error):
        return None, "upstream_failed"
    if not pcm:
        return None, "upstream_failed"

    wav = wrap_pcm_as_wav(pcm, sample_rate=TTS_SAMPLE_RATE)
    if cacheable:
        with _TTS_LOCK:
            _tts_cache_put(clean_text, voice, wav)
    return wav, None


# ---------------------------------------------------------------------------
# STT (in-memory only, never saved to disk)
# ---------------------------------------------------------------------------
def transcribe_audio(audio_b64, mime, test_transcript=None):
    """Transcribe one candidate audio blob strictly in memory.

    Returns ``(transcript, error)``.
    - When `B2_SPK_TEST_MODE=1`, uses `test_transcript` (from X-Test-Transcript)
      if provided, or checks decoded WAV silence.
    - Outside test mode, requires `B2_SPK_GOOGLE_KEY`; if missing, returns
      ``(None, "speech_not_configured")``.
    """
    if is_test_mode() and test_transcript is not None:
        return str(test_transcript).strip()[:2000], None

    if not isinstance(audio_b64, str) or not audio_b64.strip():
        if is_test_mode():
            return "", None
        api_key = google_api_key()
        if not api_key:
            return None, "speech_not_configured"
        return "", None

    try:
        raw_bytes = base64.b64decode(audio_b64, validate=False)
    except (ValueError, binascii.Error):
        return None, "invalid_audio"

    if len(raw_bytes) > AUDIO_MAX_BYTES:
        return None, "audio_too_large"

    if not raw_bytes:
        return "", None

    norm_bytes, norm_mime = normalize_audio(raw_bytes, mime)
    if norm_mime == "audio/wav" and is_wav_silent(norm_bytes):
        return "", None

    if is_test_mode():
        # Non-silent synthetic WAV without X-Test-Transcript -> empty unless header sent
        return "", None

    api_key = google_api_key()
    if not api_key:
        return None, "speech_not_configured"

    norm_b64 = base64.b64encode(norm_bytes).decode("ascii")
    payload = {
        "systemInstruction": {
            "parts": [{
                "text": (
                    "Transcribe the speaker's audio verbatim in the language spoken. "
                    "Do not translate. Do not invent or guess words if the audio is silent "
                    "or unintelligible — return an empty string in that case. "
                    "Return JSON: {\"transcript\": \"...\"}"
                )
            }]
        },
        "contents": [{
            "role": "user",
            "parts": [
                {"inlineData": {"mimeType": norm_mime, "data": norm_b64}},
                {"text": "Transcribe verbatim. Return JSON only."},
            ],
        }],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 400,
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "object",
                "properties": {"transcript": {"type": "string"}},
                "required": ["transcript"],
            },
        },
    }
    body, err = _gemini_post(stt_model(), payload, api_key, timeout=20)
    if err:
        return None, err
    txt = _gemini_text(body)
    try:
        obj = json.loads(txt)
        transcript = str(obj.get("transcript") or "").strip()[:2000]
    except (ValueError, TypeError, AttributeError):
        transcript = ""
    return transcript, None


# ---------------------------------------------------------------------------
# Natural B2 Partner Reply Generator (British English, natural, imperfect B2)
# ---------------------------------------------------------------------------
_PART1_PARTNER_BANK = {
    "How do you like to spend your evenings?": (
        "Well, normally I like to unwind after a busy day — I might cook something simple "
        "and watch a series, or go for a short walk if the weather's decent."
    ),
    "Do you prefer to spend time on your own or with other people?": (
        "Hmm, it depends really. I enjoy seeing my friends at the weekend, "
        "though after a long week I definitely need a quiet evening on my own."
    ),
    "Tell us about a film you really like.": (
        "One film I really enjoyed was Paddington 2 — it sounds a bit silly, "
        "I know, but it's genuinely funny and brilliantly made."
    ),
    "Do you like cooking?": (
        "I do, actually, though I'm not terribly adventurous. I mostly make "
        "pasta dishes and stir-fries during the week."
    ),
    "Do you normally celebrate special occasions with friends or family?": (
        "Usually with my family first, especially for birthdays, and then "
        "I'll often meet up with friends later in the week."
    ),
    "Tell us about a festival or celebration in your country.": (
        "Well, Bonfire Night in November is quite popular in Britain — people "
        "go to fireworks displays and wrap up warm with hot drinks."
    ),
    "What did you do on your last birthday?": (
        "Nothing too extravagant — I went out for dinner with a few close friends "
        "in the city centre, which was lovely."
    ),
    "Are you going to do anything special this weekend?": (
        "I'm thinking of visiting my cousin on Saturday afternoon, and then "
        "catching up on a bit of reading on Sunday."
    ),
    "How much TV do you watch in a week?": (
        "Probably around four or five hours a week. I used to watch more, "
        "but nowadays I'd rather read or listen to a podcast."
    ),
    "Tell us about a TV programme you've seen recently.": (
        "I watched a nature documentary the other night about coastal wildlife, "
        "and the photography was remarkable."
    ),
    "Do you use the internet much?": (
        "Quite a lot, to be honest — mainly for studying and keeping in touch "
        "with family, though I try not to spend too long scrolling."
    ),
    "Do you ever listen to the radio?": (
        "Sometimes in the morning while I'm making breakfast. I quite like "
        "listening to the news and a bit of music."
    ),
    "Who are you most like in your family? Tell us about them.": (
        "I'd say I'm most like my older sister. We're both quite calm, "
        "although she's probably a bit more organised than I am."
    ),
    "Do you have a best friend?": (
        "Yes, I've known my best friend Sam since primary school. "
        "We don't always agree on everything, but we always have a laugh."
    ),
    "Who do you spend time with after school?": (
        "Mostly with a couple of classmates — we sometimes walk into town "
        "or revise together in the library."
    ),
    "Tell us about a good teacher you've had.": (
        "My history teacher last year was brilliant at explaining difficult topics "
        "clearly, and she always encouraged us to ask questions."
    ),
    "What's your favourite subject at school?": (
        "I've always enjoyed geography because it feels relevant to the real world, "
        "even though some of the essays are quite tough."
    ),
    "Do you like reading?": (
        "Yes, especially mystery novels. I don't have as much time as I'd like "
        "during term time, so I mostly read before bed."
    ),
    "Do you enjoy using the internet in your free time?": (
        "I do, mainly for watching videos about music and chatting with friends, "
        "though it's easy to lose track of time."
    ),
    "Tell us about the things you like doing at the weekend.": (
        "At the weekend I usually play football on Saturday morning and then "
        "relax with friends or family on Sunday."
    ),
    "Do you like your school?": (
        "On the whole, yes. The teachers are supportive and there are plenty "
        "of clubs, even if the buildings are a bit old."
    ),
    "Are there any nice places to go in your area?": (
        "There's a lovely park near the river where lots of students go in summer, "
        "and a few nice independent cafes in the town centre."
    ),
    "Have you been anywhere nice recently?": (
        "Last weekend I went to a small coastal town with my family. "
        "It was quite windy, actually, but the views were worth it."
    ),
    "Where would you like to go for your next holiday?": (
        "I'd love to visit Scotland or maybe Italy — somewhere with great scenery "
        "and interesting local food."
    ),
}


def generate_partner_line(kind, test, question_text="", turn_index=0, candidate_summary=""):
    """Produce a natural B2 British-English partner response.

    Uses Gemini when configured (and not in test mode), falling back cleanly
    to curated natural British B2 responses (never Americanisms).
    `candidate_summary` is NEVER persisted — only used in memory if live LLM runs.
    """
    partner_cfg = test.get("partner") or {}
    partner_name = partner_cfg.get("name", "Alex")
    partner_home = partner_cfg.get("home", "Bristol")

    if kind == "intro_name":
        return f"I'm {partner_name}."
    if kind == "intro_home":
        return f"I live in {partner_home}."
    if kind == "part2_monologue":
        return test["parts"]["2"]["task2"].get("partner_monologue") or (
            "Both photographs show quite different situations. In the first picture, "
            "things look fairly calm, whereas the second seems much busier and livelier."
        )

    # Try live LLM for interactive Part 3 / Part 4 / Part 2 followup when key exists
    api_key = google_api_key()
    if api_key and not is_test_mode() and kind in ("part3_discussion", "part3_decision", "part4", "part2_followup"):
        persona = partner_cfg.get("persona") or f"A B2 First candidate from {partner_home}."
        sys_prompt = (
            f"You are {partner_name}, a B2 First speaking candidate. {persona} "
            "Speak natural spoken British English (NEVER American spellings or words like "
            "gotten, mom, math, vacation, soccer, sidewalk, color, organize). "
            "Keep your turn to 1-3 natural sentences (20-45 words). "
            "You may pause briefly ('Well,', 'Hmm,'), politely disagree, or adjust your view, "
            "and in Part 3 ask a short question back to keep the discussion collaborative. "
            "Return JSON: {\"line\": \"...\"}"
        )
        user_msg = (
            f"Exam stage: {kind}\n"
            f"Task/question: {question_text}\n"
            f"Turn index: {turn_index}\n"
            f"Context from partner candidate (react naturally, do not quote verbatim): "
            f"{candidate_summary[:250] if candidate_summary else 'none'}\n"
            "Your spoken reply:"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": sys_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
            "generationConfig": {
                "temperature": 0.6,
                "maxOutputTokens": 120,
                "thinkingConfig": {"thinkingBudget": 0},
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "object",
                    "properties": {"line": {"type": "string"}},
                    "required": ["line"],
                },
            },
        }
        body, err = _gemini_post(stt_model(), payload, api_key, timeout=12)
        if not err:
            try:
                line = str(json.loads(_gemini_text(body)).get("line") or "").strip()
                if line and not tone.check_partner_line(line):
                    return line
            except (ValueError, TypeError, AttributeError):
                pass

    # Deterministic natural British B2 fallback (also used in offline test mode)
    if kind == "part1":
        if question_text in _PART1_PARTNER_BANK:
            return _PART1_PARTNER_BANK[question_text]
        return (
            "Well, I'd say it depends on the week, really. Normally I try to make "
            "a bit of time for friends and hobbies, because it helps me switch off."
        )

    if kind == "part2_followup":
        tid = test.get("id")
        if tid == "01":
            return (
                "To be honest, I don't always find it easy to ask for help at first — "
                "I usually try to sort things out myself, though if it's serious I'll definitely ask a friend."
            )
        if tid == "02":
            return (
                "I quite enjoy flying for longer journeys because it saves so much time, "
                "even though waiting around at airports can be a bit tiring."
            )
        if tid == "03":
            return (
                "I think I'd prefer tennis, actually. Running looks exhausting, "
                "whereas tennis seems a bit more tactical — though playing in front of a huge crowd would make me nervous."
            )
        if tid == "04":
            return (
                "Well, I used to prefer studying on my own, but lately I've realised "
                "working with friends helps because you can test each other and share ideas."
            )
        return (
            "I'd probably prefer the calmer option, because it's easier to concentrate, "
            "though both situations have their own appeal."
        )

    if kind == "part3_discussion":
        opts = test["parts"]["3"].get("options") or ["the first option", "the second option"]
        opt_a = opts[turn_index % len(opts)]
        opt_b = opts[(turn_index + 1) % len(opts)]
        if turn_index == 0:
            return (
                f"Hmm, I see what you mean, though I'm not completely sure about {opt_a}. "
                f"What about {opt_b}? Do you think that would make a bigger difference?"
            )
        if turn_index == 1:
            return (
                f"Actually, you've got a point there — I hadn't thought of it that way. "
                f"On the other hand, {opt_b} might be easier to organise in practice. How do you see it?"
            )
        return (
            f"Fair enough, I partly agree with that. Still, I think {opt_a} is worth considering "
            f"alongside {opt_b} before we rule anything out."
        )

    if kind == "part3_decision":
        opts = test["parts"]["3"].get("options") or ["the first idea", "the second idea"]
        opt_a = opts[0]
        opt_b = opts[-1] if len(opts) > 1 else opts[0]
        if turn_index == 0:
            return (
                f"Well, if we have to choose, I'd lean towards {opt_a} first, "
                f"though I'm torn between that and {opt_b}. Which two would you pick?"
            )
        return (
            f"Yes, I think I've changed my mind slightly — going with your suggestion "
            f"alongside {opt_b} feels like the most sensible choice overall. Shall we agree on those?"
        )

    # Part 4 fallback
    p4_lines = [
        "Well, I partly agree, though I think it really depends on someone's circumstances and how much free time they've got.",
        "Hmm, I'm not entirely convinced about that. On the one hand it sounds appealing, but on the other hand there are practical drawbacks to consider.",
        "Actually, I'd look at it slightly differently — having a good balance usually matters far more than going to extremes.",
        "That's a fair point. In my experience, people enjoy things much more when they're well organised and not overly expensive.",
    ]
    return p4_lines[turn_index % len(p4_lines)]
