"""Phase 55: the report repeats one part without redoing the four.

The report screen carries "Repeat this part". It re-runs the part the report
itself points at (the weakest one, named by its tip) as a one-part session; the
four-part exam is never replayed and its saved row is never written twice.

  1. A saved four-part report shows the button in the report actions, in
     English and Spanish, with an aria-label that follows the switch.
  2. Pressing it opens the brief of a single part: that part, `full` false and a
     one-entry plan. The saved full-exam row is still there exactly once, so
     pressing the button writes nothing to D.log.
  3. Saving the repeated part's own report adds one single-part row and leaves
     the full-exam row untouched: two rows, one full, nothing duplicated.

Run:  uv run --with playwright python test_speaking_repeat.py
"""
import json
import os
import sys
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

os.environ.pop("B2_AI_KEY", None)

from playwright.sync_api import sync_playwright  # noqa: E402

import helpers  # noqa: E402

URL = helpers.isolated_server() + "/"
NAME = "speaking-repeat-suite"
PASS = "speaking-repeat-suite-pass-9"

# Part 2 is the weakest: no candidate turn at all, while the other three have
# two or three. The report's tip must therefore name part 2, which is not the
# part the full exam ended on (4) — so the test proves the target comes from
# the report and not from whatever part happened to be last.
TIP_PART = 2
FULL_ROW_KEYS = {"part": 0, "full": True, "parts": [1, 2, 3, 4], "min": 15,
                 "score": 3}


def wait_until(pg, expression, timeout_s, step=100):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pg.evaluate(expression):
            return True
        pg.wait_for_timeout(step)
    return False


def sp_rows(pg):
    return pg.evaluate("""() => {
        const doc = JSON.parse(localStorage.getItem(userKey()));
        return doc.log.filter(e => e.type === 'sp');
    }""")


