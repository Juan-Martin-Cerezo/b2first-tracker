#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 tests — single part vs full exam 1->2->3->4, timings, images, quotas.

Run: python3 tests/test_speaking_v3_parts.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

import helpers  # noqa: E402
from speaking_v3 import engine, voice  # noqa: E402


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


def _get_bytes(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def _login(base, name, password):
    _req(base, "POST", "/api/register", {"name": name, "password": password})
    st, obj = _req(base, "POST", "/api/login", {"name": name, "password": password})
    assert st == 200 and obj.get("token"), (st, obj)
    return obj["token"]


def _turn(base, sid, tok, text, extra=None):
    body = {"audio_b64": "", "mime": "audio/wav"}
    if extra:
        body.update(extra)
    st, obj = _req(
        base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
        body, token=tok, headers={"X-Test-Transcript": text},
    )
    assert st == 200, (st, obj)
    return obj


def _complete_intro(base, sid, tok):
    r1 = _turn(base, sid, tok, "My name is Juan")
    assert r1["accepted"] is True and r1["state"]["step"] == "ask_home"
    r2 = _turn(base, sid, tok, "I live in Buenos Aires")
    assert r2["accepted"] is True
    return r2


def main():
    base = helpers.isolated_server(extra_env={
        "B2_SPK_TEST_MODE": "1",
        "B2_OWNER_UIDS": "parts-owner",
    })
    owner_tok = _login(base, "parts-owner", "PartsOwnerPass123!")
    reg_tok = _login(base, "parts-regular", "PartsRegularPass123!")

    # 1. Single Part 2: jumps straight to Part 2 after intro, shows exact test 02 images, finishes after Part 2
    st, s = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "02", "part": 2}, token=owner_tok)
    assert st == 200
    sid = s["session_id"]
    assert s["ui"]["timer_seconds"] == 0 and s["ui"]["images"] == []

    r_p2 = _complete_intro(base, sid, owner_tok)
    assert r_p2["state"]["phase"] == "part2"
    assert r_p2["state"]["step"] == "user_long_turn"
    assert r_p2["ui"]["part"] == 2
    assert r_p2["ui"]["timer_seconds"] == 240
    assert r_p2["ui"]["turn_seconds"] == 60
    assert r_p2["ui"]["images"] == [
        "/assets/speaking/exams/02/p2-1a.jpg",
        "/assets/speaking/exams/02/p2-1b.jpg",
    ]

    # Verify Part 2 images are actually served via HTTP and are clean JPEGs without examiner script text
    for img_url in r_p2["ui"]["images"]:
        ist, ctype, raw = _get_bytes(base, img_url)
        assert ist == 200 and "jpeg" in ctype.lower() and raw[:3] == b"\xff\xd8\xff"
        assert b"Interlocutor" not in raw and b"Candidate A" not in raw

    # Part 2 long turn WITHOUT comparison -> examiner asks compare_followup!
    r_nocomp = _turn(base, sid, owner_tok, "I see people sitting on a bus looking at their phones.")
    assert r_nocomp["accepted"] is True
    assert r_nocomp["state"]["step"] == "user_compare_followup"
    assert r_nocomp["done"] is False

    # Answer compare_followup -> partner sequence runs -> examiner asks user Task 2 follow-up with Task 2 photos
    r_after = _turn(base, sid, owner_tok, "Travelling by plane takes much more planning because of airports.")
    assert r_after["state"]["step"] == "user_followup"
    assert r_after["ui"]["images"] == [
        "/assets/speaking/exams/02/p2-2a.jpg",
        "/assets/speaking/exams/02/p2-2b.jpg",
    ]
    assert r_after["ui"]["turn_seconds"] == 30
    speakers = [c["speaker"] for c in r_after["sequence"]]
    assert "partner" in speakers and "examiner" in speakers

    # Answer Task 2 follow-up -> single Part 2 ends!
    r_done = _turn(base, sid, owner_tok, "Yes, I sometimes visit art galleries and museums because I enjoy paintings and history.")
    assert r_done["done"] is True
    assert r_done["state"]["phase"] == "finished"

    st, rep_p2 = _req(base, "POST", f"/api/speaking/v3/sessions/{sid}/report", {}, token=owner_tok)
    assert st == 200 and rep_p2["flags"]["part2_compared"] is False

    # 2. Full exam (part=0): traverses 1 -> 2 -> 3 -> 4 continuously with correct timings & assets
    st, sf = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "01", "part": 0}, token=owner_tok)
    assert st == 200
    fsid = sf["session_id"]

    # Intro -> Part 1
    r = _complete_intro(base, fsid, owner_tok)
    assert r["state"]["phase"] == "part1"
    assert r["ui"]["part"] == 1 and r["ui"]["timer_seconds"] == 120

    # Part 1: 3 user turns -> automatically transitions to Part 2
    r = _turn(base, fsid, owner_tok, "In the evenings I usually relax at home, cook dinner and read a book.")
    assert r["state"]["phase"] == "part1" and r["accepted"] is True
    r = _turn(base, fsid, owner_tok, "I normally celebrate special occasions with my family and close friends at home.")
    assert r["state"]["phase"] == "part1" and r["accepted"] is True
    r = _turn(base, fsid, owner_tok, "I watch about four hours of television a week, mostly news programmes and series.")
    assert r["state"]["phase"] == "part2", r["state"]
    assert r["ui"]["part"] == 2 and r["ui"]["timer_seconds"] == 240
    assert r["ui"]["images"] == [
        "/assets/speaking/exams/01/p2-1a.jpg",
        "/assets/speaking/exams/01/p2-1b.jpg",
    ]

    # Part 2: long turn WITH comparison -> advances straight to user_followup
    r = _turn(
        base, fsid, owner_tok,
        "Both photographs show people helping others, whereas the first picture shows an injured football player on a pitch and the second shows a police officer giving directions with a map.",
    )
    assert r["state"]["phase"] == "part2" and r["state"]["step"] == "user_followup"
    assert r["ui"]["images"] == [
        "/assets/speaking/exams/01/p2-2a.jpg",
        "/assets/speaking/exams/01/p2-2b.jpg",
    ]

    # Part 2 follow-up -> transitions to Part 3 (15s prep + card)
    r = _turn(base, fsid, owner_tok, "I would prefer the quiet private garden because I enjoy peaceful nature and looking after plants.")
    assert r["state"]["phase"] == "part3"
    assert r["state"]["step"] == "prep"
    assert r["ui"]["part"] == 3
    assert r["ui"]["timer_seconds"] == 240
    assert r["ui"]["subtimer_seconds"] == 15
    assert r["ui"]["card"] == "/assets/speaking/exams/01/p3-card.png"

    # Verify Part 3 card served cleanly
    cst, ctype, craw = _get_bytes(base, r["ui"]["card"])
    assert cst == 200 and "png" in ctype.lower() and craw[:8] == b"\x89PNG\r\n\x1a\n"

    # Part 3: prep_done -> examiner start_discussion + partner opening line -> 120s discussion
    spoken_log = []
    orig_synth = voice.synthesize_speech

    def spy_synth(text, role="examiner", partner_voice=None, cacheable=False):
        spoken_log.append((role, text))
        return orig_synth(text, role=role, partner_voice=partner_voice, cacheable=cacheable)

    voice.synthesize_speech = spy_synth
    try:
        spoken_log.clear()
        st, r = _req(
            base, "POST", f"/api/speaking/v3/sessions/{fsid}/turn",
            {"action": "prep_done"}, token=owner_tok,
        )
        assert st == 200 and r["state"]["step"] == "discussion_0"
        assert r["ui"]["subtimer_seconds"] == 120
        assert [c["speaker"] for c in r["sequence"]] == ["examiner", "partner"], r["sequence"]
        partner_open_lines = [txt for role, txt in spoken_log if role == "partner"]
        assert partner_open_lines and "shall we start with" in partner_open_lines[0].lower(), partner_open_lines

        # Part 3 meta-turn: "Can I start?" -> partner says "Yes, go ahead.", does NOT count as content turn!
        spoken_log.clear()
        r_meta = _turn(base, fsid, owner_tok, "Can I start?")
        assert r_meta["accepted"] is True and r_meta.get("meta_turn") is True
        assert r_meta["state"]["step"] == "discussion_0" and r_meta["state"]["question_index"] == 0
        assert [c["speaker"] for c in r_meta["sequence"]] == ["partner"]
        assert spoken_log == [("partner", "Yes, go ahead.")], spoken_log

        # Part 3 discussion: 5 user turns (including short cooperative turns!), partner covers distinct ideas,
        # NO examiner interruptions between turns, and does NOT end at 3 turns!
        disc_turns = [
            "I think building a nightclub would mainly attract young tourists in the summer.",
            "I agree",
            "That's true",
            "I'm not sure, maybe providing parks is better for families.",
            "Having more shops could also keep visitors busy when it rains.",
        ]
        partner_disc_lines = []
        for idx, msg in enumerate(disc_turns):
            spoken_log.clear()
            r = _turn(base, fsid, owner_tok, msg)
            assert r["accepted"] is True, (idx, msg, r)
            if idx < 4:
                assert r["state"]["phase"] == "part3" and r["state"]["step"] == f"discussion_{idx + 1}", (idx, r["state"])
                # Strictly candidate-to-candidate: NO examiner clips during discussion!
                assert [c["speaker"] for c in r["sequence"]] == ["partner"], (idx, r["sequence"])
                p_txt = [txt for role, txt in spoken_log if role == "partner"][0]
                partner_disc_lines.append(p_txt)
            else:
                # 5th turn transitions to decision_0: examiner decision_prompt + partner opens negotiation
                assert r["state"]["phase"] == "part3" and r["state"]["step"] == "decision_0", r["state"]
                assert r["ui"]["subtimer_seconds"] == 60
                assert [c["speaker"] for c in r["sequence"]] == ["examiner", "partner"], r["sequence"]

        # Partner covered multiple distinct card options and never repeated the exact same line
        assert len(set(partner_disc_lines)) == len(partner_disc_lines) == 4, partner_disc_lines
        assert r["state"].get("covered_count", 0) >= 4, r["state"]

        # Part 3 decision: 3 user turns of negotiation -> transitions to Part 4
        r = _turn(base, fsid, owner_tok, "I'm not sure about a nightclub, I think providing parks is better for everyone.")
        assert r["state"]["phase"] == "part3" and r["state"]["step"] == "decision_1"
        assert [c["speaker"] for c in r["sequence"]] == ["partner"]

        r = _turn(base, fsid, owner_tok, "True, holiday flats are useful too, though parks attract families all year.")
        assert r["state"]["phase"] == "part3" and r["state"]["step"] == "decision_2"
        assert [c["speaker"] for c in r["sequence"]] == ["partner"]

        r = _turn(base, fsid, owner_tok, "I still prefer parks, even if we don't completely agree.")
        assert r["state"]["phase"] == "part4" and r["state"]["step"] == "q_0_user", r["state"]
        assert r["ui"]["part"] == 4 and r["ui"]["timer_seconds"] == 240
        assert r["ui"]["card"] is None and r["ui"]["images"] == []

        # Part 4: alternating odd/even rounds with partner's own opinion + user reaction!
        # Round 0 (odd: user first) -> user answers -> examiner asks partner -> partner gives own opinion -> examiner asks user to react
        spoken_log.clear()
        r = _turn(base, fsid, owner_tok, "No, you do not have to spend a lot of money to enjoy a good holiday with friends or family.")
        assert r["accepted"] is True and r["state"]["phase"] == "part4" and r["state"]["step"] == "q_0_react", r["state"]
        assert [c["speaker"] for c in r["sequence"]] == ["examiner", "partner", "examiner"]
        p4_r0_partner = [txt for role, txt in spoken_log if role == "partner"][0]
        assert "cheap" in p4_r0_partner.lower() or "camping" in p4_r0_partner.lower() or "holiday" in p4_r0_partner.lower(), p4_r0_partner
        assert any(role == "examiner" and "agree with alex" in txt.lower() for role, txt in spoken_log), spoken_log

        # Round 0 reaction by user -> advances to Round 1 (even: partner goes FIRST!)
        spoken_log.clear()
        r = _turn(base, fsid, owner_tok, "Yes, I agree with Alex, spending time with friends matters more than expensive hotels.")
        assert r["accepted"] is True and r["state"]["phase"] == "part4" and r["state"]["step"] == "q_1_user", r["state"]
        assert [c["speaker"] for c in r["sequence"]] == ["examiner", "partner", "examiner"]
        p4_r1_partner = [txt for role, txt in spoken_log if role == "partner"][0]
        assert "flight" in p4_r1_partner.lower() or "travel" in p4_r1_partner.lower(), p4_r1_partner

        # Round 1 user answers -> examiner asks partner "do you agree?" -> partner reacts -> Round 2 (odd: user first)
        spoken_log.clear()
        r = _turn(base, fsid, owner_tok, "I partly agree that people travel too much, especially because frequent flights can harm the environment.")
        assert r["accepted"] is True and r["state"]["phase"] == "part4" and r["state"]["step"] == "q_2_user", r["state"]
        assert [c["speaker"] for c in r["sequence"]] == ["examiner", "partner", "examiner"]

        # Round 2 (odd: user first) -> answer -> partner opinion -> user reacts -> Round 3 (even: partner first)
        r = _turn(base, fsid, owner_tok, "Many workers do not have enough time for holidays because their jobs are busy and stressful.")
        assert r["accepted"] is True and r["state"]["step"] == "q_2_react"
        r = _turn(base, fsid, owner_tok, "That's true, longer breaks would definitely help people relax.")
        assert r["accepted"] is True and r["state"]["step"] == "q_3_user"
        assert [c["speaker"] for c in r["sequence"]] == ["examiner", "partner", "examiner"]

        # Round 3 (even: partner went first) -> user answers -> partner reacts -> finished!
        r = _turn(base, fsid, owner_tok, "People like going away on holiday to escape their routine, relax and explore new places and cultures.")
        assert r["accepted"] is True and r["state"]["phase"] == "finished" and r["done"] is True
    finally:
        voice.synthesize_speech = orig_synth

    st, rep_full = _req(base, "POST", f"/api/speaking/v3/sessions/{fsid}/report", {}, token=owner_tok)
    assert st == 200 and rep_full["flags"]["part2_compared"] is True
    for k in ("grammar_vocabulary", "discourse", "interactive"):
        assert 0.0 <= rep_full["bands"][k] <= 5.0

    # 2b. Verify Part 3 time-based cutoff (~110s discussion -> elapsed_part_seconds=125) transitions to decision
    st, st3 = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "02", "part": 3}, token=owner_tok)
    assert st == 200
    s3id = st3["session_id"]
    _complete_intro(base, s3id, owner_tok)
    st, _ = _req(base, "POST", f"/api/speaking/v3/sessions/{s3id}/turn", {"action": "prep_done"}, token=owner_tok)
    assert st == 200
    r_time_dec = _turn(
        base, s3id, owner_tok,
        "Sleeping eight hours every night is essential for energy and concentration.",
        extra={"elapsed_part_seconds": 126},
    )
    assert r_time_dec["state"]["phase"] == "part3" and r_time_dec["state"]["step"] == "decision_0", r_time_dec["state"]

    # 2c. Measure & verify parallel TTS latency speedup vs sequential while preserving clip order
    orig_synth2 = voice.synthesize_speech
    sim_delay = 0.12

    def slow_synth(text, role="examiner", partner_voice=None, cacheable=False):
        time.sleep(sim_delay)
        return orig_synth2(text, role=role, partner_voice=partner_voice, cacheable=False)

    voice.synthesize_speech = slow_synth
    try:
        test_clips = [
            {"speaker": "examiner", "text": f"Examiner clip {i}", "step": f"s{i}", "ui": None, "cacheable": False}
            for i in range(4)
        ]
        t_seq0 = time.monotonic()
        for c in test_clips:
            voice.synthesize_speech(c["text"], role=c["speaker"], partner_voice="Kore", cacheable=False)
        seq_ms = (time.monotonic() - t_seq0) * 1000.0

        t_par0 = time.monotonic()
        par_out, par_err = engine._synth_sequence(test_clips, "Kore")
        par_ms = (time.monotonic() - t_par0) * 1000.0
        assert not par_err and len(par_out) == 4
        assert [c["step"] for c in par_out] == ["s0", "s1", "s2", "s3"], "Parallel TTS broke clip order!"
        assert par_ms < seq_ms * 0.55, f"Parallel TTS not faster enough: par={par_ms:.1f}ms vs seq={seq_ms:.1f}ms"
        print(f"LATENCY 4-clip TTS: sequential={seq_ms:.1f}ms -> parallel={par_ms:.1f}ms ({seq_ms/par_ms:.2f}x speedup)")
    finally:
        voice.synthesize_speech = orig_synth2

    # 3. Skip & Delete endpoints
    st, ss = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "03", "part": 1}, token=owner_tok)
    assert st == 200
    st, sk = _req(base, "POST", f"/api/speaking/v3/sessions/{ss['session_id']}/skip", {}, token=owner_tok)
    assert st == 200 and sk["skipped"] is True and sk["state"]["step"] == "ask_home"
    st, dl = _req(base, "DELETE", f"/api/speaking/v3/sessions/{ss['session_id']}", token=owner_tok)
    assert st == 200 and dl["deleted"] is True
    st, dl2 = _req(base, "DELETE", f"/api/speaking/v3/sessions/{ss['session_id']}", token=owner_tok)
    assert st == 404

    # 4. Daily quota: regular user gets 3 mocks/day (single part = 1, full = 1), 4th returns 429
    for idx, part_choice in enumerate((1, 2, 0)):
        st, q = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "04", "part": part_choice}, token=reg_tok)
        assert st == 200, (idx, st, q)
    st, q4 = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "04", "part": 3}, token=reg_tok)
    assert st == 429 and q4.get("error") == "limit_reached" and q4.get("limit") == "speaking", (st, q4)

    # Owner is NOT capped by the 3/day mock limit
    st, ow = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "04", "part": 4}, token=owner_tok)
    assert st == 200, (st, ow)

    print("PASS test_speaking_v3_parts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
