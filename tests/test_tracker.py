import json, sys
from playwright.sync_api import sync_playwright
from helpers import login_owner

URL = "http://127.0.0.1:8088/"
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="networkidle")
    login_owner(pg, URL)
    out["titulo"] = pg.title()
    # ir a LIBROS
    pg.click("nav button[data-view='libros']")
    pg.wait_for_timeout(800)
    # material (fetch /libros.json -> render)
    out["material_cards"] = pg.eval_on_selector_all("#matList .book", "els => els.length")
    out["material_groups"] = pg.eval_on_selector_all("#matList .folder", "els => els.length")
    out["libros_comprables"] = pg.eval_on_selector_all("#bookList .book", "els => els.length")
    # filtro de libros
    pg.fill("#bookFilter", "grammar")
    pg.wait_for_timeout(200)
    out["filtro_grammar"] = pg.eval_on_selector_all("#bookList .book", "els => els.length")
    pg.fill("#bookFilter", "")
    pg.wait_for_timeout(200)
    # primer libro: link?
    out["primer_link"] = pg.eval_on_selector("#bookList .book a", "a => a ? a.href.slice(0,60) : null")
    # primer pdf material: href?
    out["primer_pdf"] = pg.eval_on_selector("#matList .book a[target='_blank']", "a => a ? a.href.slice(0,70) : null")
    # audio player?
    out["audio_players"] = pg.eval_on_selector_all("#matList audio", "els => els.length")
    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
