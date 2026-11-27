# -*- coding: utf-8 -*-
"""Deterministic text facts and rubric guardrails for B2 First Writing.

Stdlib only: no HTTP, no model calls, pure functions.
Guardrails enforce hard rules of the Cambridge B2 First assessment scales so
individual criteria cannot inflate or leak into each other.
"""
import re

COLLAPSE_KEYS = ("content", "communicative_achievement", "organisation")
BAND_KEYS = ("content", "communicative_achievement", "organisation", "language")

CORE_BASIC_ERROR_TYPES = frozenset((
    "subject_verb",
    "article",
    "modal_infinitive",
    "tense",
))

_FENCE_RE = re.compile(r"<<<[A-Za-z0-9_]+>>>")
_SENTENCE_END_RE = re.compile(r"[.!?]+")
_APOSTROPHE_RE = re.compile(r"[\u2018\u2019\u02bc]")

# Contractions only (deliberately excludes noun possessives like people's,
# today's, government's).
_CONTRACTION_RE = re.compile(
    r"\b(?:"
    r"[a-z]+n't"
    r"|i'm"
    r"|(?:you|we|they|who|there)'re"
    r"|(?:i|you|we|they|could|would|should|might|must|who)'ve"
    r"|(?:i|you|he|she|it|we|they|that|there|who|what)'ll"
    r"|(?:i|you|he|she|it|we|they|that|there|who|what|where|how)'d"
    r"|(?:it|that|there|here|he|she|who|what|where|when|why|how|let|"
    r"everyone|everybody|someone|somebody|nobody|nothing|everything)'s"
    r")\b",
    re.I,
)

# Informal/chat/blog register markers.
_INFORMAL_WORD_RE = re.compile(
    r"\b(?:"
    r"hey|yo|gonna|gotta|wanna|kinda|sorta|dunno|ain't|"
    r"yeah|yep|nope|nah|lol|omg|btw|tbh|imo|"
    r"awesome|cool|super|hyped|stuff|guys|folks|loads|tons|crap|"
    r"totally|chill|vibe|vibes|sucks|dude|bro|mate"
    r")\b",
    re.I,
)

_INFORMAL_PHRASE_RE = re.compile(
    r"\b(?:"
    r"you\s+know|you\s+guys|wrap\s+it\s+up|pitch\s+in|first\s+off|"
    r"don't\s+you\s+think|what\s+do\s+you\s+think|like\s+you\s+and\s+me|"
    r"a\s+bunch\s+of|hang\s+out"
    r")\b",
    re.I,
)

# Formal / academic register markers (connectors + impersonal "one").
_FORMAL_WORD_RE = re.compile(
    r"\b(?:"
    r"therefore|however|moreover|furthermore|nevertheless|nonetheless|"
    r"consequently|accordingly|hence|thus|notwithstanding|whereas|"
    r"conversely|subsequently|undeniably"
    r")\b",
    re.I,
)

_FORMAL_PHRASE_RE = re.compile(
    r"\b(?:"
    r"in\s+addition|in\s+conclusion|on\s+the\s+contrary|"
    r"as\s+a\s+consequence|with\s+regard\s+to|in\s+terms\s+of|"
    r"one\s+(?:must|should|can|cannot|may|might|could|would|ought|needs|has|is)"
    r")\b",
    re.I,
)

_COMMON_ACRONYMS = frozenset((
    "USA", "UNESCO", "BBC", "NGO", "GDP", "CEO", "COVID", "NATO",
    "UNHCR", "NASA", "WHO", "PDF", "HTTP", "HTML", "USB", "GPS",
    "SUV", "DNA", "RNA", "FAQ", "DIY", "VIP", "ATM", "PIN", "SIM", "SMS",
))


