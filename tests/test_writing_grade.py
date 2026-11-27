# -*- coding: utf-8 -*-
"""Deterministic unit tests for writing_grade.py (no network, no model calls)."""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import writing_grade as wg  # noqa: E402

out = {}

# 1. text_facts: words ignore fence markers; contractions count as one word.
fenced = (
    "<<<TEXT_a1b2c3d4>>>\n"
    "I don't think people's habits can't change. It's clear that today's youth care.\n\n"
    "However, one must consider government action — therefore laws matter!\n"
    "<<<END_a1b2c3d4>>>"
)
f1 = wg.text_facts(fenced)
assert f1["words"] == 22, f"expected 22 words (contractions as 1, dash & fences ignored), got {f1['words']}"
assert f1["paragraphs"] == 2, f"expected 2 paragraphs, got {f1['paragraphs']}"
assert f1["sentences"] == 3, f"expected 3 sentences, got {f1['sentences']}"
assert f1["contractions"] == ["don't", "can't", "it's"], f"unexpected contractions: {f1['contractions']}"
assert "people's" not in f1["contractions"] and "today's" not in f1["contractions"]
assert "!" in f1["informal_markers"]
assert "however" in f1["formal_markers"]
assert "therefore" in f1["formal_markers"]
assert any("one must" in m for m in f1["formal_markers"]), f1["formal_markers"]
out["1_text_facts_basic"] = {
    "words": f1["words"],
    "paragraphs": f1["paragraphs"],
    "contractions": f1["contractions"],
    "formal": f1["formal_markers"],
}

# 2. text_facts: single paragraph (even with single newlines), informal markers, ALL-CAPS words.
single_para = (
    "Hey guys! You know, I'm gonna say this is REALLY HUGE stuff!\n"
    "We gotta stop ignoring the UK and TV news, don't you think?!"
)
f2 = wg.text_facts(single_para)
assert f2["paragraphs"] == 1, f"single newline should stay 1 paragraph, got {f2['paragraphs']}"
assert f2["all_caps_words"] == 2, f"expected 2 ALL-CAPS words (REALLY, HUGE; not I/UK/TV), got {f2['all_caps_words']}"
assert "hey" in f2["informal_markers"]
assert "you know" in f2["informal_markers"]
assert "gonna" in f2["informal_markers"]
assert "gotta" in f2["informal_markers"]
assert "!" in f2["informal_markers"]
assert len(f2["contractions"]) >= 2
assert f2["formal_markers"] == []
out["2_text_facts_informal_caps"] = {
    "paragraphs": f2["paragraphs"],
    "all_caps_words": f2["all_caps_words"],
    "informal_count": len(f2["informal_markers"]),
    "contractions": f2["contractions"],
}

# 3. Every guard individually.
BASE_BANDS = {"content": 5, "communicative_achievement": 5, "organisation": 5, "language": 5}
NEUTRAL_FACTS = {
    "words": 160,
    "paragraphs": 4,
    "sentences": 10,
    "contractions": [],
    "informal_markers": [],
    "formal_markers": ["however"],
    "all_caps_words": 0,
}

# 3a. content_short_100
b, applied = wg.apply_guards(BASE_BANDS, dict(NEUTRAL_FACTS, words=99), None)
assert b["content"] == 2 and b["language"] == 5 and applied == ["content_short_100"], (b, applied)

# 3b. content_short_120 (100..119)
b, applied = wg.apply_guards(BASE_BANDS, dict(NEUTRAL_FACTS, words=100), None)
assert b["content"] == 3 and applied == ["content_short_120"], (b, applied)
b, applied = wg.apply_guards(BASE_BANDS, dict(NEUTRAL_FACTS, words=119), None)
assert b["content"] == 3 and applied == ["content_short_120"], (b, applied)
b, applied = wg.apply_guards(BASE_BANDS, dict(NEUTRAL_FACTS, words=120), None)
assert b["content"] == 5 and applied == [], (b, applied)