def seed_full_report(pg):
    """A finished four-part session, saved once exactly as saveReport() does."""
    return pg.evaluate("""() => {
        SP_EXAM.part = 4;
        SPK.part = 4;
        SP_EXAM.full = true;
        SP_EXAM.session = {
            full: true, seed: 7, partner: 'Alex',
            plan: {parts: [{part: 1}, {part: 2}, {part: 3}, {part: 4}]},
            turns: {examiner: 6, partner: 3, candidate: 7},
            partStats: {
                1: {part: 1, planned: 120, seconds: 110, wall: 110,
                    turns: {examiner: 2, partner: 0, candidate: 2}},
                2: {part: 2, planned: 240, seconds: 170, wall: 170,
                    turns: {examiner: 1, partner: 1, candidate: 0}},
                3: {part: 3, planned: 240, seconds: 200, wall: 200,
                    turns: {examiner: 1, partner: 2, candidate: 2}},
                4: {part: 4, planned: 240, seconds: 210, wall: 210,
                    turns: {examiner: 2, partner: 0, candidate: 3}}
            }
        };
        SPK.reportData = {
            bands: {grammar_vocabulary: 3, discourse_management: 3,
                    pronunciation: null, interactive_communication: 3},
            metrics: {wpm: 90, fillers: 2, longest_silence: 0.5, overlap_ms: 0},
            duration_s: 900, evidence: [], fixes: []
        };
        /* ready() carries the session shape into the report like this. */
        SPK.reportFull = true;
        spxFinalizeReport(SPK.reportData);
        SP_EXAM.saved = false;
        SP_EXAM.entry = null;
        SP_EXAM.saveReport();
        return {tipPart: SPK.reportData.tipPart, screen: SP_EXAM.screen};
    }""")


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1200, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))

    pg.goto(URL + "app", wait_until="networkidle")
    helpers.login_user(pg, URL, NAME, PASS)
    helpers.dismiss_onboarding(pg)
    pg.evaluate("setLang('en')")
    pg.evaluate("async () => { await SP_EXAM.open(); }")

    seeded = seed_full_report(pg)
    assert seeded["tipPart"] == TIP_PART, f"wrong tip part: {seeded}"
    assert seeded["screen"] == "report", seeded

    rows = sp_rows(pg)
    assert len(rows) == 1, f"the full exam was saved {len(rows)} times"
    full_row = rows[0]
    for key, value in FULL_ROW_KEYS.items():
        assert full_row[key] == value, f"full row {key}: {full_row.get(key)!r}"

    # 1. The button lives in the saved report, translated, with its aria-label.
    assert pg.is_visible("#spxRepeatBtn"), "the report has no Repeat this part"
    assert pg.eval_on_selector(
        "#spxRepeatBtn",
        "el => !!el.closest('[data-spx-screen=\"report\"]')")
    en = pg.eval_on_selector("#spxRepeatBtn", """el => ({
        text: el.textContent.trim(),
        label: el.getAttribute('aria-label'),
        i18n: el.getAttribute('data-i18n'),
        ariaI18n: el.getAttribute('data-i18n-aria-label')
    })""")
    assert en == {"text": "Repeat this part", "label": "Repeat this part",
                  "i18n": "spx_repeat_part",
                  "ariaI18n": "spx_aria_repeat_part"}, en

    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(150)
    es = pg.eval_on_selector("#spxRepeatBtn", """el => ({
        text: el.textContent.trim(),
        label: el.getAttribute('aria-label')
    })""")
    assert es == {"text": "Repetir esta parte",
                  "label": "Repetir esta parte"}, es
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(150)
    out["1_button"] = {"en": en, "es": es}

    # 2. Pressing it starts one part only. The full exam's row is untouched.
    pg.click("#spxRepeatBtn")
    assert wait_until(
        pg,
        "SP_EXAM.screen === 'brief' && !!SP_EXAM.session &&"
        " SP_EXAM.session.plan.parts.length === 1", 15), \
        pg.evaluate("({screen: SP_EXAM.screen, plan: SP_EXAM.session &&"
                    " SP_EXAM.session.plan.parts.length})")

    repeat_state = pg.evaluate("""() => ({
        screen: SP_EXAM.screen,
        full: SP_EXAM.full,
        selectedFull: SP_EXAM.selectedFull,
        part: SP_EXAM.part,
        planParts: SP_EXAM.session.plan.parts.map(function (p) { return p.part; }),
        sessionFull: SP_EXAM.session.full,
        reportData: SPK.reportData,
        reportFull: SPK.reportFull,
        saved: SP_EXAM.saved
    })""")
    assert repeat_state["part"] == TIP_PART, repeat_state
    assert repeat_state["full"] is False, repeat_state
    assert repeat_state["selectedFull"] is False, repeat_state
    assert repeat_state["sessionFull"] is False, repeat_state
    assert repeat_state["planParts"] == [TIP_PART], repeat_state
    assert repeat_state["reportData"] is None, \
        "the old report is still waiting to be saved again"
    assert repeat_state["saved"] is False, repeat_state

    rows = sp_rows(pg)
    assert len(rows) == 1, \
        f"pressing Repeat wrote {len(rows) - 1} extra row(s) to D.log"
    assert rows[0].get("full") is True, rows[0]
    out["2_repeat_starts_one_part"] = repeat_state

    # 3. The repeated part's own report is a single-part row; the full one stays.
    saved = pg.evaluate("""() => {
        SPK.reportData = {
            bands: {grammar_vocabulary: 4, discourse_management: 4,
                    pronunciation: null, interactive_communication: 4},
            metrics: {wpm: 95, fillers: 0, longest_silence: 0, overlap_ms: 0},
            duration_s: 120, evidence: [], fixes: []
        };
        spxFinalizeReport(SPK.reportData);
        SP_EXAM.saved = false;
        SP_EXAM.entry = null;
        SP_EXAM.saveReport();
        const doc = JSON.parse(localStorage.getItem(userKey()));
        return doc.log.filter(e => e.type === 'sp');
    }""")
    assert len(saved) == 2, f"expected 2 rows, got {len(saved)}: {saved}"

    full_rows = [r for r in saved if r.get("full") is True]
    assert len(full_rows) == 1, f"the full exam row was duplicated: {saved}"
    for key, value in FULL_ROW_KEYS.items():
        assert full_rows[0][key] == value, \
            f"the full row was rewritten ({key}={full_rows[0].get(key)!r})"

    repeat_rows = [r for r in saved if r.get("full") is not True]
    assert len(repeat_rows) == 1, f"expected one repeated part: {saved}"
    row = repeat_rows[0]
    assert row["part"] == TIP_PART, row
    assert "parts" not in row, f"a one-part row listed parts: {row}"
    out["3_log_rows"] = {"count": len(saved), "repeat": row,
                         "full": full_rows[0]}

    assert page_errors == [], f"page errors: {page_errors}"
    out["4_errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
