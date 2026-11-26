#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 tests — formal British Cambridge examiner tone & language linter.

Walks EVERY examiner line in all 4 scripts, all canonical phrases, all retry
responses, and all partner lines (partner exempt from formal register, NOT
from British English spelling/vocabulary rules).

Run: python3 tests/test_speaking_v3_tone.py
"""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

import helpers  # noqa: E402
from speaking_v3 import catalog, engine, tone, voice  # noqa: E402


def _assert_examiner_clean(label, text):
    issues = tone.check_examiner_line(text)
    assert not issues, f"Examiner tone violation in [{label}]: {issues} -> {text!r}"


def _assert_partner_clean(label, text):
    issues = tone.check_partner_line(text)
    assert not issues, f"Partner language violation in [{label}]: {issues} -> {text!r}"


def main():
    # 0. Sanity-check that the linter itself catches every forbidden expression from the spec
    must_reject_examiner = [
        "Sorry, I didn't catch your name.",
        "I didn't quite catch that.",
        "Could you please repeat the question?",
        "Pardon?",
        "Sorry?",
        "What?",
        "Okay, let's begin.",
        "OK, next question.",
        "Hi there!",
        "Hey, welcome.",
        "Yeah, that's fine.",
        "We're gonna move on.",
        "Do you wanna start?",
        "Talk about that stuff.",
        "Thank you, guys.",
        "I have gotten the photos.",
        "Talk about your mom.",
        "Do you like math?",
        "Tell me about your vacation.",
        "In the fall we visit parks.",
        "Walk on the sidewalk.",
        "Do you play soccer?",
        "Meet at the train station.",
        "What is your favorite color?",
        "How do you organize your time?",
        "Excellent! Next question.",
        "Well done!",
        "No problem.",
        "Alright?",
        "Let's go.",
        "Ready?",
        "Thank you!!",
        "Thank you 😊",
    ]
    for bad in must_reject_examiner:
        assert tone.check_examiner_line(bad), f"Linter FAILED to reject forbidden examiner line: {bad!r}"

    # Verify legitimate Cambridge British lines PASS
    must_accept_examiner = [
        "All right?",
        "Good morning. My name is Mr Thompson. And your names are?",
        "I beg your pardon. I didn't quite hear your name. Would you mind repeating it?",
        "I beg your pardon. I didn't quite hear where you live. Would you mind repeating that?",
        "I'm terribly sorry. I didn't quite hear that. Would you mind saying it again?",
        "I'm afraid I didn't quite follow. Would you mind explaining that again?",
        "I'm afraid that wasn't quite what I asked. Would you mind answering the question about cooking?",
        "I'm afraid I didn't quite follow that. Would you mind repeating it in English?",
        "Take your time. Do let me know when you're ready.",
        "Thank you very much. That brings us to the end of this part.",
        "Thank you. We'll now move on to Part 2.",
    ]
    for good in must_accept_examiner:
        _assert_examiner_clean("must_accept", good)

    # 1. Verify exact canonical retry & transition phrases
    assert tone.CANONICAL["name_retry"] == (
        "I beg your pardon. I didn't quite hear your name. Would you mind repeating it?"
    )
    assert tone.CANONICAL["home_retry"] == (
        "I beg your pardon. I didn't quite hear where you live. Would you mind repeating that?"
    )
    assert tone.CANONICAL["general_unheard"] == (
        "I'm terribly sorry. I didn't quite hear that. Would you mind saying it again?"
    )
    assert tone.CANONICAL["didnt_follow"] == (
        "I'm afraid I didn't quite follow. Would you mind explaining that again?"
    )
    assert tone.CANONICAL["non_english"] == (
        "I'm afraid I didn't quite follow that. Would you mind repeating it in English?"
    )
    assert tone.CANONICAL["silence"] == (
        "Take your time. Do let me know when you're ready."
    )
    assert tone.CANONICAL["part_end"] == (
        "Thank you very much. That brings us to the end of this part."
    )
    assert tone.part_transition(2) == "Thank you. We'll now move on to Part 2."

    for key, val in tone.CANONICAL.items():
        rendered = val.format(topic="cooking", part=2, candidate="Juan", partner="Alex")
        _assert_examiner_clean(f"CANONICAL.{key}", rendered)

    for hr in (8, 14, 20):
        _assert_examiner_clean(f"greeting_{hr}", tone.opening_greeting(hour=hr))

    # 2. Walk EVERY examiner line and EVERY partner line in all 4 exam JSON scripts
    tests = catalog.load_all_tests(force_reload=True)
    assert sorted(tests.keys()) == ["01", "02", "03", "04"]

    for tid, doc in sorted(tests.items()):
        p1 = doc["parts"]["1"]
        _assert_examiner_clean(f"{tid}.p1.opening", p1["opening"])
        for cat in p1["categories"]:
            for q in cat["questions"]:
                _assert_examiner_clean(f"{tid}.p1.q", q["text"])
                for fu in q.get("followups") or []:
                    _assert_examiner_clean(f"{tid}.p1.fu", fu)
                _assert_examiner_clean(f"{tid}.p1.offtopic", tone.off_topic_prompt(q["topic"]))

        p2 = doc["parts"]["2"]
        _assert_examiner_clean(f"{tid}.p2.opening", p2["opening"])
        for tk in ("task1", "task2"):
            t = p2[tk]
            for field in ("intro", "prompt", "check", "compare_followup", "followup_to_partner", "followup_to_user"):
                if field in t:
                    rendered = t[field].format(candidate="Juan", partner=doc["partner"]["name"])
                    _assert_examiner_clean(f"{tid}.p2.{tk}.{field}", rendered)
            if "partner_monologue" in t:
                _assert_partner_clean(f"{tid}.p2.{tk}.partner_monologue", t["partner_monologue"])

        p3 = doc["parts"]["3"]
        for field in ("opening", "start_discussion", "decision_prompt", "closing"):
            _assert_examiner_clean(f"{tid}.p3.{field}", p3[field])
        _assert_examiner_clean(f"{tid}.p3.offtopic", tone.off_topic_prompt(p3["topic"]))

        p4 = doc["parts"]["4"]
        _assert_examiner_clean(f"{tid}.p4.closing", p4["closing"])
        for pr in p4["prompts"]:
            _assert_examiner_clean(f"{tid}.p4.prompt", pr)
        for q in p4["questions"]:
            _assert_examiner_clean(f"{tid}.p4.q", q["text"])
            for fu in q.get("followups") or []:
                _assert_examiner_clean(f"{tid}.p4.fu", fu)
            _assert_examiner_clean(f"{tid}.p4.offtopic", tone.off_topic_prompt(q["topic"]))

        # Check all generated partner lines for this test
        for kind in (
            "intro_name", "intro_home", "part2_monologue", "part2_followup",
            "part3_open", "part3_meta_go_ahead", "part3_discussion",
            "part3_decision_open", "part3_decision", "part4_answer", "part4_react", "part4",
        ):
            for idx in range(6):
                line = voice.generate_partner_line(kind, doc, turn_index=idx)
                _assert_partner_clean(f"{tid}.partner.{kind}.{idx}", line)

    # Check entire Part 1 and Part 4 partner banks
    for q_text, ans in voice._PART1_PARTNER_BANK.items():
        _assert_partner_clean(f"partner_bank_p1.{q_text}", ans)
    for q_text, ans in voice._PART4_PARTNER_BANK.items():
        _assert_partner_clean(f"partner_bank_p4.{q_text}", ans)

    # 3. Live in-process engine sweep across all 4 tests: capture EVERY spoken clip
    helpers.isolated_data_dir(prefix="b2tone-")
    os.environ["B2_SPK_TEST_MODE"] = "1"
    import store
    store.DATA_DIR = os.environ["B2_DATA_DIR"]

    captured = []
    orig_synth = voice.synthesize_speech

    def capture_synth(text, role="examiner", partner_voice=None, cacheable=False):
        captured.append((role, text))
        return orig_synth(text, role=role, partner_voice=partner_voice, cacheable=cacheable)

    voice.synthesize_speech = capture_synth
    try:
        for tid in ("01", "02", "03", "04"):
            res, code, err = engine.create_session("tone-u", test_id=tid, part=0, hour=10)
            assert code == 200 and not err
            sid = res["session_id"]
            # Exercise retries (silence, Spanish, off-topic name/home)
            engine.handle_turn("tone-u", sid, test_transcript="")
            engine.handle_turn("tone-u", sid, test_transcript="Hola, me llamo Juan")
            engine.handle_turn("tone-u", sid, test_transcript="I like pizza")
            engine.handle_turn("tone-u", sid, test_transcript="My name is Juan")
            engine.handle_turn("tone-u", sid, test_transcript="I like pizza")
            engine.handle_turn("tone-u", sid, test_transcript="I live in Buenos Aires")
            # Exercise Part 1 off-topic + valid + skip
            engine.handle_turn("tone-u", sid, test_transcript="I like pizza")
            engine.handle_skip("tone-u", sid)
            engine.handle_skip("tone-u", sid)
            engine.handle_skip("tone-u", sid)
            # Part 2 non-comparison + skip through rest
            engine.handle_turn("tone-u", sid, test_transcript="There is a person outdoors.")
            for _ in range(15):
                r, c, e = engine.handle_skip("tone-u", sid)
                if e or (r and r.get("done")):
                    break
    finally:
        voice.synthesize_speech = orig_synth

    examiner_count = 0
    partner_count = 0
    for role, line in captured:
        if role == "examiner":
            examiner_count += 1
            _assert_examiner_clean(f"live_examiner_{examiner_count}", line)
        else:
            partner_count += 1
            _assert_partner_clean(f"live_partner_{partner_count}", line)

    assert examiner_count >= 40 and partner_count >= 8, (examiner_count, partner_count)
    print(f"PASS test_speaking_v3_tone (checked {examiner_count} live examiner lines, {partner_count} live partner lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
