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

    # PRACTICE: By part + always-visible Library
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(400)
    out["library_rows"] = pg.eval_on_selector_all("#pracLibList a.exlib-row", "els => els.length")
    assert out["library_rows"] > 0, "Practice Library rendered 0 rows on mobile"

    # filter works on mobile
    pg.fill("#pracLibSearch", "listening")
    pg.wait_for_timeout(200)
    out["filtro_listening"] = pg.eval_on_selector_all("#pracLibList a.exlib-row", "els => els.length")
    assert out["filtro_listening"] > 0, "Listening search returned 0 rows on mobile"
    pg.fill("#pracLibSearch", "")

    # PROGRESS: export/import present + gates
    pg.click("nav button[data-view='prog']")
    pg.wait_for_timeout(200)
    out["gates"] = pg.eval_on_selector_all(".gate", "els => els.length")
    out["export_btn"] = pg.evaluate("typeof exportData === 'function'")

    # rubric checkboxes exist in the DOM (Session A is task 2 of TODAY)
    out["rubric_items"] = pg.eval_on_selector_all(".rub", "els => els.length")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
