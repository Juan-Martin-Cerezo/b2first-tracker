import json
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8088/"
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="networkidle")
    out["titulo"] = pg.title()

    # overflow horizontal?
    out["scroll_width"] = pg.evaluate("document.documentElement.scrollWidth")
    out["viewport_width"] = pg.evaluate("window.innerWidth")

    # HOY: sesion C visible siempre, simulacro oculto en etapa 0
    out["sesC_visible"] = pg.evaluate("document.getElementById('sesC').style.display")
    out["sesFull_etapa0"] = pg.evaluate("document.getElementById('sesFull').style.display")

    # nav completo visible?
    out["nav_btns"] = pg.eval_on_selector_all("nav button", "els => els.length")

    # tab LIBROS
    pg.click("nav button[data-view='libros']")
    pg.wait_for_timeout(300)
    out["libros_comprables"] = pg.eval_on_selector_all("#bookList .book", "els => els.length")
    out["sin_material"] = pg.eval_on_selector_all("#matList", "els => els.length") == 0

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

    # registrar una clase (Sesion C) desde HOY
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(200)
    pg.check("#cW"); pg.check("#cS"); pg.check("#cQ")
    pg.click("text=Registrar clase")
    pg.wait_for_timeout(200)
    out["log_tiene_clase"] = pg.evaluate("D.log.some(e => e.type === 'c')")

    # rubric checkboxes existen y cuentan (forzar visibilidad de Sesion A)
    pg.evaluate("document.getElementById('sesA').style.display='block'")
    pg.wait_for_timeout(200)
    out["rubric_items"] = pg.eval_on_selector_all(".rub", "els => els.length")
    pg.check(".rub >> nth=0")
    pg.wait_for_timeout(100)
    out["rubric_count_tras_tick"] = pg.evaluate("document.getElementById('rubCount').textContent")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
