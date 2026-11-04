import json, sys
from playwright.sync_api import sync_playwright
from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    out["titulo"] = pg.title()
    # ir a PRACTICE (Books merged into it)
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(800)
    # online practice (static list) + material (fetch /libros.json -> render)
    out["online_cards"] = pg.eval_on_selector_all("#onlineList .book", "els => els.length")
    out["material_cards"] = pg.eval_on_selector_all("#matList .book", "els => els.length")
    out["material_groups"] = pg.eval_on_selector_all("#matList .folder", "els => els.length")
    # filtro de material
    pg.fill("#matFilter", "grammar")
    pg.wait_for_timeout(200)
    out["filtro_grammar"] = pg.eval_on_selector_all("#matList .book", "els => els.length")
    pg.fill("#matFilter", "")
    pg.wait_for_timeout(200)
    # primer enlace online
    out["primer_link"] = pg.eval_on_selector("#onlineList .book a", "a => a ? a.href.slice(0,60) : null")
    # primer pdf material: href?
    out["primer_pdf"] = pg.eval_on_selector("#matList .book a[target='_blank']", "a => a ? a.href.slice(0,70) : null")
    # audio player?
    out["audio_players"] = pg.eval_on_selector_all("#matList audio", "els => els.length")
    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
