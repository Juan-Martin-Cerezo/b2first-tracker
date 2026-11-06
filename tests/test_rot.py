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
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # rotación: the writing genres are product constants now
    out["ovW_opts"] = pg.evaluate("QUEUE_CYCLES.w.length")
    out["wTipo_value"] = pg.input_value("#wTipo")
    out["semana_txt"] = pg.evaluate("document.getElementById('semanaTxt').textContent")

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

    # PLAN ciclos: constants, no editable inputs
    out["plan_rue_cycle"] = pg.evaluate("QUEUE_CYCLES.rue.join(',')")
    out["plan_w_cycle"] = pg.evaluate("QUEUE_CYCLES.w.join(',')")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
