import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright

os.environ["B2_DEMO"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S
import store

_tmp = tempfile.mkdtemp(prefix="b2demo-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.B2_DEMO = True

srv1 = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
port1 = srv1.server_address[1]
S.PORT = port1
th1 = threading.Thread(target=srv1.serve_forever, daemon=True)
th1.start()
URL1 = f"http://127.0.0.1:{port1}"


def req_http(base, method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    r = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


out = {}

# 1. /api/config -> 200 y demo===true
st_cfg, body_cfg = req_http(URL1, "GET", "/api/config")
cfg_json = json.loads(body_cfg)
assert st_cfg == 200 and cfg_json.get("demo") is True and cfg_json.get("version") == "1.0.0" and cfg_json.get("ai") is True
out["1_config_demo"] = cfg_json["demo"]

# 2. /api/register POST -> 403
st_reg, body_reg = req_http(URL1, "POST", "/api/register", {"name": "test", "password": "password123"})
assert st_reg == 403 and "modo demo" in json.loads(body_reg).get("error", "")
out["2_register_403"] = st_reg

# 3. /api/login POST -> 403
st_log, body_log = req_http(URL1, "POST", "/api/login", {"name": "Owner", "password": "b2first"})
assert st_log == 403 and "modo demo" in json.loads(body_log).get("error", "")
out["3_login_403"] = st_log

# 4. /api/progress PUT -> 403
st_put, body_put = req_http(URL1, "PUT", "/api/progress", {"log": [], "errs": []})
assert st_put == 403 and "modo demo" in json.loads(body_put).get("error", "")
out["4_progress_put_403"] = st_put

# 5. /api/progress GET -> 403 (y también /api/logout, /api/me, /api/users)
st_get, body_get = req_http(URL1, "GET", "/api/progress?download=1")
st_out, _ = req_http(URL1, "POST", "/api/logout", {"token": "x"})
st_me, _ = req_http(URL1, "GET", "/api/me")
st_usr, _ = req_http(URL1, "GET", "/api/users")
assert st_get == 403 and st_out == 403 and st_me == 403 and st_usr == 403
out["5_progress_get_403"] = st_get

# 6. GET / -> 200 y el HTML contiene la banda de demo (Modo demo)
st_idx, body_idx = req_http(URL1, "GET", "/")
assert st_idx == 200 and "Modo demo" in body_idx
out["6_index_has_demo_banner"] = "Modo demo" in body_idx

# 7. /diagnostico.json -> 200 con 12 items
st_diag, body_diag = req_http(URL1, "GET", "/diagnostico.json")
diag_items = json.loads(body_diag).get("items", [])
assert st_diag == 200 and len(diag_items) == 12
out["7_diagnostico_items"] = len(diag_items)

# 9. errores_js: [] cargando la app en modo demo con Playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errores_js = []
    pg.on("pageerror", lambda e: errores_js.append(str(e)))
    pg.goto(URL1 + "/", wait_until="networkidle")
    demo_state = pg.evaluate(
        """() => ({
        demo: window.DEMO && window.DEMO.demo === true,
        bannerVisible: getComputedStyle(document.getElementById('demoBanner')).display !== 'none',
        bannerText: document.getElementById('demoBanner').textContent.trim(),
        authHidden: getComputedStyle(document.getElementById('authOverlay')).display === 'none',
        footSyncHidden: getComputedStyle(document.getElementById('syncBadgeFoot')).display === 'none'
    })"""
    )
    assert demo_state["demo"] is True, f"Expected DEMO.demo===true, got {demo_state}"
    assert demo_state["bannerVisible"] is True and "Modo demo" in demo_state["bannerText"]
    assert demo_state["authHidden"] is True and demo_state["footSyncHidden"] is True
    assert errores_js == [], f"JS errors in demo mode: {errores_js}"
    b.close()

srv1.shutdown()

# 8. con B2_DEMO=0 (segundo arranque): /api/config -> demo===false y /api/register con datos inválidos -> 400 (no 403)
os.environ["B2_DEMO"] = "0"
S.B2_DEMO = False
srv2 = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
port2 = srv2.server_address[1]
S.PORT = port2
th2 = threading.Thread(target=srv2.serve_forever, daemon=True)
th2.start()
URL2 = f"http://127.0.0.1:{port2}"

st_cfg0, body_cfg0 = req_http(URL2, "GET", "/api/config")
cfg0_json = json.loads(body_cfg0)
st_reg0, _ = req_http(URL2, "POST", "/api/register", {"name": "", "password": "123"})
assert st_cfg0 == 200 and cfg0_json.get("demo") is False, f"Expected demo=False, got {cfg0_json}"
assert st_reg0 == 400, f"Expected 400 on invalid register in non-demo mode, got {st_reg0}"
out["8_nodemo_config_and_reg400"] = f"demo={cfg0_json['demo']},register={st_reg0}"
out["errores_js"] = errores_js

srv2.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
