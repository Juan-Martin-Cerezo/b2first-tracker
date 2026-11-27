import json
from playwright.sync_api import sync_playwright
from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    out["titulo"] = pg.title()

    # horizontal overflow?
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # TODAY: A/B sessions visible + rotation
    out["sesA"] = pg.evaluate("getComputedStyle(document.getElementById('sesA')).display")
    out["sesB"] = pg.evaluate("getComputedStyle(document.getElementById('sesB')).display")
    out["sesFull"] = pg.evaluate("getComputedStyle(document.getElementById('sesFull')).display")
    out["rot_opts"] = pg.evaluate("QUEUE_CYCLES.w.length")

    # full nav present (10 views + More)?
    out["nav_btns"] = pg.eval_on_selector_all("nav button", "els => els.length")

    # PRACTICE: two intents + inline part chooser
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(400)
    assert pg.evaluate("document.getElementById('practiceLibraryCard').hidden"), "Library leaked into Practice"
    out["intent_cards"] = pg.eval_on_selector_all(".practice-intent-card", "els => els.length")
    assert out["intent_cards"] == 2, f"Expected 2 practice intents, got {out['intent_cards']}"
    out["part_rows"] = pg.eval_on_selector_all("#practicePartChooser .part-row", "els => els.length")
    assert out["part_rows"] == 17, f"Expected 17 part rows, got {out['part_rows']}"
    out["charts"] = pg.eval_on_selector_all("#practiceOverview .practice-progress-card", "els => els.length")
    assert out["charts"] == 0, f"Practice still has {out['charts']} progress charts"
    out["practice_overview_absent"] = pg.evaluate("document.getElementById('practiceOverview') === null")
    assert out["practice_overview_absent"], "Practice still contains #practiceOverview"
    pg.click("#practicePartChooser .part-row")
    pg.wait_for_timeout(400)
    assert pg.evaluate("(() => { const v=document.getElementById('v-sesion'); return (v&&v.classList.contains('active')) || (document.getElementById('sessionTabSession') && !document.getElementById('sessionTabSession').hidden); })()"), "Part tap did not open Session"
    pg.evaluate("typeof closeSessionStudios === 'function' && closeSessionStudios()")
    pg.wait_for_timeout(200)
    pg.click("nav button[data-view='prog']")
    pg.wait_for_timeout(200)
    out["gates"] = pg.eval_on_selector_all(".gate", "els => els.length")
    out["export_btn"] = pg.evaluate("typeof exportData === 'function'")

    # rubric checkboxes exist in the DOM (Session A is task 2 of TODAY)
    out["rubric_items"] = pg.eval_on_selector_all(".rub", "els => els.length")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
