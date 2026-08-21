import json
from playwright.sync_api import sync_playwright
from helpers import login_owner

URL = "http://127.0.0.1:8088/"
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="networkidle")
    login_owner(pg, URL)
    out["titulo"] = pg.title()

    # overflow horizontal?
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # HOY: sesiones A/B visibles + rotación
    out["sesA"] = pg.evaluate("getComputedStyle(document.getElementById('sesA')).display")
    out["sesB"] = pg.evaluate("getComputedStyle(document.getElementById('sesB')).display")
    out["sesFull"] = pg.evaluate("getComputedStyle(document.getElementById('sesFull')).display")
    out["rot_opts"] = pg.eval_on_selector_all("#ovRue option", "els => els.length")

    # nav completo visible?
    out["nav_btns"] = pg.eval_on_selector_all("nav button", "els => els.length")

    # tab LIBROS
    pg.click("nav button[data-view='libros']")
    pg.wait_for_timeout(300)
    out["libros_comprables"] = pg.eval_on_selector_all("#bookList .book", "els => els.length")

    # filtro funciona en mobile
    pg.fill("#bookFilter", "fce")
    pg.wait_for_timeout(200)
    out["filtro_fce"] = pg.eval_on_selector_all("#bookList .book", "els => els.length")
    pg.fill("#bookFilter", "")

    # PROGRESO: export/import presentes + gates
    pg.click("nav button[data-view='prog']")
    pg.wait_for_timeout(200)
    out["gates"] = pg.eval_on_selector_all(".gate", "els => els.length")
    out["export_btn"] = pg.evaluate("typeof exportData === 'function'")

    # rubric checkboxes existen en el DOM (la Sesion A es la tarea 2 del HOY)
    out["rubric_items"] = pg.eval_on_selector_all(".rub", "els => els.length")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
