import json, os, sys, tempfile, threading, urllib.request
import http.client

# Import the server with data in a temporary directory (never touch the real one)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S

_tmp = tempfile.mkdtemp(prefix="b2sync-")
S.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
# Ephemeral port: a fixed one (8099) may be taken by a stale process
S.PORT = 0
# The multi-user server migrates on first boot: create the owner and its folder
if not os.path.exists(S.USERS_FILE):
    S.migrate_legacy()

srv = S.ThreadingHTTPServer(("127.0.0.1", S.PORT), S.H)
S.PORT = srv.server_address[1]
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()

URL = f"http://127.0.0.1:{S.PORT}"
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


# 0. Owner login (default password from the migration)
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

# 1. GET with no data -> {}
out["get_vacio"] = get("/api/progress?download=1", tok)

# 2. Valid PUT -> 200 "ok"
prog = {"log": [{"date": "2026-08-17", "type": "ue", "part": 1, "correct": 5, "total": 6}],
        "errs": [], "stage": 0}
out["put_ok"] = put("/api/progress?user=" + UID, prog, tok)[0]

# 3. GET returns what was saved
out["get_tras_put"] = get("/api/progress?download=1&user=" + UID, tok)["log"][0]["type"]

# 4. Second PUT -> backup of the previous one (data/users/<id>/backups/)
prog2 = {"log": [{"date": "2026-08-17", "type": "w", "kind": "Essay", "score": 16}],
         "errs": [], "stage": 1}
put("/api/progress?user=" + UID, prog2, tok)
bk_dir = os.path.join(_tmp, "users", UID, "backups")
out["backups"] = sorted(os.listdir(bk_dir))
out["prog_actual"] = get("/api/progress?download=1&user=" + UID, tok)["log"][0]["type"]

# 5. list_backups via GET
out["lista_backups"] = len(get("/api/progress?user=" + UID, tok))

# 6. Invalid PUT -> 400
out["put_invalido"] = put("/api/progress?user=" + UID, "no-json", tok)[0]
out["put_sin_log"] = put("/api/progress?user=" + UID, {"foo": 1}, tok)[0]

srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
