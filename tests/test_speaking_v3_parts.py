#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 tests — single part vs full exam 1->2->3->4, timings, images, quotas.

Run: python3 tests/test_speaking_v3_parts.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

import helpers  # noqa: E402


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

    # Part 3: prep_done -> 120s discussion
    st, r = _req(
        base, "POST", f"/api/speaking/v3/sessions/{fsid}/turn",
        {"action": "prep_done"}, token=owner_tok,
    )
    assert st == 200 and r["state"]["step"] == "discussion_0"
    assert r["ui"]["subtimer_seconds"] == 120

    # Part 3: 3 discussion turns -> 60s decision
    for msg in [
        "Providing parks would attract families and tourists who want green spaces in the town.",
        "Building holiday flats makes it easier for visitors to stay longer, although shops are also important.",
        "Security cameras might make tourists feel safe, whereas a large nightclub mainly appeals to young people.",
    ]:
        r = _turn(base, fsid, owner_tok, msg)
        assert r["accepted"] is True

    assert r["state"]["phase"] == "part3" and r["state"]["step"] == "decision_0"
    assert r["ui"]["subtimer_seconds"] == 60

    # Part 3: 2 decision turns -> transitions to Part 4
    r = _turn(base, fsid, owner_tok, "I think providing parks and having more shops are the best ideas for tourists.")
    assert r["state"]["phase"] == "part3" and r["state"]["step"] == "decision_1"
    r = _turn(base, fsid, owner_tok, "Yes, I agree, parks and holiday flats together would attract the widest range of visitors.")
    assert r["state"]["phase"] == "part4"
    assert r["ui"]["part"] == 4 and r["ui"]["timer_seconds"] == 240
    assert r["ui"]["card"] is None and r["ui"]["images"] == []

    # Part 4: 4 discussion questions -> finished!
    p4_answers = [
        "No, you do not have to spend a lot of money to enjoy a good holiday with friends or family.",
        "I partly agree that people travel too much, especially because frequent flights can harm the environment.",
        "Many workers do not have enough time for holidays because their jobs are busy and stressful.",
        "People like going away on holiday to escape their routine, relax and explore new places and cultures.",
    ]
    for idx, ans in enumerate(p4_answers):
        r = _turn(base, fsid, owner_tok, ans)
        assert r["accepted"] is True
        if idx < 3:
            assert r["state"]["phase"] == "part4" and r["done"] is False
        else:
            assert r["state"]["phase"] == "finished" and r["done"] is True

    st, rep_full = _req(base, "POST", f"/api/speaking/v3/sessions/{fsid}/report", {}, token=owner_tok)
    assert st == 200 and rep_full["flags"]["part2_compared"] is True
    for k in ("grammar_vocabulary", "discourse", "interactive"):
        assert 0.0 <= rep_full["bands"][k] <= 5.0

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
