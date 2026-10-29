import json, os, sys, tempfile, threading
from playwright.sync_api import sync_playwright
from helpers import login_owner

# Spin up a test server with temporary data (same technique as test_sync.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S

_tmp = tempfile.mkdtemp(prefix="b2graf-")
S.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
# Ephemeral port: a fixed one may be taken by a stale process
S.PORT = 0

srv = S.ThreadingHTTPServer(("127.0.0.1", S.PORT), S.H)
S.PORT = srv.server_address[1]
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()

URL = f"http://127.0.0.1:{S.PORT}/"
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="networkidle")
    login_owner(pg, URL)

    # CHARTS tab exists in the nav
    out["nav_graf"] = pg.eval_on_selector_all("nav button[data-view='graf']", "els => els.length")

    # no data: empty messages (CHARTS is behind "More" in the mobile nav)
    pg.click("#navMoreBtn")
    pg.wait_for_timeout(80)
    pg.click("nav button[data-view='graf']")
    pg.wait_for_timeout(200)
    out["evol_vacio"] = "Log Writing" in pg.evaluate("document.getElementById('gEvol').textContent")
    out["part_vacio"] = "No data yet" in pg.evaluate("document.getElementById('gPart').textContent")
    out["err_vacio"] = "No errors logged" in pg.evaluate("document.getElementById('gErr').textContent")
    out["cons_vacio"] = "No logs yet" in pg.evaluate("document.getElementById('gCons').textContent")

    # with data: the 4 panels render
    pg.evaluate("""D.log.push({date:'2026-08-15',type:'w',kind:'Essay',score:15,min:30});
                   D.log.push({date:'2026-08-16',type:'w',kind:'Essay',score:17,min:28});
                   D.log.push({date:'2026-08-16',type:'l',correct:24,total:30,min:30});
                   D.log.push({date:'2026-08-16',type:'lp',part:2,correct:7,total:10,min:9});
                   D.log.push({date:'2026-08-16',type:'ue',part:5,correct:4,total:6,min:20});
                   D.errs.push({date:'2026-08-16',code:'L-GAP',desc:'missing connector'});
                   D.errs.push({date:'2026-08-16',code:'T-MIS',desc:'date distractor'});
                   save(); refreshAll();""")
    pg.wait_for_timeout(300)
    out["evol_svg"] = pg.eval_on_selector_all("#gEvol svg", "els => els.length")
    out["part_svg"] = pg.eval_on_selector_all("#gPart [style*='flex']", "els => els.length")
    out["err_svg"] = pg.eval_on_selector_all("#gErr svg", "els => els.length")
    out["cons_svg"] = pg.eval_on_selector_all("#gCons svg", "els => els.length")
    out["streak"] = pg.evaluate("document.getElementById('gStreak').textContent")
    out["bars_ue"] = pg.evaluate("[...document.querySelectorAll('#gPart span')].filter(s=>s.textContent.includes('UoE P5')).length")

    # no overflow on mobile with the charts
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # clean up test data
    pg.evaluate("""D.log=[]; D.errs=[]; D.stage=0; save(); refreshAll();""")
    out["errores_js"] = errs
    b.close()
srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
