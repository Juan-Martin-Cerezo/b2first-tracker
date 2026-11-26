#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Formal British Cambridge examiner tone rules, canonical phrases, and linter.

The examiner (Mr Thompson) ALWAYS speaks formal, measured British English.
The partner is a B2 candidate (natural, may hesitate or disagree) — exempt
from formal register, but still bound by British English vocabulary/spelling.
"""
import datetime
import re
import time

# ---------------------------------------------------------------------------
# Canonical examiner phrases (used verbatim across the engine and tests)
# ---------------------------------------------------------------------------
EXAMINER_NAME = "Mr Thompson"

CANONICAL = {
    "name_retry": (
        "I beg your pardon. I didn't quite hear your name. "
        "Would you mind repeating it?"
    ),
    "home_retry": (
        "I beg your pardon. I didn't quite hear where you live. "
        "Would you mind repeating that?"
    ),
    "general_unheard": (
        "I'm terribly sorry. I didn't quite hear that. "
        "Would you mind saying it again?"
    ),
    "didnt_follow": (
        "I'm afraid I didn't quite follow. "
        "Would you mind explaining that again?"
    ),
    "off_topic_template": (
        "I'm afraid that wasn't quite what I asked. "
        "Would you mind answering the question about {topic}?"
    ),
    "non_english": (
        "I'm afraid I didn't quite follow that. "
        "Would you mind repeating it in English?"
    ),
    "silence": "Take your time. Do let me know when you're ready.",
    "part_end": (
        "Thank you very much. That brings us to the end of this part."
    ),
    "transition_template": "Thank you. We'll now move on to Part {part}.",
    "skip_advance": "Very well. Let us move on.",
    "test_end": "Thank you. That is the end of the test.",
    "ask_names": "And your names are?",
    "ask_home_template": "Thank you. Where do you live, {candidate}?",
    "ask_partner_home_template": "Thank you. And you, {partner}?",
}


def greeting_for_hour(hour=None, tz_offset_minutes=None):
    """Return 'Good morning', 'Good afternoon', or 'Good evening'.

    Uses the server's local clock by default. If `tz_offset_minutes` is
    provided (minutes offset from UTC, e.g. -180 for UTC-3 or +60 for UTC+1),
    computes the user's local hour from UTC.
    """
    if hour is None:
        if tz_offset_minutes is not None:
            try:
                off = int(tz_offset_minutes)
                if -720 <= off <= 840:
                    utc_now = datetime.datetime.now(datetime.timezone.utc)
                    local_dt = utc_now + datetime.timedelta(minutes=off)
                    hour = local_dt.hour
            except (TypeError, ValueError):
                hour = None
        if hour is None:
            hour = time.localtime().tm_hour
    hour = int(hour) % 24
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def opening_greeting(hour=None, tz_offset_minutes=None):
    """Initial examiner greeting + name prompt."""
    g = greeting_for_hour(hour=hour, tz_offset_minutes=tz_offset_minutes)
    return f"{g}. My name is {EXAMINER_NAME}. {CANONICAL['ask_names']}"


def off_topic_prompt(topic):
    """Canonical formal examiner prompt when an answer is off-topic."""
    clean = re.sub(r"\s+", " ", str(topic or "this topic")).strip().rstrip(".?!")
    if not clean:
        clean = "this topic"
    return CANONICAL["off_topic_template"].format(topic=clean)


def part_transition(next_part):
    """Canonical formal examiner transition to the next part."""
    return CANONICAL["transition_template"].format(part=int(next_part))


# ---------------------------------------------------------------------------
# Tone & British English validation (used by tests and safety guards)
# ---------------------------------------------------------------------------
AMERICANISMS = (
    r"\bgotten\b",
    r"\bmom\b",
    r"\bmath\b",
    r"\bvacation\b",
    r"\bfall\b",
    r"\bsidewalk\b",
    r"\bcell\s+phone\b",
    r"\bsoccer\b",
    r"\btrain\s+station\b",
    r"\bcolor\b",
    r"\bcolors\b",
    r"\borganize\b",
    r"\borganizes\b",
    r"\borganized\b",
    r"\borganizing\b",
    r"\bfavorite\b",
    r"\bfavorites\b",
    r"\bcenter\b",
    r"\bcenters\b",
    r"\bapologize\b",
    r"\bapologized\b",
    r"\bbehavior\b",
    r"\bneighbor\b",
    r"\bneighbors\b",
    r"\btraveling\b",
    r"\btraveled\b",
    r"\bpracticing\b",
    r"\brealize\b",
    r"\brealized\b",
    r"\bprogram\b",
    r"\bprograms\b",
)

EXAMINER_FORBIDDEN_PHRASES = (
    r"\bcatch(?:es|ing)?\b",
    r"\bcaught\b",
    r"could\s+you\s+please\s+repeat\s+the\s+question",
    r"^\s*pardon\??\s*$",
    r"^\s*sorry\??\s*$",
    r"^\s*what\??\s*$",
    r"\bokay\b",
    r"\bok\b",
    r"\bhi\b",
    r"\bhey\b",
    r"\byeah\b",
    r"\bgonna\b",
    r"\bwanna\b",
    r"\bstuff\b",
    r"\bguys\b",
    r"\bno\s+worries\b",
    r"\bgot\s+it\b",
    r"\bgreat\s+job\b",
    r"\bawesome\b",
    r"\bexcellent!",
    r"\bwell\s+done!",
    r"\bno\s+problem\b",
    r"\balright\b",
    r"\blet['’]?s\s+go\b",
    r"^\s*ready\?\s*$",
    r"^\s*could\s+you\s+say\s+it\s+again\?\s*$",
    r"!!+",
)

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E0-\U0001F1FF]"
)

_AMERICAN_PATTERNS = [(p, re.compile(p, re.IGNORECASE)) for p in AMERICANISMS]
_EXAMINER_PATTERNS = [
    (p, re.compile(p, re.IGNORECASE)) for p in EXAMINER_FORBIDDEN_PHRASES
]


def check_language_rules(text):
    """Return list of British-English / Americanism violations in `text`."""
    violations = []
    s = str(text or "")
    for pat_str, rx in _AMERICAN_PATTERNS:
        m = rx.search(s)
        if m:
            violations.append(f"americanism:{m.group(0)}")
    if _EMOJI_RE.search(s):
        violations.append("emoji_present")
    return violations


def check_examiner_line(text):
    """Return list of tone or British-English violations for an examiner line."""
    s = str(text or "")
    violations = check_language_rules(s)
    for pat_str, rx in _EXAMINER_PATTERNS:
        m = rx.search(s)
        if m:
            violations.append(f"forbidden_examiner:{m.group(0)}")
    return violations


def check_partner_line(text):
    """Partner is exempt from formal register, NOT from British English rules."""
    return check_language_rules(text)
