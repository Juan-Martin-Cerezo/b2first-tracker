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
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # HOY: todas las sesiones visibles + rotación
    out["sesA"] = pg.evaluate("getComputedStyle(document.getElementById('sesA')).display")
    out["sesB"] = pg.evaluate("getComputedStyle(document.getElementById('sesB')).display")
    out["sesFull"] = pg.evaluate("getComputedStyle(document.getElementById('sesFull')).display")
    out["rot_opts"] = pg.eval_on_selector_all("#ovRue option", "els => els.length")
    out["nextBox"] = pg.evaluate("document.getElementById('nextBox').textContent.slice(0,70)")

    # LIBROS: material + libros
    pg.click("nav button[data-view='libros']")
    pg.wait_for_timeout(800)
    out["material_cards"] = pg.eval_on_selector_all("#matList .book", "els => els.length")
    out["audio_players"] = pg.eval_on_selector_all("#matList audio", "els => els.length")
    out["libros_comprables"] = pg.eval_on_selector_all("#bookList .book", "els => els.length")

    # EXAMEN: timer con tiempo real
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(200)
    out["ex_timer"] = pg.evaluate("document.getElementById('exTimer').textContent")

    # PARTES: 15 ejercicios
    pg.click("nav button[data-view='partes']")
    pg.wait_for_timeout(200)
    out["partes"] = pg.eval_on_selector_all("#partsList .step", "els => els.length")

    # PROGRESO: gates + stats + export
    pg.click("nav button[data-view='prog']")
    pg.wait_for_timeout(200)
    out["gates"] = pg.eval_on_selector_all(".gate", "els => els.length")
    out["export_ok"] = pg.evaluate("typeof exportData === 'function'")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
