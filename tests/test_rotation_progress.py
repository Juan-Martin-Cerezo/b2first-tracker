"""The rotation card marks how far the current pass of each cycle is done.

The count comes from D.log: a unit counts once per pass, a repeat does not
count twice, and a full pass closes so the next new unit starts the next one.
The card says "3 of 7 Reading parts done" and the same for the other three
cycles; no estimate, no stored cursor.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"

# Rows are handed in as a JSON list. Newest first is how the app stores them,
# so the seed keeps that order to prove the count does not depend on it.
SEED = """(rows) => {
    D.log = rows.slice();
    D.log.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
    D.sessionOffset = 0;
    D.settings.itemsPerSession = 1;
    D.settings.rotationMode = 'by-part';
    save();
    renderPlan();
}"""

READ = """() => ({
    mode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
    lines: [...document.querySelectorAll('#rotationCardBody .rot-done')]
        .map(el => ({skill: el.dataset.skill, text: el.textContent.trim()})),
})"""


def rows(*units, day="2026-10-01"):
    return [{"type": "ue", "part": part, "date": day} for part in units]


def by_skill(state):
    return {line["skill"]: line["text"] for line in state["lines"]}


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(250)

    # 0. Empty log: every cycle is honestly at zero, out of its real length.
    pg.evaluate(SEED, [])
    pg.wait_for_timeout(200)
    zero = by_skill(pg.evaluate(READ))
    assert zero == {
        "rue": "0 of 7 Reading parts done",
        "l": "0 of 4 Listening parts done",
        "w": "0 of 5 Writing tasks done",
        "sp": "0 of 4 Speaking parts done",
    }, f"the empty log does not read as zero: {zero}"
    out_zero = zero

    # 1. Three Reading parts logged: three of seven, other cycles untouched.
    pg.evaluate(SEED, rows(1, 2, 3))
    pg.wait_for_timeout(200)
    three = by_skill(pg.evaluate(READ))
    assert three["rue"] == "3 of 7 Reading parts done", three["rue"]
    assert three["l"] == "0 of 4 Listening parts done", three["l"]
    out_three = three

    # 2. Repeating a unit inside the pass does not inflate the count.
    pg.evaluate(SEED, rows(1, 1, 2))
    pg.wait_for_timeout(200)
    repeated = by_skill(pg.evaluate(READ))
    assert repeated["rue"] == "2 of 7 Reading parts done", repeated["rue"]

    # 3. Seven logged parts close the pass: seven of seven, not a reset.
    full = rows(1, 2, 3, 4, 5, 6, 7)
    pg.evaluate(SEED, full)
    pg.wait_for_timeout(200)
    seven = by_skill(pg.evaluate(READ))
    assert seven["rue"] == "7 of 7 Reading parts done", seven["rue"]
    out_seven = seven

    # 4. The next new unit after a full pass opens the following one.
    pg.evaluate(SEED, full + [{"type": "ue", "part": 2, "date": "2026-10-02"}])
    pg.wait_for_timeout(200)
    next_pass = by_skill(pg.evaluate(READ))
    assert next_pass["rue"] == "1 of 7 Reading parts done", next_pass["rue"]

    # 5. Spanish reads from the second dictionary.
    pg.evaluate(SEED, rows(1, 2, 3))
    pg.wait_for_timeout(200)
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    spanish = by_skill(pg.evaluate(READ))
    assert spanish["rue"] == "3 de 7 partes de Reading hechas", spanish["rue"]
    assert spanish["w"] == "0 de 5 tareas de Writing hechas", spanish["w"]
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    # 6. In full-section a whole paper is one session: no unit-by-unit lines.
    pg.evaluate(
        "D.settings.rotationMode = 'full-section'; save(); renderPlan();"
    )
    pg.wait_for_timeout(250)
    whole = pg.evaluate(READ)
    assert whole["lines"] == [], f"unit progress in full-section: {whole}"
    assert "A whole paper per session." in whole["mode"], whole["mode"]
    pg.evaluate(
        "D.settings.rotationMode = 'by-part'; save(); renderPlan();"
    )
    pg.wait_for_timeout(250)

    # 7. Both dictionaries carry the four keys the card uses.
    missing = pg.evaluate(
        """() => ['plan_progress_rue','plan_progress_l','plan_progress_w',
                  'plan_progress_sp'].filter(k => !I18N.en[k] || !I18N.es[k])"""
    )
    assert missing == [], f"keys missing from a dictionary: {missing}"

    assert page_errors == [], f"page errors: {page_errors}"
    out = {
        "0_empty": out_zero,
        "1_three": out_three,
        "3_full": out_seven,
        "5_spanish": spanish,
        "errors": page_errors,
    }
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
