#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 tests — mandatory intro flow, semantic validation, retries, flags.

Run: python3 tests/test_speaking_v3_intro.py
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


def _login(base, name="intro-user", password="IntroUserPass123!"):
    _req(base, "POST", "/api/register", {"name": name, "password": password})
    st, obj = _req(base, "POST", "/api/login", {"name": name, "password": password})
    assert st == 200 and obj.get("token"), (st, obj)
    return obj["token"]


def _is_valid_wav(b64_str):
    raw = base64.b64decode(b64_str)
    return len(raw) > 44 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"


def _wav_freq_signature(b64_str):
    """Count zero-crossings to verify examiner vs partner use distinct voices."""
    raw = base64.b64decode(b64_str)
    idx = raw.find(b"data")
    pcm = raw[idx + 8:]
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if (a < 0 <= b) or (a > 0 >= b))
    return crossings


def main():
    base = helpers.isolated_server(extra_env={
        "B2_SPK_TEST_MODE": "1",
        "B2_OWNER_UIDS": "intro-owner",
    })
    tok = _login(base, name="intro-owner", password="IntroOwnerPass123!")

    # Capture spoken texts via voice.synthesize_speech hook (test runs in-process!)
    spoken = []
    orig_synth = voice.synthesize_speech

    def spy_synth(text, role="examiner", partner_voice=None, cacheable=False):
        spoken.append((role, text))
        return orig_synth(text, role=role, partner_voice=partner_voice, cacheable=cacheable)

    voice.synthesize_speech = spy_synth
    try:
        # 1. Valid full intro: greeting -> names -> user valid -> partner -> home -> user valid -> partner -> Part 4
        spoken.clear()
        st, sess = _req(
            base, "POST", "/api/speaking/v3/sessions",
            {"test_id": "01", "part": 4},
            token=tok,
            headers={"X-Test-Hour": "9"},
        )
        assert st == 200, (st, sess)
        sid = sess["session_id"]
        assert sess["speaker"] == "examiner"
        assert _is_valid_wav(sess["audio_b64"])
        assert sess["state"]["phase"] == "intro"
        assert sess["state"]["step"] == "greeting"
        assert sess["ui"]["timer_seconds"] == 0
        assert sess["ui"]["images"] == []
        assert sess["ui"]["card"] is None
        assert len(spoken) == 1
        assert spoken[0][0] == "examiner"
        assert "Good morning." in spoken[0][1]
        assert "My name is Mr Thompson." in spoken[0][1]
        assert "And your names are?" in spoken[0][1]

        # 2. Invalid name ("I like pizza") -> examiner re-prompts with canonical phrase
        spoken.clear()
        st, r_bad = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "I like pizza"},
        )
        assert st == 200, (st, r_bad)
        assert r_bad["accepted"] is False
        assert r_bad["retry"] is True
        assert r_bad["speaker"] == "examiner"
        assert r_bad["state"]["phase"] == "intro"
        assert r_bad["state"]["step"] == "greeting"
        assert spoken[0] == ("examiner", tone.CANONICAL["name_retry"]), spoken

        # 3. Valid name ("My name is Juan") -> partner speaks AFTER user, distinct voice, then examiner asks home
        spoken.clear()
        st, r_name = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "My name is Juan"},
        )
        assert st == 200, (st, r_name)
        assert r_name["accepted"] is True
        assert r_name["retry"] is False
        assert r_name["state"]["phase"] == "intro"
        assert r_name["state"]["step"] == "ask_home"
        assert len(r_name["sequence"]) == 2
        assert r_name["sequence"][0]["speaker"] == "partner"
        assert r_name["sequence"][1]["speaker"] == "examiner"
        assert ("partner", "I'm Alex.") in spoken, spoken
        assert any(r == "examiner" and "Where do you live, Juan?" in txt for r, txt in spoken), spoken
        # Verify distinct audio voices (examiner vs partner)
        f_partner = _wav_freq_signature(r_name["sequence"][0]["audio_b64"])
        f_examiner = _wav_freq_signature(r_name["sequence"][1]["audio_b64"])
        assert f_partner != f_examiner, (f_partner, f_examiner)

        # 4. Invalid home ("I like pizza") -> canonical retry
        spoken.clear()
        st, r_hbad = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "I like pizza"},
        )
        assert st == 200 and r_hbad["accepted"] is False and r_hbad["retry"] is True
        assert spoken[0] == ("examiner", tone.CANONICAL["home_retry"]), spoken

        # 5. Valid home ("I live in Buenos Aires") -> examiner asks partner -> partner answers -> jumps to Part 4!
        spoken.clear()
        st, r_home = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "I live in Buenos Aires"},
        )
        assert st == 200, (st, r_home)
        assert r_home["accepted"] is True
        assert r_home["state"]["phase"] == "part4"
        assert r_home["ui"]["part"] == 4
        assert r_home["ui"]["timer_seconds"] == 240
        assert [c["speaker"] for c in r_home["sequence"]] == ["examiner", "partner", "examiner"]
        assert any(r == "examiner" and "And you, Alex?" in txt for r, txt in spoken), spoken
        assert ("partner", "I live in Bristol.") in spoken, spoken
        assert any(r == "examiner" and "Part 4" in txt for r, txt in spoken), spoken

        # Check report records name_ok=True, home_ok=True (even after 1 retry each)
        st, rep = _req(base, "POST", f"/api/speaking/v3/sessions/{sid}/report", {}, token=tok)
        assert st == 200
        assert rep["flags"]["name_ok"] is True
        assert rep["flags"]["home_ok"] is True

        # 6. Exhaust max 2 retries on name AND home -> advances & records name_ok=False, home_ok=False
        st, s2 = _req(
            base, "POST", "/api/speaking/v3/sessions",
            {"test_id": "02", "part": 1},
            token=tok,
            headers={"X-Test-Hour": "15"},
        )
        assert st == 200
        sid2 = s2["session_id"]
        assert "Good afternoon." in spoken[-1][1]

        for attempt in range(2):
            st, r = _req(
                base, "POST", f"/api/speaking/v3/sessions/{sid2}/turn",
                {"audio_b64": "", "mime": "audio/wav"},
                token=tok,
                headers={"X-Test-Transcript": "I like pizza"},
            )
            assert st == 200 and r["accepted"] is False and r["retry"] is True, (attempt, r)
            assert r["state"]["step"] == "greeting"

        # 3rd invalid attempt -> advances to ask_home with name_ok=False
        st, r3 = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid2}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "I like pizza"},
        )
        assert st == 200 and r3["accepted"] is False and r3["retry"] is False
        assert r3["state"]["step"] == "ask_home"

        for attempt in range(2):
            st, r = _req(
                base, "POST", f"/api/speaking/v3/sessions/{sid2}/turn",
                {"audio_b64": "", "mime": "audio/wav"},
                token=tok,
                headers={"X-Test-Transcript": "I like pizza"},
            )
            assert st == 200 and r["accepted"] is False and r["retry"] is True

        # 3rd invalid home -> advances to Part 1 with home_ok=False
        st, r_h3 = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid2}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": "I like pizza"},
        )
        assert st == 200 and r_h3["accepted"] is False and r_h3["retry"] is False
        assert r_h3["state"]["phase"] == "part1"
        assert r_h3["ui"]["timer_seconds"] == 120

        st, rep2 = _req(base, "POST", f"/api/speaking/v3/sessions/{sid2}/report", {}, token=tok)
        assert st == 200
        assert rep2["flags"]["name_ok"] is False
        assert rep2["flags"]["home_ok"] is False

        # 7. Check evening greeting + various valid name/home formats ("Juan", "I'm Juan", "Juan Perez", "Argentina")
        for idx, (nm, hm) in enumerate([
            ("Juan", "Buenos Aires"),
            ("I'm Juan", "Argentina"),
            ("Juan Perez", "I live in Argentina"),
        ]):
            st, sx = _req(
                base, "POST", "/api/speaking/v3/sessions",
                {"test_id": "03", "part": 1},
                token=tok,
                headers={"X-Test-Hour": "20"},
            )
            assert st == 200
            if idx == 0:
                assert "Good evening." in spoken[-1][1]
            st, rn = _req(
                base, "POST", f"/api/speaking/v3/sessions/{sx['session_id']}/turn",
                {"audio_b64": "", "mime": "audio/wav"},
                token=tok,
                headers={"X-Test-Transcript": nm},
            )
            assert st == 200 and rn["accepted"] is True, (nm, rn)
            st, rh = _req(
                base, "POST", f"/api/speaking/v3/sessions/{sx['session_id']}/turn",
                {"audio_b64": "", "mime": "audio/wav"},
                token=tok,
                headers={"X-Test-Transcript": hm},
            )
            assert st == 200 and rh["accepted"] is True and rh["state"]["phase"] == "part1", (hm, rh)
    finally:
        voice.synthesize_speech = orig_synth

    print("PASS test_speaking_v3_intro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
