import json, os, sys, tempfile, threading, urllib.request
import http.client

# Importar el server con data en un directorio temporal (no tocar la real)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S

_tmp = tempfile.mkdtemp(prefix="b2sync-")
S.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.PORT = 8099
# El server multi-usuario migra al primer arranque: crear el owner y su carpeta
if not os.path.exists(S.USERS_FILE):
    S.migrate_legacy()

srv = S.ThreadingHTTPServer(("127.0.0.1", S.PORT), S.H)
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()

URL = "http://127.0.0.1:8099"
out = {}


def get(path, token=None):
    req = urllib.request.Request(URL + path)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    return json.loads(urllib.request.urlopen(req).read().decode("utf-8"))


def put(path, body, token=None):
    conn = http.client.HTTPConnection("127.0.0.1", S.PORT)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    conn.request("PUT", path, body=json.dumps(body), headers=headers)
    r = conn.getresponse()
    return r.status, r.read().decode("utf-8")


# 0. Login del owner (contraseña por defecto de la migración)
tok = get("/api/login", None) if False else None
_req = urllib.request.Request(
    URL + "/api/login",
    data=json.dumps({"name": "Owner", "password": "b2first"}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(_req) as r:
    owner = json.loads(r.read().decode())
tok = owner["token"]
UID = owner["id"]

# 1. GET sin datos -> {}
out["get_vacio"] = get("/api/progress?download=1", tok)

# 2. PUT válido -> 200 "ok"
prog = {"log": [{"date": "2026-08-17", "type": "ue", "part": 1, "correct": 5, "total": 6}],
        "errs": [], "stage": 0}
out["put_ok"] = put("/api/progress?user=" + UID, prog, tok)[0]

# 3. GET devuelve lo guardado
out["get_tras_put"] = get("/api/progress?download=1&user=" + UID, tok)["log"][0]["type"]

# 4. Segundo PUT -> backup del anterior (data/users/<id>/backups/)
prog2 = {"log": [{"date": "2026-08-17", "type": "w", "kind": "Essay", "score": 16}],
         "errs": [], "stage": 1}
put("/api/progress?user=" + UID, prog2, tok)
bk_dir = os.path.join(_tmp, "users", UID, "backups")
out["backups"] = sorted(os.listdir(bk_dir))
out["prog_actual"] = get("/api/progress?download=1&user=" + UID, tok)["log"][0]["type"]

# 5. list_backups via GET
out["lista_backups"] = len(get("/api/progress?user=" + UID, tok))

# 6. PUT inválido -> 400
out["put_invalido"] = put("/api/progress?user=" + UID, "no-json", tok)[0]
out["put_sin_log"] = put("/api/progress?user=" + UID, {"foo": 1}, tok)[0]

srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
