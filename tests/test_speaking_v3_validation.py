#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 tests — off-topic, Spanish, silence, max retries, partner order.

Run: python3 tests/test_speaking_v3_validation.py
"""
import base64
import json
import os
import struct
import sys
import urllib.error
import urllib.request

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

import helpers  # noqa: E402
from speaking_v3 import tone, voice  # noqa: E402


def _req(base, method, path, payload=None, token=None, headers=None):
    hdrs = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8")
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else {}


def _login(base, name="val-owner", password="ValOwnerPass123!"):
    _req(base, "POST", "/api/register", {"name": name, "password": password})
    st, obj = _req(base, "POST", "/api/login", {"name": name, "password": password})
    assert st == 200 and obj.get("token"), (st, obj)
    return obj["token"]


def _silent_wav_b64():
    pcm = b"\x00\x00" * 1600
    wav = voice.wrap_pcm_as_wav(pcm, sample_rate=16000)
    return base64.b64encode(wav).decode("ascii")


def main():
    base = helpers.isolated_server(extra_env={
        "B2_SPK_TEST_MODE": "1",
        "B2_OWNER_UIDS": "val-owner",
    })
    tok = _login(base)

    spoken = []
    orig_synth = voice.synthesize_speech

    def spy_synth(text, role="examiner", partner_voice=None, cacheable=False):
        spoken.append((role, text))
        return orig_synth(text, role=role, partner_voice=partner_voice, cacheable=cacheable)

    voice.synthesize_speech = spy_synth
    try:
        # Start Part 1 on test 01
        st, sess = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "01", "part": 1}, token=tok)
        assert st == 200
        sid = sess["session_id"]

        # 1. Silence during intro -> canonical silence prompt, does NOT burn retries
        spoken.clear()
        st, r_sil = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": _silent_wav_b64(), "mime": "audio/wav"},
            token=tok,
        )
        assert st == 200
        assert r_sil["accepted"] is False
        assert r_sil["retry"] is True
        assert r_sil["reason"] == "silence"
        assert r_sil["state"]["retries"] == 0
        assert spoken == [("examiner", tone.CANONICAL["silence"])], spoken

        # 2. Spanish during intro -> canonical non_english prompt
        spoken.clear()
        st, r_es = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "Hola, me llamo Juan"},
        )
        assert st == 200
        assert r_es["accepted"] is False and r_es["retry"] is True
        assert r_es["reason"] == "non_english"
        assert spoken == [("examiner", tone.CANONICAL["non_english"])], spoken

        # Complete intro validly -> verify partner speaks AFTER user
        spoken.clear()
        st, r_n = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "Juan"},
        )
        assert st == 200 and r_n["accepted"] is True
        assert r_n["sequence"][0]["speaker"] == "partner"

        st, r_h = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "Buenos Aires"},
        )
        assert st == 200 and r_h["accepted"] is True and r_h["state"]["phase"] == "part1"

        # 3. Part 1: silence -> canonical silence, no retry burned
        spoken.clear()
        st, r_p1_sil = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": _silent_wav_b64(), "mime": "audio/wav"},
            token=tok,
        )
        assert st == 200 and r_p1_sil["accepted"] is False and r_p1_sil["retry"] is True
        assert r_p1_sil["reason"] == "silence"
        assert spoken == [("examiner", tone.CANONICAL["silence"])]

        # 4. Part 1: Spanish -> canonical non_english
        spoken.clear()
        st, r_p1_es = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "No entiendo la pregunta, prefiero hablar en español"},
        )
        assert st == 200 and r_p1_es["accepted"] is False and r_p1_es["retry"] is True
        assert r_p1_es["reason"] == "non_english"
        assert spoken == [("examiner", tone.CANONICAL["non_english"])]

        # 5. Part 1: off-topic -> canonical off_topic prompt (retry #2 of 2)
        spoken.clear()
        st, r_p1_ot = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "I like pizza"},
        )
        assert st == 200 and r_p1_ot["accepted"] is False and r_p1_ot["retry"] is True
        assert r_p1_ot["reason"] == "off_topic"
        assert "I'm afraid that wasn't quite what I asked." in spoken[0][1]

        # 6. 3rd invalid attempt on same question -> max retries exceeded, advances & partner answers after user
        spoken.clear()
        st, r_p1_adv = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "Bananas are yellow"},
        )
        assert st == 200 and r_p1_adv["accepted"] is False and r_p1_adv["retry"] is False
        assert r_p1_adv["state"]["question_index"] == 1
        assert any(c["speaker"] == "partner" for c in r_p1_adv["sequence"])

        # 7. Valid answer on q_1 -> accepted, partner responds after user
        st, r_ok = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "I normally celebrate special occasions with my family and close friends."},
        )
        assert st == 200 and r_ok["accepted"] is True
        assert any(c["speaker"] == "partner" for c in r_ok["sequence"])

        # Verify flags recorded in report
        st, rep = _req(base, "POST", f"/api/speaking/v3/sessions/{sid}/report", {}, token=tok)
        assert st == 200
        assert rep["flags"]["silence_turns"] >= 2
        assert rep["flags"]["non_english_turns"] >= 2
        assert rep["flags"]["off_topic_turns"] >= 2
    finally:
        voice.synthesize_speech = orig_synth

    print("PASS test_speaking_v3_validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