# 3c. content_points_missing_1 (1 absent -> cap 2; 1 partial -> cap 3)
audit_m1_absent = {
    "task_points": [
        {"point": "habits", "status": "present", "quote": "recycle"},
        {"point": "laws", "status": "absent", "quote": ""},
        {"point": "own idea", "status": "present", "quote": "schools"},
    ],
    "off_topic": False,
}
b, applied = wg.apply_guards(BASE_BANDS, NEUTRAL_FACTS, audit_m1_absent)
assert b["content"] == 2 and applied == ["content_points_missing_1"], (b, applied)
assert b["language"] == 5 and b["organisation"] == 5 and b["communicative_achievement"] == 5

audit_m1_partial = {
    "task_points": [
        {"point": "habits", "status": "present", "quote": "recycle"},
        {"point": "laws", "status": "partial", "quote": "some rules"},
        {"point": "own idea", "status": "present", "quote": "schools"},
    ],
    "off_topic": False,
}
b, applied = wg.apply_guards(BASE_BANDS, NEUTRAL_FACTS, audit_m1_partial)
assert b["content"] == 3 and applied == ["content_points_missing_1"], (b, applied)
assert b["language"] == 5 and b["organisation"] == 5 and b["communicative_achievement"] == 5

# 3d. content_points_missing_2
audit_m2 = {
    "task_points": [
        {"point": "habits", "status": "present", "quote": "recycle"},
        {"point": "laws", "status": "absent", "quote": ""},
        {"point": "own idea", "status": "absent", "quote": ""},
    ],
    "off_topic": False,
}
b, applied = wg.apply_guards(BASE_BANDS, NEUTRAL_FACTS, audit_m2)
assert b["content"] == 2 and applied == ["content_points_missing_2"], (b, applied)

# 3e. content_points_all_absent (all absent and off_topic)
audit_all = {
    "task_points": [
        {"point": "habits", "status": "absent", "quote": ""},
        {"point": "laws", "status": "absent", "quote": ""},
        {"point": "own idea", "status": "absent", "quote": ""},
    ],
    "off_topic": False,
}
b, applied = wg.apply_guards(BASE_BANDS, NEUTRAL_FACTS, audit_all)
assert b["content"] == 1 and applied == ["content_points_all_absent"], (b, applied)

audit_off = {"task_points": [], "off_topic": True}
b, applied = wg.apply_guards(BASE_BANDS, NEUTRAL_FACTS, audit_off)
assert b["content"] == 1 and applied == ["content_points_all_absent"], (b, applied)
assert b["language"] == 5 and b["organisation"] == 5

# 3f. organisation_no_paragraphs (and NEVER clamps language)
b, applied = wg.apply_guards(BASE_BANDS, dict(NEUTRAL_FACTS, paragraphs=1), None)
assert b["organisation"] == 2 and b["language"] == 5 and applied == ["organisation_no_paragraphs"], (b, applied)

# 3g. ca_informal_sustained + email exemption
inf_facts = dict(
    NEUTRAL_FACTS,
    contractions=["don't", "it's"],
    informal_markers=["hey", "gonna", "!"],
    formal_markers=[],
)
b, applied = wg.apply_guards(BASE_BANDS, inf_facts, None, kind="Essay")
assert b["communicative_achievement"] == 2 and applied == ["ca_informal_sustained"], (b, applied)
assert b["content"] == 5 and b["organisation"] == 5 and b["language"] == 5

# Email exemption: informal email must NOT trigger ca_informal_sustained.
b_email, applied_email = wg.apply_guards(BASE_BANDS, inf_facts, None, kind="Email")
assert b_email["communicative_achievement"] == 5 and applied_email == [], (b_email, applied_email)
b_email2, applied_email2 = wg.apply_guards(BASE_BANDS, inf_facts, None, kind="email")
assert b_email2["communicative_achievement"] == 5 and applied_email2 == [], (b_email2, applied_email2)

# Presence of formal marker prevents ca_informal_sustained.
b_mixed, applied_mixed = wg.apply_guards(
    BASE_BANDS, dict(inf_facts, formal_markers=["however"]), None, kind="Essay"
)
assert b_mixed["communicative_achievement"] == 5 and applied_mixed == [], (b_mixed, applied_mixed)

