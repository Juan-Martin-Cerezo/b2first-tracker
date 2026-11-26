#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 guard — verify old Speaking UI, Live Studio, Azure PA, and legacy routes are gone.

Run: python3 tests/test_speaking_v3_no_old_ui.py
"""
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "index.html")


def main():
    with open(INDEX_HTML, "r", encoding="utf-8") as fh:
        src = fh.read()

    forbidden_patterns = [
        (r"spx", "legacy spx identifier"),
        (r"spxTranscript", "legacy spxTranscript"),
        (r"/api/speaking/turn\b", "legacy /api/speaking/turn"),
        (r"/api/speaking/report\b", "legacy /api/speaking/report"),
        (r"/api/speaking/partner\b", "legacy /api/speaking/partner"),
        (r"/api/speaking/pa\b", "legacy /api/speaking/pa"),
        (r"/api/speaking/token\b", "legacy /api/speaking/token"),
        (r"/api/speaking/capabilities\b", "legacy /api/speaking/capabilities"),
        (r"/api/speaking/minute\b", "legacy /api/speaking/minute"),
        (r"Live Studio", "removed Live Studio"),
        (r"\blivePanel\b", "legacy livePanel"),
        (r"\bspkPanel\b", "legacy spkPanel"),
        (r"\bspLiveCard\b", "legacy spLiveCard"),
        (r"Azure Pronunciation", "removed Azure Pronunciation"),
        (r"ob_acct_pron", "removed pronunciation account row"),
    ]

    failures = []
    for pat, label in forbidden_patterns:
        matches = re.findall(pat, src, re.IGNORECASE)
        if matches:
            failures.append(f"{label} ({pat!r}): {len(matches)} match(es)")

    # Verify Speaking overlay markup itself contains zero visible "pronunciation" or "transcript"
    m_ov = re.search(
        r"<!-- ============ SPEAKING V3 EXAM OVERLAY ============ -->.*?<!-- ============ PLAN ROTATION RESET CONFIRMATION ============",
        src,
        re.S,
    )
    assert m_ov, "Could not locate SPEAKING V3 EXAM OVERLAY block in index.html"
    ov_html = m_ov.group(0)
    for word in ("pronunciation", "transcript", "live studio", "azure"):
        if word in ov_html.lower():
            failures.append(f"Forbidden word {word!r} inside Speaking overlay markup")

    # Verify Speaking v3 JS block contains zero "pronunciation" or "transcript" UI text
    m_js = re.search(
        r"/\* ---------- SPEAKING V3 UI ENGINE ----------.*?window\.SP_EXAM=\{",
        src,
        re.S,
    )
    assert m_js, "Could not locate SPEAKING V3 UI ENGINE JS block in index.html"
    js_block = m_js.group(0)
    if "pronunciation" in js_block.lower():
        failures.append("Forbidden word 'pronunciation' inside Speaking v3 JS engine")
    if "localStorage" in js_block:
        failures.append("Speaking v3 JS engine must not touch localStorage")
    if "console.log" in js_block:
        failures.append("Speaking v3 JS engine must not console.log")

    # Verify new Speaking v3 endpoints and aliases exist
    required = [
        "/api/speaking/v3/catalog",
        "/api/speaking/v3/sessions",
        "/api/speaking/v3/own-tasks",
        "window.SPEAKING=SPEAKING",
        "window.SP_EXAM={",
        "function openSpeakingExam(",
    ]
    for req in required:
        if req not in src:
            failures.append(f"Missing required Speaking v3 symbol/route: {req!r}")

    assert not failures, "Old Speaking UI check failed:\n  - " + "\n  - ".join(failures)
    print("PASS test_speaking_v3_no_old_ui")
    return 0


if __name__ == "__main__":
    sys.exit(main())
