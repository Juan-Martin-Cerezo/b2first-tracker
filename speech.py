#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Azure Pronunciation Assessment helpers (S2). Pure, stdlib, no network.

`server.py` owns the HTTP call; everything here is testable without a key:
  pa_config_header()  -> the base64 Pronunciation-Assessment header
  validate_audio()    -> container signature + duration (< 10 s)
  parse_pa_response() -> the normalised contract the frontend consumes

The Pronunciation band of the B2 First speaking scale may only come from a
phoneme-level measurement (docs/SPEAKING-REALTIME-PLAN.md §3). If this module
cannot score a turn, the caller must report the band as "not measured".
"""
import base64
import json
import struct

PA_TIMEOUT = 8
PA_MAX_SECONDS = 10.0
PA_MAX_WORDS = 5               # words returned in `worst`
PA_OGG_SAMPLE_RATE = 48000     # opus always decodes at 48 kHz


def pa_config_header(ref_text=""):
    """Base64 Pronunciation-Assessment config for the request header.

    Phoneme granularity and prosody are what make the score honest; the
    hundred-mark scale keeps the numbers comparable to Cambridge bands.
    """
    text = ref_text if isinstance(ref_text, str) else ""
    config = {
        "ReferenceText": text,
        "GradingSystem": "HundredMark",
        "Granularity": "Phoneme",
        "EnableMiscue": True,
        "EnableProsodyAssessment": True,
        "Dimension": "Comprehensive",
    }
    raw = json.dumps(config, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _wav_info(buf):
    """(byte_rate, data_bytes) from a RIFF/WAVE buffer, or None if unparseable."""
    if len(buf) < 44 or buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
        return None
    off = 12
    byte_rate = 0
    data_bytes = None
    while off + 8 <= len(buf):
        cid = buf[off:off + 4]
        size = struct.unpack("<I", buf[off + 4:off + 8])[0]
        body = off + 8
        if body + size > len(buf):
            size = max(0, len(buf) - body)
        if cid == b"fmt " and size >= 16 and body + 16 <= len(buf):
            _afmt, _ch, rate, brate, _align, _bits = struct.unpack("<HHIIHH", buf[body:body + 16])
            byte_rate = brate or rate * max(1, _ch)
        elif cid == b"data":
            data_bytes = size
            break
        off = body + size + (size % 2)
    if data_bytes is None or byte_rate <= 0:
        return None
    return byte_rate, data_bytes


def _ogg_duration(buf):
    """Duration in seconds from the granule position of the last Ogg page."""
    idx = buf.rfind(b"OggS")
    if idx < 0 or idx + 14 > len(buf):
        return None
    granule = struct.unpack("<q", buf[idx + 6:idx + 14])[0]
    if granule <= 0:
        return None
    return granule / float(PA_OGG_SAMPLE_RATE)


def audio_duration_s(buf, fmt):
    """Length of the buffer in seconds, or None when it cannot be measured."""
    fmt = (fmt or "").strip().lower()
    if fmt == "wav":
        info = _wav_info(buf)
        if not info:
            return None
        byte_rate, data_bytes = info
        return data_bytes / float(byte_rate)
    if fmt == "ogg":
        return _ogg_duration(buf)
    return None


def validate_audio(buf, fmt):
    """(ok, reason) — the real container signature decides, never `fmt` alone."""
    if not isinstance(buf, (bytes, bytearray)) or not buf:
        return False, "empty"
    fmt = (fmt or "").strip().lower()
    if fmt not in ("wav", "ogg"):
        return False, "unsupported_format"
    if fmt == "wav":
        if len(buf) < 44 or buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
            return False, "container_mismatch"
        if _wav_info(buf) is None:
            return False, "bad_header"
    else:
        if len(buf) < 27 or buf[0:4] != b"OggS":
            return False, "container_mismatch"
    duration = audio_duration_s(buf, fmt)
    if duration is None:
        return False, "unknown_duration"
    if duration > PA_MAX_SECONDS:
        return False, "too_long"
    if duration <= 0:
        return False, "empty"
    return True, "ok"


def _num(value):
    """Round a score to one decimal; whole values stay ints (100, not 100.0)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    number = round(number, 1)
    return int(number) if number.is_integer() else number


def _phonemes(word):
    out = []
    for ph in word.get("Phonemes") or []:
        if not isinstance(ph, dict):
            continue
        name = ph.get("Phoneme")
        if not isinstance(name, str) or not name:
            continue
        pa = ph.get("PronunciationAssessment") or {}
        out.append({"p": name, "score": _num(pa.get("AccuracyScore"))})
    return out


def parse_pa_response(azure_json):
    """Normalise Azure's detailed recognition response into the API contract.

    Contract (do not rename): ok, accuracy, fluency, completeness, prosody,
    words[{w,err,score,phonemes[{p,score}]}], worst[], duration_s, provider.
    """
    if not isinstance(azure_json, dict):
        return {"ok": False, "error": "invalid_response", "provider": "azure"}
    status = azure_json.get("RecognitionStatus")
    if status not in (None, "", "Success"):
        silent = status in ("NoMatch", "InitialSilenceTimeout", "BabbleTimeout")
        return {"ok": False, "error": "no_speech" if silent else "recognition_failed",
                "provider": "azure"}
    candidates = azure_json.get("NBest")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        return {"ok": False, "error": "no_speech", "provider": "azure"}
    best = candidates[0]
    overall = best.get("PronunciationAssessment") or {}

    words = []
    for item in best.get("Words") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("Word")
        if not isinstance(name, str) or not name:
            continue
        pa = item.get("PronunciationAssessment") or {}
        err = pa.get("ErrorType")
        words.append({
            "w": name,
            "err": err if isinstance(err, str) and err else "None",
            "score": _num(pa.get("AccuracyScore")),
            "phonemes": _phonemes(item),
        })

    ranked = [w for w in words
              if w["score"] is not None and w["err"] != "Omission"]
    ranked.sort(key=lambda w: w["score"])
    worst = [{"w": w["w"], "score": w["score"], "phonemes": w["phonemes"]}
             for w in ranked[:PA_MAX_WORDS]]

    ticks = azure_json.get("Duration")
    if ticks is None:
        ticks = best.get("Duration")
    try:
        duration_s = round(float(ticks) / 1e7, 1) if ticks is not None else None
    except (TypeError, ValueError):
        duration_s = None

    return {
        "ok": True,
        "accuracy": _num(overall.get("AccuracyScore")),
        "fluency": _num(overall.get("FluencyScore")),
        "completeness": _num(overall.get("CompletenessScore")),
        "prosody": _num(overall.get("ProsodyScore")),
        "words": words,
        "worst": worst,
        "duration_s": duration_s,
        "provider": "azure",
    }