def _unique_in_order(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _strip_fences(text):
    cleaned = _FENCE_RE.sub("", str(text or ""))
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned.strip()


def text_facts(text):
    """Extract deterministic, server-verified text metrics and register cues.

    - ``words``: whitespace split, ignoring fence markers and standalone
      punctuation, counting contractions as one word.
    - ``paragraphs``: split on blank lines; 1 if non-empty with no blank lines.
    - ``sentences``: sentence-ending punctuation count (at least 1 if non-empty).
    - ``contractions``: distinct lowercased contractions in order of appearance.
    - ``informal_markers``: distinct lowercased informal markers and ``"!"``.
    - ``formal_markers``: distinct lowercased formal linkers and impersonal ``one``.
    - ``all_caps_words``: count of ALL-CAPS alphabetic words (len >= 3, non-acronym).
    """
    cleaned = _strip_fences(text)
    if not cleaned:
        return {
            "words": 0,
            "paragraphs": 1,
            "sentences": 0,
            "contractions": [],
            "informal_markers": [],
            "formal_markers": [],
            "all_caps_words": 0,
        }

    normalised = _APOSTROPHE_RE.sub("'", cleaned)
    tokens = normalised.split()
    words = sum(1 for tok in tokens if any(ch.isalnum() for ch in tok))

    para_chunks = [p.strip() for p in re.split(r"\n[ \t]*\n+", normalised) if p.strip()]
    paragraphs = len(para_chunks) if para_chunks else 1

    sentence_hits = _SENTENCE_END_RE.findall(normalised)
    sentences = len(sentence_hits) if sentence_hits else (1 if words > 0 else 0)

    contractions = _unique_in_order(m.group(0).lower() for m in _CONTRACTION_RE.finditer(normalised))

    informal_hits = []
    for m in re.finditer(
        f"(?:{_INFORMAL_PHRASE_RE.pattern})|(?:{_INFORMAL_WORD_RE.pattern})|!",
        normalised,
        re.I,
    ):
        val = " ".join(m.group(0).lower().split())
        informal_hits.append(val)
    informal_markers = _unique_in_order(informal_hits)

    formal_hits = []
    for m in re.finditer(
        f"(?:{_FORMAL_PHRASE_RE.pattern})|(?:{_FORMAL_WORD_RE.pattern})",
        normalised,
        re.I,
    ):
        val = " ".join(m.group(0).lower().split())
        formal_hits.append(val)
    formal_markers = _unique_in_order(formal_hits)

    all_caps_words = 0
    for tok in tokens:
        stripped_tok = tok.strip(".,!?;:\"'()[]{}-—–")
        if len(stripped_tok) >= 3 and stripped_tok.isalpha() and stripped_tok.isupper():
            if stripped_tok not in _COMMON_ACRONYMS:
                all_caps_words += 1

    return {
        "words": words,
        "paragraphs": paragraphs,
        "sentences": sentences,
        "contractions": contractions,
        "informal_markers": informal_markers,
        "formal_markers": formal_markers,
        "all_caps_words": all_caps_words,
    }


def is_collapsed(bands):
    """True when Content, Communicative Achievement and Organisation share one band."""
    if not isinstance(bands, dict):
        return False
    vals = [bands.get(k) for k in COLLAPSE_KEYS]
    if any(v is None for v in vals):
        return False
    return len(set(vals)) == 1


def apply_guards(bands, facts, audit, kind=None):
    """Apply deterministic rubric ceiling rules to model-assigned bands.

    Rules only ever lower a band, never raise it. The caller's ``bands`` dict
    is never mutated. Criterion independence is enforced strictly:
    - Paragraphing NEVER clamps ``language``.
    - Grammar errors NEVER clamp ``organisation``.
    - ``ca_informal_sustained`` is skipped for ``email`` tasks because informal
      emails are a legitimate B2 First Part 2 genre.

    Returns ``(guarded_bands, applied_rule_ids)``.
    """
    out = {k: int(bands[k]) for k in BAND_KEYS}
    applied = []
    facts = facts if isinstance(facts, dict) else {}

    def clamp(key, ceiling, rule_id):
        if out[key] > ceiling:
            out[key] = ceiling
        if rule_id not in applied:
            applied.append(rule_id)

    words = int(facts.get("words", 0) or 0)
    paragraphs = int(facts.get("paragraphs", 1) or 1)
    contractions = facts.get("contractions") or []
    informal_markers = facts.get("informal_markers") or []
    formal_markers = facts.get("formal_markers") or []

    # 1. Very short submission (< 100 words)
    if words < 100:
        clamp("content", 2, "content_short_100")

    # 2. Short submission (100..119 words)
    elif words < 120:
        clamp("content", 3, "content_short_120")

    # 3-5. Task point coverage rules from the pre-scoring audit
    if isinstance(audit, dict):
        off_topic = bool(audit.get("off_topic"))
        raw_points = audit.get("task_points")
        points = [p for p in raw_points if isinstance(p, dict)] if isinstance(raw_points, list) else []
        n_total = len(points)
        n_absent = sum(1 for p in points if p.get("status") == "absent")
        n_partial = sum(1 for p in points if p.get("status") == "partial")

        if off_topic or (n_total > 0 and n_absent == n_total):
            clamp("content", 1, "content_points_all_absent")
        elif n_absent >= 2:
            clamp("content", 2, "content_points_missing_2")
        elif n_absent == 1:
            clamp("content", 2, "content_points_missing_1")
        elif n_partial >= 1:
            clamp("content", 3, "content_points_missing_1")

    # 6. Organisation: single wall of text (< 2 paragraphs).
    # Independence rule: paragraphing NEVER clamps language.
    if paragraphs < 2:
        clamp("organisation", 2, "organisation_no_paragraphs")

    # 7. Communicative Achievement: sustained informal/chat register in non-email genres.
    task_kind = str(kind or "").strip().lower()
    if task_kind != "email":
        if (
            len(informal_markers) >= 3
            and len(contractions) >= 2
            and len(formal_markers) == 0
        ):
            clamp("communicative_achievement", 2, "ca_informal_sustained")

    # 8. Language: >= 5 distinct grammar errors including at least one core basic error type.
    # Independence rule: grammar errors NEVER clamp organisation.
    if isinstance(audit, dict):
        raw_errors = audit.get("grammar_errors")
        if isinstance(raw_errors, list):
            seen_quotes = set()
            has_core_basic = False
            for err in raw_errors:
                if not isinstance(err, dict):
                    continue
                quote = str(err.get("quote") or "").strip().lower()
                err_type = str(err.get("type") or "").strip().lower()
                if not quote:
                    continue
                if quote not in seen_quotes:
                    seen_quotes.add(quote)
                    if err_type in CORE_BASIC_ERROR_TYPES:
                        has_core_basic = True
            if len(seen_quotes) >= 5 and has_core_basic:
                clamp("language", 2, "language_basic_errors")

    # 9. Over-long submission (> 250 words): cap Content and Communicative Achievement at 4.
    if words > 250:
        clamp("content", 4, "length_over_250")
        clamp("communicative_achievement", 4, "length_over_250")

    return out, applied
