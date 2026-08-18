import json, os, sys, tempfile, threading, urllib.request
import http.client

# Importar el server con data en un directorio temporal (no tocar la real)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S

_tmp = tempfile.mkdtemp(prefix="b2sync-")
S.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.PORT = 8099

srv = S.ThreadingHTTPServer(("127.0.0.1", S.PORT), S.H)
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()

URL = "http://127.0.0.1:8099"
out = {}

def get(path):
    return json.loads(urllib.request.urlopen(URL + path).read().decode("utf-8"))

def put(path, body):
    conn = http.client.HTTPConnection("127.0.0.1", S.PORT)
    conn.request("PUT", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
    r = conn.getresponse()
    return r.status, r.read().decode("utf-8")

# 1. GET sin datos -> {}
out["get_vacio"] = get("/api/progress?download=1")

# 2. PUT válido -> 200 "ok"
prog = {"log": [{"date": "2026-08-17", "type": "ue", "part": 1, "correct": 5, "total": 6}],
        "errs": [], "stage": 0}
out["put_ok"] = put("/api/progress", prog)[0]

# 3. GET devuelve lo guardado
out["get_tras_put"] = get("/api/progress?download=1")["log"][0]["type"]

# 4. Segundo PUT -> backup del anterior
prog2 = {"log": [{"date": "2026-08-17", "type": "w", "kind": "Essay", "score": 16}],
         "errs": [], "stage": 1}
put("/api/progress", prog2)
out["backups"] = sorted(os.listdir(S.BK_DIR))
out["prog_actual"] = get("/api/progress?download=1")["log"][0]["type"]

# 5. list_backups via GET
out["lista_backups"] = len(get("/api/progress"))

# 6. PUT inválido -> 400
out["put_invalido"] = put("/api/progress", "no-json")[0]
out["put_sin_log"] = put("/api/progress", {"foo": 1})[0]

srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