# 3h. language_basic_errors (and NEVER clamps organisation)
audit_basic = {
    "grammar_errors": [
        {"quote": "the peoples thinks", "type": "subject_verb", "severity": "basic"},
        {"quote": "can't to change", "type": "modal_infinitive", "severity": "basic"},
        {"quote": "is big problem", "type": "article", "severity": "basic"},
        {"quote": "yesterday I see", "type": "tense", "severity": "basic"},
        {"quote": "for help nature", "type": "preposition", "severity": "basic"},
    ]
}
b, applied = wg.apply_guards(BASE_BANDS, NEUTRAL_FACTS, audit_basic)
assert b["language"] == 2 and b["organisation"] == 5 and applied == ["language_basic_errors"], (b, applied)

# Duplicate quotes do NOT count twice toward the 5-error threshold.
audit_dups = {
    "grammar_errors": [
        {"quote": "the peoples thinks", "type": "subject_verb", "severity": "basic"},
        {"quote": "the peoples thinks", "type": "subject_verb", "severity": "basic"},
        {"quote": "can't to change", "type": "modal_infinitive", "severity": "basic"},
        {"quote": "is big problem", "type": "article", "severity": "basic"},
        {"quote": "yesterday I see", "type": "tense", "severity": "basic"},
    ]
}
b, applied = wg.apply_guards(BASE_BANDS, NEUTRAL_FACTS, audit_dups)
assert b["language"] == 5 and applied == [], (b, applied)

# 5 errors with NO core basic type (only preposition/word_form/other) do not trigger language_basic_errors.
audit_nonbasic = {
    "grammar_errors": [
        {"quote": f"phrase {i}", "type": "preposition", "severity": "minor"}
        for i in range(6)
    ]
}
b, applied = wg.apply_guards(BASE_BANDS, NEUTRAL_FACTS, audit_nonbasic)
assert b["language"] == 5 and applied == [], (b, applied)

# 3i. length_over_250
b, applied = wg.apply_guards(BASE_BANDS, dict(NEUTRAL_FACTS, words=251), None)
assert b["content"] == 4 and b["communicative_achievement"] == 4 and applied == ["length_over_250"], (b, applied)
assert b["organisation"] == 5 and b["language"] == 5

out["3_all_guards"] = True

# 4. Monotonicity: guards ONLY lower, NEVER raise, and never mutate caller dict.
low_bands = {"content": 0, "communicative_achievement": 1, "organisation": 1, "language": 1}
low_copy = dict(low_bands)
extreme_facts = dict(
    words=50,
    paragraphs=1,
    sentences=3,
    contractions=["don't", "can't"],
    informal_markers=["hey", "gonna", "gotta", "!"],
    formal_markers=[],
    all_caps_words=3,
)
b_low, app_low = wg.apply_guards(low_bands, extreme_facts, audit_basic, kind="Essay")
assert low_bands == low_copy, "apply_guards mutated caller bands dict"
for k in low_bands:
    assert b_low[k] == low_bands[k], f"guard changed already-low {k}: {low_bands[k]} -> {b_low[k]}"
assert "content_short_100" in app_low and "organisation_no_paragraphs" in app_low, app_low

for start in range(6):
    inp = {k: start for k in ("content", "communicative_achievement", "organisation", "language")}
    res, _ = wg.apply_guards(inp, extreme_facts, audit_all, kind="Essay")
    for k in inp:
        assert res[k] <= inp[k], f"guard raised {k} from {inp[k]} to {res[k]}"
out["4_guards_only_lower"] = True

# 5. Collapse detection.
assert wg.COLLAPSE_KEYS == ("content", "communicative_achievement", "organisation")
assert wg.is_collapsed({"content": 3, "communicative_achievement": 3, "organisation": 3, "language": 5}) is True
assert wg.is_collapsed({"content": 3, "communicative_achievement": 4, "organisation": 3, "language": 3}) is False
assert wg.is_collapsed({"content": 2, "communicative_achievement": 2, "organisation": 2, "language": 2}) is True
out["5_collapse_detection"] = True

print(json.dumps(out, ensure_ascii=False, indent=1))
