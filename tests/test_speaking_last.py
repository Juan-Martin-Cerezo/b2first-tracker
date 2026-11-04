"""Phase 54: TODAY says when the last speaking exam was and how many parts it had.

The card reads D.log, nothing is recomputed and nothing is requested from the
server. The test seeds the log itself:

  1. No `sp` row: the card is hidden.
  2. A seeded log with a full exam (one row, `parts:[1,2,3,4]`) and an older
     single-part row shows the full exam's date and "4 parts done"; a newer
     non-speaking row never wins.
  3. A single-part row counts as one part, in the singular.
  4. The newest row wins by date even when the array is not sorted.
  5. The card is translated to Spanish with the language switch.
  6. Logging a new exam updates the card without a reload.

Run:  uv run --with playwright python test_speaking_last.py
"""
import json
import os
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

os.environ.pop("B2_AI_KEY", None)

from playwright.sync_api import sync_playwright  # noqa: E402

import helpers  # noqa: E402

URL = helpers.isolated_server() + "/"
NAME = "speaking-last-suite"
PASS = "speaking-last-suite-pass-9"

FULL_ROW = {
    "type": "sp", "date": "2026-10-30", "created_at": 300,
    "part": 0, "full": True, "parts": [1, 2, 3, 4], "min": 15,
}
SINGLE_ROW = {
    "type": "sp", "date": "2026-10-01", "created_at": 100,
    "part": 2, "min": 3,
}
UE_ROW = {
    "type": "ue", "date": "2026-11-02", "created_at": 400,
    "part": 1, "correct": 8, "total": 8,
}


def seed(pg, rows):
    """Put the rows in D.log exactly as stored and paint the view."""
    pg.evaluate(
        """rows => {
            D.log = rows;
            refreshAll();
        }""",
        rows,
    )


def card_text(pg):
    return pg.inner_text("#lastSpeaking")


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1200, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))

    pg.goto(URL + "app", wait_until="networkidle")
    user = helpers.login_user(pg, URL, NAME, PASS)
    helpers.dismiss_onboarding(pg)

    # 1. No speaking exam yet: the card stays out of the view.
    seed(pg, [UE_ROW])
    assert not pg.is_visible("#lastSpeaking"), "the card shows with no speaking exam"
    out["1_empty"] = {"visible": False}

    # 2. Full exam wins over the older single part, and over a newer UE row.
    seed(pg, [FULL_ROW, SINGLE_ROW, UE_ROW])
    assert pg.is_visible("#lastSpeaking"), "the card is hidden with a speaking exam"
    text = card_text(pg)
    assert "Last speaking exam" in text, f"missing title: {text!r}"
    assert "30/10/2026" in text, f"wrong date: {text!r}"
    assert "4 parts done" in text, f"wrong part count: {text!r}"
    assert "01/10/2026" not in text, f"showed the older exam: {text!r}"
    out["2_full_exam"] = {"text": text}

    # 3. A single-part row counts as one part, in the singular.
    seed(pg, [SINGLE_ROW])
    text = card_text(pg)
    assert "01/10/2026" in text, f"wrong date: {text!r}"
    assert "1 part done" in text, f"wrong singular: {text!r}"
    assert "parts done" not in text, f"plural used for one part: {text!r}"
    out["3_single_part"] = {"text": text}

    # 4. The newest row wins by date, not by array position.
    seed(pg, [SINGLE_ROW, FULL_ROW])
    text = card_text(pg)
    assert "30/10/2026" in text and "4 parts done" in text, (
        f"did not pick the newest row: {text!r}"
    )
    out["4_unsorted"] = {"text": text}

    # 5. The language switch translates the card.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    text = card_text(pg)
    assert "Último examen de Speaking" in text, f"not translated: {text!r}"
    assert "30/10/2026" in text and "4 partes hechas" in text, (
        f"Spanish card is wrong: {text!r}"
    )
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)
    out["5_spanish"] = {"text": text}

    # 6. Logging an exam updates the card immediately (no reload).
    pg.evaluate("""() => {
        D.log = [];
        refreshAll();
        log({type: 'sp', part: 3, min: 4});
    }""")
    pg.wait_for_timeout(200)
    text = card_text(pg)
    assert pg.is_visible("#lastSpeaking"), "a newly logged exam did not show"
    assert "1 part done" in text, f"new exam not counted: {text!r}"
    out["6_new_exam"] = {"text": text}

    assert page_errors == [], f"page errors: {page_errors}"
    out["7_errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
