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
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # EXAMEN tab
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(300)
    out["ex_timer"] = pg.evaluate("document.getElementById('exTimer').textContent")
    out["ex_guide_len"] = pg.evaluate("document.getElementById('exGuide').innerText.length")
    out["ex_links"] = pg.eval_on_selector_all("#exGuide a", "els => els.length")
    # cambiar a Writing
    pg.select_option("#exPaper", "w")
    pg.wait_for_timeout(200)
    out["ex_w_timer"] = pg.evaluate("document.getElementById('exTimer').textContent")
    out["ex_w_links"] = pg.eval_on_selector_all("#exGuide a", "els => els.length")
    # start timer y verificar cuenta regresiva
    pg.click("button[onclick='exStart()']")
    pg.wait_for_timeout(2100)
    out["ex_corriendo"] = pg.evaluate("exIv !== null")
    out["ex_timer_tras2s"] = pg.evaluate("document.getElementById('exTimer').textContent")
    pg.evaluate("document.querySelector(\"button[onclick='exPause()']\").click()")
    out["ex_pausado"] = pg.evaluate("exIv === null")
    pg.evaluate("exLeft = 590; exTick()")  # simular <10min -> rojo
    out["ex_color_warn"] = pg.evaluate("document.getElementById('exTimer').style.color")

    # PARTES tab
    pg.click("nav button[data-view='partes']")
    pg.wait_for_timeout(300)
    out["partes_total"] = pg.eval_on_selector_all("#partsList .step", "els => els.length")
    out["partes_grupos"] = pg.eval_on_selector_all("#partsList .folder", "els => els.length")
    # registrar un part UoE P5
    pg.evaluate("savePart(4)")  # index 4 = R&UoE Part 5
    out["log_ue_p5"] = pg.evaluate("D.log.some(e => e.type==='ue' && e.part===5)")
    out["log_modo"] = pg.evaluate("(D.log.find(e => e.type==='ue' && e.part===5)||{}).note")
    # limpiar test
    pg.evaluate("D.log = D.log.filter(e => !(e.type==='ue' && e.part===5 && e.note==='Multiple choice (2 textos)')); save(); refreshAll();")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
