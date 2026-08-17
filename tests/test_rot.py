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
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # rotación: selects llenos + uePart + wTipo
    out["ovRue_opts"] = pg.eval_on_selector_all("#ovRue option", "els => els.length")
    out["ovW_opts"] = pg.eval_on_selector_all("#ovW option", "els => els.length")
    out["uePart_value"] = pg.input_value("#uePart")
    out["wTipo_value"] = pg.input_value("#wTipo")
    out["semana_txt"] = pg.evaluate("document.getElementById('semanaTxt').textContent")
    out["lFocus"] = pg.evaluate("document.getElementById('lFocusNote').textContent.slice(0,40)")
    out["spFocus"] = pg.evaluate("document.getElementById('spFocusNote').textContent.slice(0,40)")

    # override manual: elegir UoE P1 y guardar
    pg.select_option("#ovRue", "1")
    out["override_set"] = pg.evaluate("D.weekOverrides.rue === 1")
    out["uePart_tras_override"] = pg.input_value("#uePart")
    # limpiar override
    pg.evaluate("delete D.weekOverrides.rue; save(); renderToday();")
    out["override_limpio"] = pg.evaluate("!D.weekOverrides.rue")

    # stats: cargar datos de ejemplo y ver tabla
    pg.evaluate("""D.log.push({date:'2026-08-16',type:'ue',part:5,correct:4,total:6,min:20});
                   D.log.push({date:'2026-08-16',type:'ue',part:5,correct:5,total:6,min:19});
                   D.log.push({date:'2026-08-16',type:'lp',part:2,correct:7,total:10,min:9});
                   D.log.push({date:'2026-08-15',type:'w',kind:'Essay',score:15,min:30});
                   D.log.push({date:'2026-08-15',type:'w',kind:'Essay',score:17,min:28});
                   save(); refreshAll();""")
    pg.wait_for_timeout(300)
    out["stats_rows"] = pg.eval_on_selector_all("#statsTable tbody tr", "els => els.length")
    out["stats_ue_p5"] = pg.evaluate("(document.querySelector('#statsTable tbody tr')||{}).textContent")
    # limpiar test data
    pg.evaluate("""D.log = D.log.filter(e => !(e.note === undefined && (e.part === 5 || (e.part === 2 && e.correct === 7) || (e.kind === 'Essay' && e.score === 15) || (e.kind === 'Essay' && e.score === 17))));
                   save(); refreshAll();""")

    # PLAN ciclos cargados
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(200)
    out["plan_rue_cycle"] = pg.input_value("#pRueCycle")
    out["plan_w_cycle"] = pg.input_value("#pWCycle")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
