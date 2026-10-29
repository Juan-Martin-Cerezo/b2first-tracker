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

    # rotación: select de Writing + wTipo
    out["ovW_opts"] = pg.eval_on_selector_all("#ovW option", "els => els.length")
    out["wTipo_value"] = pg.input_value("#wTipo")
    out["semana_txt"] = pg.evaluate("document.getElementById('semanaTxt').textContent")

    # manual writing override: pick Report and save
    pg.select_option("#ovW", "Report")
    out["override_set"] = pg.evaluate("D.weekOverrides.w === 'Report'")
    out["wTipo_tras_override"] = pg.input_value("#wTipo")
    # limpiar override
    pg.evaluate("delete D.weekOverrides.w; save(); renderToday();")
    out["override_limpio"] = pg.evaluate("!D.weekOverrides.w")

    # stats: save state, load sample data with test flag and restore
    pg.evaluate("""const origLog = JSON.stringify(D.log);
                   window.__origLog = origLog;
                   D.log.push({date:'2026-08-16',type:'ue',part:5,correct:4,total:6,min:20,_test:true});
                   D.log.push({date:'2026-08-16',type:'ue',part:5,correct:5,total:6,min:19,_test:true});
                   D.log.push({date:'2026-08-16',type:'lp',part:2,correct:7,total:10,min:9,_test:true});
                   D.log.push({date:'2026-08-15',type:'w',kind:'Essay',score:15,min:30,_test:true});
                   D.log.push({date:'2026-08-15',type:'w',kind:'Essay',score:17,min:28,_test:true});
                   save(); refreshAll();""")
    pg.wait_for_timeout(300)
    out["stats_rows"] = pg.eval_on_selector_all("#statsTable tbody tr", "els => els.length")
    out["stats_ue_p5"] = pg.evaluate("(document.querySelector('#statsTable tbody tr')||{}).textContent")
    # restore test data exactly
    pg.evaluate("""D.log = JSON.parse(window.__origLog);
                   save(); refreshAll();""")

    # PLAN ciclos cargados
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(200)
    out["plan_rue_cycle"] = pg.input_value("#pRueCycle")
    out["plan_w_cycle"] = pg.input_value("#pWCycle")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
