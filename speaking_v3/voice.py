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
PARTNER_VOICE_BY_SEX = {"male": "Puck", "female": "Aoede"}
DEFAULT_PARTNER_VOICE = PARTNER_VOICE_BY_SEX["male"]
DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_STT_MODEL = "gemini-2.5-flash"
DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_SAMPLE_RATE = 24000
TTS_CACHE_MAX = 400
AUDIO_MAX_BYTES = 5 * 1024 * 1024

_TTS_LOCK = threading.Lock()


def partner_voice_for(sex, explicit=None):
    """Partner voice that matches the partner's sex; explicit wins."""
    return explicit or PARTNER_VOICE_BY_SEX.get((sex or "").lower(), DEFAULT_PARTNER_VOICE)


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


_PART4_PARTNER_BANK = {
    # Test 01: Holidays and tourism
    "Do you think you have to spend a lot of money to have a good holiday?": (
        "No, not really. Some of my favourite trips have been quite cheap — camping with friends "
        "or visiting a nearby coastal town. What matters most is who you're with and getting a proper break."
    ),
    "Some people say we travel too much these days and shouldn't go on so many holidays. What do you think?": (
        "Well, I can see why people worry about the environmental impact of frequent flights. "
        "At the same time, travelling opens your mind, so perhaps taking fewer but longer trips is a sensible compromise."
    ),
    "Do you think people have enough time for holidays these days?": (
        "Probably not, to be honest. Many jobs are quite demanding and people struggle to switch off "
        "even when they're away, so having slightly longer breaks would do everyone a lot of good."
    ),
    "Why do you think people like to go away on holiday?": (
        "Mainly to escape their everyday routine, I'd say. Seeing unfamiliar places, trying different food "
        "and simply not worrying about work or studying helps people come back feeling refreshed."
    ),
    "What do you think is the biggest advantage of living in a place where there are a lot of tourists?": (
        "The main advantage is probably the boost to the local economy — shops, cafes and transport stay lively, "
        "and you get to meet people from all sorts of backgrounds."
    ),
    "What can people do to have a good holiday in your country?": (
        "There's quite a lot of variety, really. You can explore historic cities and museums, "
        "or head out to the countryside and national parks for walking and fresh air."
    ),
    # Test 02: Keeping fit and healthy
    "What is the advantage of keeping fit with friends?": (
        "I think the biggest advantage is motivation. When you've arranged to meet a friend for a run or a class, "
        "you're far less likely to cancel just because you feel tired."
    ),
    "Some people say it is a waste of time going to a gym because you can exercise outside for free. What do you think?": (
        "Well, exercising outdoors is great when the weather's decent, though in winter it's dark and rainy. "
        "A gym also gives you proper equipment and structured classes, so it's not a waste for everyone."
    ),
    "Is it possible to live healthily without spending a lot of money?": (
        "Yes, definitely. Cooking simple meals with seasonal vegetables is usually cheaper than takeaways, "
        "and walking, cycling or stretching at home costs nothing at all."
    ),
    "Do you think the government should spend more money on sports and leisure facilities?": (
        "I think so, yes. Investing in public parks, swimming pools and local sports centres encourages "
        "people to stay active, which probably saves healthcare costs in the long run."
    ),
    "Some people say it's a school's responsibility to help students keep fit. Do you agree?": (
        "I partly agree — schools should definitely provide good sports lessons and clubs, "
        "though families also play a huge role in building healthy habits at home."
    ),
    "Do you think advertising makes people worry too much about keeping fit and how they look?": (
        "Yes, quite often. Social media and adverts tend to show unrealistic body types, "
        "which can put unnecessary pressure on young people instead of focusing on genuine health."
    ),
    # Test 03: After-school activities and trying new things
    "Do you think classes like these would be popular with students?": (
        "I think they would, especially if they feel relaxed and practical rather than like extra homework. "
        "Learning something creative with friends after school is a nice way to unwind."
    ),
    "How important do you think it is for people to try new activities?": (
        "Quite important, really. Trying unfamiliar things builds confidence and helps you discover "
        "talents you didn't know you had, rather than sticking to the same routine."
    ),
    "Why do you think some people don't like to try new things?": (
        "Mainly because they're afraid of making mistakes or looking silly in front of others. "
        "It's much more comfortable to stay with what you already know you're good at."
    ),
    "A lot of people enjoy doing sport after school. Do you think this is a good thing?": (
        "Definitely, yes. After sitting in classrooms all day, doing sport helps students burn off energy, "
        "reduce stress and learn how to work together as a team."
    ),
    "What do students enjoy doing after school in your country?": (
        "Quite a mix — lots of teenagers play football or go to music and drama clubs, "
        "while others prefer hanging out in local cafes or gaming with friends."
    ),
    "Do you think it's better to go out and do things after school or is it better to stay at home?": (
        "I'd say a balance is best. Going out keeps you active and social, "
        "but everyone needs a couple of quiet afternoons at home to rest and catch up on schoolwork."
    ),
    # Test 04: School trips and travel
    "Do you think school trips should take place on a school day or at the weekend?": (
        "On a school day, I'd say. Most students and teachers need their weekends to rest and see family, "
        "and a trip during the week feels like part of your actual education."
    ),
    "If you go on a school trip, is it better to visit a city, or go to the countryside?": (
        "It depends on the subject, really. Cities are brilliant for museums, theatre and history, "
        "whereas the countryside is ideal for geography, wildlife and outdoor team activities."
    ),
    "What can students do in class after going on a school trip?": (
        "They could work in small groups to prepare a short presentation or display with their photographs, "
        "which helps everyone remember what they actually learnt on the trip."
    ),
    "What's a good place for students to visit in your country?": (
        "I'd recommend somewhere like Bath or York — they're easy to walk around, packed with history "
        "and have plenty of engaging museums for school groups."
    ),
    "What's the most interesting thing about visiting other countries?": (
        "For me it's experiencing everyday life in a different culture — hearing another language, "
        "trying local dishes and noticing small differences in how people live."
    ),
    "If you could go anywhere in the world, where would you go?": (
        "I'd love to visit Japan one day. The blend of ancient temples, modern cities and amazing food "
        "seems completely different from anything I've experienced in Europe."
    ),
}


