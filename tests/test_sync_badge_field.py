"""Phase 56: the sync badge names the field the server rejected.

The server answers a bad progress document with
`422 {"error": "invalid progress", "field": "<path>"}`. This drives the real
app against a throwaway server, makes it send an oversized string, and checks
that the badge stops being a mute dot:

  1. Before the bad save the badge is hidden and the state is "saved".
  2. After it, the state is "invalid", the badge is visible (8 px dot) and both
     its tooltip and accessible name carry the exact field path.
  3. The name is translated, not hard-coded English (es label).
  4. Fixing the value brings the badge back to "saved" and clears the field.

Run:  uv run --with playwright python tests/test_sync_badge_field.py
"""
import json
import os
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

from playwright.sync_api import sync_playwright  # noqa: E402

import helpers  # noqa: E402

URL = helpers.isolated_server() + "/"
NAME = "sync-badge-field-suite"
PASS = "sync-badge-field-suite-pass-9"
KEY = "settings.probe_field_501"
LONG = "x" * 501

out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1200, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))

    pg.goto(URL + "app", wait_until="networkidle")
    helpers.login_user(pg, URL, NAME, PASS)
    helpers.dismiss_onboarding(pg)

    # 1. Baseline: the pull succeeded, so the dot stays out of the way.
    pg.wait_for_function("() => SYNC_STATE === 'ok'", timeout=15000)
    assert pg.evaluate("() => SYNC_STATE") == "ok"
    assert pg.evaluate(
        "() => document.getElementById('syncBadge').getBoundingClientRect().width < 1"
    ), "the badge is visible while everything is saved"
    out["1_baseline"] = {"state": "ok", "hidden": True}

    # 2. An oversized string in the document: 422 from the real server.
    pg.evaluate(
        """long => { D.settings.probe_field_501 = long; save(); }""", LONG
    )
    pg.wait_for_function("() => SYNC_STATE === 'invalid'", timeout=15000)
    badge = pg.evaluate(
        """() => {
            const el = document.getElementById('syncBadge');
            const r = el.getBoundingClientRect();
            return {
                field: SYNC_INVALID_FIELD,
                title: el.getAttribute('title') || '',
                aria: el.getAttribute('aria-label') || '',
                cls: el.className,
                w: r.width, h: r.height
            };
        }"""
    )
    out["2_invalid"] = badge
    assert badge["field"] == "settings.probe_field_501", badge["field"]
    assert "settings.probe_field_501" in badge["title"], badge["title"]
    assert "settings.probe_field_501" in badge["aria"], badge["aria"]
    assert "state-off" in badge["cls"], badge["cls"]
    assert badge["w"] >= 8 and badge["h"] >= 8, f"badge not visible: {badge['w']}x{badge['h']}"
    assert LONG[:20] not in badge["title"], "the value is shown, not the field name"

    # 3. Translated: the same field path inside the Spanish sentence.
    pg.evaluate("setLang('es')")
    pg.wait_for_function("() => SYNC_STATE === 'invalid'", timeout=15000)
    es = pg.evaluate(
        """() => ({
            field: SYNC_INVALID_FIELD,
            aria: document.getElementById('syncBadge').getAttribute('aria-label') || ''
        })"""
    )
    out["3_spanish"] = es
    assert "settings.probe_field_501" in es["aria"], es["aria"]
    assert es["aria"].startswith("Sin sincronizar"), es["aria"]

    # 4. Fix the value: the badge goes back to the saved state, with no field.
    pg.evaluate(
        """() => { delete D.settings.probe_field_501; save(); }"""
    )
    pg.wait_for_function("() => SYNC_STATE === 'ok'", timeout=15000)
    fixed = pg.evaluate(
        """() => ({
            field: SYNC_INVALID_FIELD,
            aria: document.getElementById('syncBadge').getAttribute('aria-label') || ''
        })"""
    )
    out["4_recovered"] = fixed
    assert fixed["field"] == "", fixed["field"]
    assert "settings.probe_field_501" not in fixed["aria"], fixed["aria"]

    assert not page_errors, f"page errors: {page_errors[:3]}"
    browser.close()

print(json.dumps(out, indent=1, ensure_ascii=False))
