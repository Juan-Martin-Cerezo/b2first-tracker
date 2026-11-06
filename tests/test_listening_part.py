"""Phase 114: changing the Listening mode never throws.

The Mode select used to carry `onchange="onLPartChange()"`. If the page was
interacted with while that inline handler's script had not run (a partial or
stale load), the browser threw `ReferenceError: onLPartChange is not defined`.
The control now uses addEventListener, so the markup without the script is
inert instead of broken.

This suite changes #lPart through every value and checks the label, the input
maximum and the default minutes, with no pageerror and no console.error.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

PARTS = {
    "all": {"max": 30, "min": 40},
    "1": {"max": 8, "min": 10},
    "2": {"max": 10, "min": 10},
    "3": {"max": 5, "min": 10},
    "4": {"max": 7, "min": 10},
}

READ_JS = """() => ({
    label: document.getElementById('lOkLbl').textContent,
    max: +document.getElementById('lOk').max,
    min: +document.getElementById('lMin').value,
    inline: document.getElementById('lPart').getAttribute('onchange'),
})"""


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors, console_errors = [], []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.on(
        "console",
        lambda m: console_errors.append(m.text)
        if m.type == "error" and "Failed to load resource" not in m.text else None,
    )
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    # Open the listening studio the way Today's Start does, so the control is
    # visible and painted from the real plan slot.
    pg.evaluate("openPlanUnit({skill:'l', value:2, min:10})")
    pg.wait_for_timeout(200)

    assert pg.get_attribute("#lPart", "onchange") is None, (
        "the select still relies on an inline onchange attribute"
    )

    for value, want in PARTS.items():
        pg.select_option("#lPart", value)
        pg.wait_for_timeout(80)
        got = pg.evaluate(READ_JS)
        assert got["label"] == f"Correct (out of {want['max']})", (
            f"value {value}: label {got['label']!r}, expected out of {want['max']}"
        )
        assert got["max"] == want["max"], (
            f"value {value}: input max {got['max']}, expected {want['max']}"
        )
        assert got["min"] == want["min"], (
            f"value {value}: minutes {got['min']}, expected {want['min']}"
        )
        OUT[value] = got

    # Fire the same event the browser fires, without Playwright's actionability
    # layer, to cover the listener itself.
    pg.evaluate("""() => {
        const el = document.getElementById('lPart');
        el.value = 'all';
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    pg.wait_for_timeout(80)
    assert pg.evaluate("document.getElementById('lOkLbl').textContent") == "Correct (out of 30)"

    assert page_errors == [], f"page errors: {page_errors}"
    assert console_errors == [], f"console errors: {console_errors}"
    OUT["page_errors"] = page_errors
    OUT["console_errors"] = console_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