def generate_partner_line(kind, test, question_text="", turn_index=0, candidate_summary="",
                          focus_option="", next_option="", covered_options=None):
    """Produce a natural B2 British-English partner response.

    Uses Gemini when configured (and not in test mode), falling back cleanly
    to curated natural British B2 responses (never Americanisms).
    `candidate_summary` is NEVER persisted — only used in memory if live LLM runs.
    """
    partner_cfg = test.get("partner") or {}
    partner_name = partner_cfg.get("name", "Alex")
    partner_home = partner_cfg.get("home", "Bristol")
    p3_opts = test.get("parts", {}).get("3", {}).get("options") or ["the first idea", "the second idea"]

    if kind == "intro_name":
        return f"I'm {partner_name}."
    if kind == "intro_home":
        return f"I live in {partner_home}."
    if kind == "part3_meta_go_ahead":
        return "Yes, go ahead."
    if kind == "part3_open":
        opt0 = focus_option or p3_opts[0]
        return f"Shall we start with {opt0}? What do you think about that one?"
    if kind == "part3_decision_open":
        opt0 = focus_option or p3_opts[0]
        return (
            f"Well, if we have to narrow it down, I'd probably lean towards {opt0} "
            f"because it seems quite practical. What do you think?"
        )
    if kind == "part2_monologue":
        return test["parts"]["2"]["task2"].get("partner_monologue") or (
            "Both photographs show quite different situations. In the first picture, "
            "things look fairly calm, whereas the second seems much busier and livelier."
        )

    # Curated Part 2 follow-up for built-in tests avoids a redundant LLM call
    if kind == "part2_followup" and test.get("id") in ("01", "02", "03", "04"):
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
        return (
            "Well, I used to prefer studying on my own, but lately I've realised "
            "working with friends helps because you can test each other and share ideas."
        )

    # Curated Part 4 own answer when partner goes first (no candidate summary yet)
    if kind == "part4_answer" and not candidate_summary and question_text in _PART4_PARTNER_BANK:
        return _PART4_PARTNER_BANK[question_text]

    # Try live LLM for interactive turns when API key exists (outside test mode)
    api_key = google_api_key()
    llm_kinds = ("part3_discussion", "part3_decision", "part4_answer", "part4_react", "part4", "part2_followup")
    if api_key and not is_test_mode() and kind in llm_kinds:
        persona = partner_cfg.get("persona") or f"A B2 First candidate from {partner_home}."
        extra_guidance = ""
        if kind == "part3_discussion":
            extra_guidance = (
                f"React directly to your partner's view on '{focus_option or p3_opts[0]}' "
                f"(partially agree or politely disagree with a brief reason), then move the conversation "
                f"on to a DIFFERENT card idea: '{next_option or p3_opts[-1]}' and ask for their view. "
                f"Do not repeat already covered ideas unnecessarily ({', '.join(covered_options or [])})."
            )
        elif kind == "part3_decision":
            extra_guidance = (
                f"Negotiate genuinely towards a decision. You may propose '{next_option or focus_option or p3_opts[0]}', "
                "push back gently, compromise, or politely maintain your view (agreement is not mandatory)."
            )
        elif kind == "part4_answer":
            extra_guidance = (
                "Give YOUR OWN clear, reasoned opinion answering the examiner's question directly. "
                "Do not merely say 'I agree' with the other candidate."
            )
        elif kind in ("part4_react", "part4"):
            extra_guidance = (
                "React naturally to the other candidate's answer — agree, partly disagree, or add a fresh angle "
                "related to the examiner's question."
            )

        sys_prompt = (
            f"You are {partner_name}, a B2 First speaking candidate. {persona} "
            "Speak natural spoken British English (NEVER American spellings or words like "
            "gotten, mom, math, vacation, soccer, sidewalk, color, organize, favorite, center). "
            "Keep your turn to 1-3 natural sentences (20-45 words). "
            f"{extra_guidance} "
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
        return (
            "I'd probably prefer the calmer option, because it's easier to concentrate, "
            "though both situations have their own appeal."
        )

    if kind == "part3_discussion":
        opt_cur = focus_option or p3_opts[turn_index % len(p3_opts)]
        opt_nxt = next_option or p3_opts[(turn_index + 1) % len(p3_opts)]
        if opt_nxt == opt_cur and len(p3_opts) > 1:
            opt_nxt = p3_opts[(p3_opts.index(opt_cur) + 1) % len(p3_opts)] if opt_cur in p3_opts else p3_opts[-1]
        templates = [
            f"Hmm, I see your point about {opt_cur}, though it might not appeal to everyone. Shall we move on to {opt_nxt}? What do you think?",
            f"That's a fair point, actually — I hadn't looked at {opt_cur} that way. What about {opt_nxt}? Could that make a bigger difference?",
            f"I partly agree with you there, although {opt_cur} could have practical drawbacks. On the other hand, how do you feel about {opt_nxt}?",
            f"True, I can see why {opt_cur} would be attractive. Still, {opt_nxt} is worth considering too — would you say that's easier to organise?",
            f"Yes, that makes sense, though I'm slightly sceptical about how well {opt_cur} would work long term. Do you think {opt_nxt} might be stronger?",
            f"Good point — both have clear pros and cons. Looking at {opt_nxt}, I'd say it's quite appealing as well, wouldn't you?",
        ]
        return templates[turn_index % len(templates)]

    if kind == "part3_decision":
        opt_cur = focus_option or p3_opts[0]
        opt_alt = next_option or (p3_opts[-1] if len(p3_opts) > 1 else opt_cur)
        if opt_alt == opt_cur and len(p3_opts) > 1:
            opt_alt = p3_opts[1]
        if turn_index == 0:
            return (
                f"Hmm, I see why you'd pick that, though I'm still quite keen on {opt_alt} as well. "
                f"Do you think {opt_cur} would work better alongside it?"
            )
        if turn_index == 1:
            return (
                f"Fair enough, you've almost convinced me — I suppose {opt_cur} is a sensible choice overall, "
                f"even if I still have a soft spot for {opt_alt}. Shall we settle on that?"
            )
        return (
            f"All right then, I think we've weighed up the main points well — "
            f"even if we don't agree on every detail, {opt_cur} feels like a realistic choice."
        )

    if kind == "part4_answer":
        if question_text in _PART4_PARTNER_BANK:
            return _PART4_PARTNER_BANK[question_text]
        own_fallbacks = [
            "Personally, I think it really depends on someone's circumstances — having a sensible balance usually works much better than going to extremes.",
            "In my view, there are clear benefits, though people often overlook the practical costs and the amount of time involved.",
            "I'd say it's mostly positive, especially for younger people, provided it's well organised and doesn't put too much pressure on anyone.",
            "Well, on the whole I'm quite optimistic about it, because shared experiences tend to be far more memorable in the long run.",
        ]
        return own_fallbacks[turn_index % len(own_fallbacks)]

    # Part 4 reaction fallback ("part4_react" or legacy "part4")
    p4_react_lines = [
        "Well, I partly agree with that, though I think it really depends on someone's circumstances and how much free time they've got.",
        "Hmm, I'm not entirely convinced about that. On the one hand it sounds appealing, but on the other hand there are practical drawbacks to consider.",
        "Actually, I'd look at it slightly differently — having a good balance usually matters far more than going to extremes.",
        "That's a fair point. In my experience, people enjoy things much more when they're well organised and not overly expensive.",
    ]
    return p4_react_lines[turn_index % len(p4_react_lines)]
