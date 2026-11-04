"""Phase 82: no chip-with-a-dot pills and no orphan i18n keys for them.

The five `.chip-plan` pills (Interface, Free, FCE Format, 4-Session Loop,
Your key, your cost) are gone from every view, their CSS rule is gone, and
neither dictionary carries their keys any more.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"

REMOVED_KEYS = [
    "plan_language_chip",
    "license_chip_free",
    "license_chip_byo",
    "license_chip_pro",
    "plan_fce_format",
    "plan_rotation_chip",
    "byo_chip",
]

VIEWS = ["hoy", "practice", "resources", "exam", "prog", "plan", "err", "ia", "diag"]

out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 1000})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    # 1. Walk every view; neither the pill nor its dot survives anywhere.
    visited = []
    for view in VIEWS:
        pg.evaluate(f"showView('{view}')")
        pg.wait_for_timeout(200)
        visited.append(view)
        pills = pg.evaluate("document.querySelectorAll('.chip-plan').length")
        dots = pg.evaluate("document.querySelectorAll('.dot').length")
        assert pills == 0, f".chip-plan still rendered in {view}: {pills}"
        assert dots == 0, f"the pill dot still rendered in {view}: {dots}"
    out["views"] = visited

    # 2. The app still renders the plan card without the deleted node.
    pg.evaluate("showView('plan'); renderPlanCard();")
    pg.wait_for_timeout(200)
    assert pg.evaluate("document.querySelectorAll('.chip-plan').length") == 0
    assert not pg.evaluate("!!document.getElementById('planNameText')"), (
        "#planNameText still exists in the DOM"
    )
    assert not pg.evaluate("!!document.getElementById('planNameChip')"), (
        "#planNameChip still exists in the DOM"
    )

    # 3. No markup references a deleted key.
    used = pg.evaluate(
        """(keys) => {
        const attrs = ['data-i18n', 'data-i18n-html', 'data-i18n-title',
                       'data-i18n-aria-label', 'data-i18n-placeholder'];
        const found = [];
        document.querySelectorAll('[data-i18n], [data-i18n-html], [data-i18n-title], [data-i18n-aria-label], [data-i18n-placeholder]').forEach(el => {
            attrs.forEach(a => { const k = el.getAttribute(a); if (k && keys.indexOf(k) >= 0) found.push(k); });
        });
        return found;
    }""",
        REMOVED_KEYS,
    )
    assert used == [], f"markup still references deleted i18n keys: {used}"

    # 4. Neither dictionary carries the deleted keys.
    present = pg.evaluate(
        """(keys) => keys.filter(k => (k in I18N.en) || (k in I18N.es))""",
        REMOVED_KEYS,
    )
    assert present == [], f"i18n dictionaries still define deleted keys: {present}"
    out["removed_keys"] = REMOVED_KEYS

    # 5. The css rule is gone too.
    css = pg.evaluate(
        """() => {
        let css = '';
        for (const ss of document.styleSheets) {
            try { for (const r of ss.cssRules) css += r.cssText + '\\n'; } catch (e) {}
        }
        return css;
    }"""
    )
    assert ".chip-plan" not in css, ".chip-plan CSS rule still present"

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
