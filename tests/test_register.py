import json, os, sys, tempfile, threading, urllib.request, urllib.error

os.environ["B2_DEMO"] = "0"
os.environ["B2_REGISTER"] = "closed"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S
import store

_tmp = tempfile.mkdtemp(prefix="b2reg-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.B2_DEMO = False
S.B2_REGISTER = "closed"

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
S.PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{S.PORT}"

out = {}


def req(base, method, path, body=None, token=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


# 1. /api/config -> register==="closed" and demo===false
st_cfg, body_cfg = req(URL, "GET", "/api/config")
cfg = json.loads(body_cfg)
assert st_cfg == 200 and cfg.get("register") == "closed" and cfg.get("demo") is False, f"bad config: {cfg}"
out["1_config_register_closed"] = {"register": cfg["register"], "demo": cfg["demo"]}

# 2. POST /api/register -> 403 {"error": "registration is closed"}
st_reg, body_reg = req(URL, "POST", "/api/register", {"name": "mallory", "password": "password123"})
assert st_reg == 403 and json.loads(body_reg).get("error") == "registration is closed", f"bad register: {st_reg} {body_reg}"
out["2_register_403"] = st_reg

# 3. user created via the internal API (the route is closed) -> POST /api/login -> 200 + token
uid, err = S.register_user("alice", "password123")
assert uid and err is None, f"internal register failed: {uid} {err}"
st_log, body_log = req(URL, "POST", "/api/login", {"name": "alice", "password": "password123"})
login1 = json.loads(body_log)
assert st_log == 200 and login1.get("token"), f"login failed: {st_log} {body_log}"
tok1 = login1["token"]
st_log2, body_log2 = req(URL, "POST", "/api/login", {"name": "alice", "password": "password123"})
tok2 = json.loads(body_log2)["token"]
out["3_login_200"] = st_log

# 4. GET /api/progress with the token -> 200
st_get, body_get = req(URL, "GET", f"/api/progress?download=1&user={uid}", token=tok1)
assert st_get == 200, f"progress GET failed: {st_get} {body_get}"
out["4_progress_get_200"] = st_get

# 5. PUT /api/progress with the token -> 200 and the file in DATA_DIR changes
prog_file = os.path.join(_tmp, "users", uid, "progress.json")
before = open(prog_file, encoding="utf-8").read() if os.path.exists(prog_file) else None
prog = {"log": [{"date": "2026-10-29", "type": "ue", "part": 1, "correct": 5, "total": 6}], "errs": [], "stage": 0}
st_put, body_put = req(URL, "PUT", f"/api/progress?user={uid}", prog, token=tok1)
after = open(prog_file, encoding="utf-8").read() if os.path.exists(prog_file) else None
assert st_put == 200, f"progress PUT failed: {st_put} {body_put}"
assert after is not None and after != before and json.loads(after)["log"][0]["type"] == "ue", "progress file did not change"
out["5_progress_put_200_and_file_changed"] = st_put

# 6. POST /api/password with wrong current -> 401
st_pw, body_pw = req(URL, "POST", "/api/password", {"current": "wrong-pass", "next": "newpassword123"}, token=tok1)
assert st_pw == 401, f"expected 401 for wrong current, got {st_pw} {body_pw}"
out["6_password_wrong_current_401"] = st_pw

# 7. POST /api/password with next of 5 chars -> 400
st_pw2, body_pw2 = req(URL, "POST", "/api/password", {"current": "password123", "next": "short"}, token=tok1)
assert st_pw2 == 400, f"expected 400 for short next, got {st_pw2} {body_pw2}"
out["7_password_short_next_400"] = st_pw2

# 8. successful change -> 200, old login 401, new login 200, other token invalidated
st_chg, body_chg = req(URL, "POST", "/api/password", {"current": "password123", "next": "newpassword123"}, token=tok2)
assert st_chg == 200 and json.loads(body_chg).get("ok") is True, f"password change failed: {st_chg} {body_chg}"
st_old, _ = req(URL, "POST", "/api/login", {"name": "alice", "password": "password123"})
st_new, body_new = req(URL, "POST", "/api/login", {"name": "alice", "password": "newpassword123"})
assert st_old == 401 and st_new == 200, f"old={st_old} new={st_new}"
fresh = json.loads(body_chg).get("token", "")
st_me_other, _ = req(URL, "GET", "/api/me", token=tok1)
st_me_current, _ = req(URL, "GET", "/api/me", token=tok2)
st_me_fresh, _ = req(URL, "GET", "/api/me", token=fresh)
assert st_me_other == 401, f"other token still valid: {st_me_other}"
assert st_me_current == 401, f"current token survived the change: {st_me_current}"
assert st_me_fresh == 200, f"fresh token invalid: {st_me_fresh}"
out["8_password_change"] = {"change": st_chg, "old_login": st_old, "new_login": st_new,
                            "other_token": st_me_other, "current_token": st_me_current,
                            "fresh_token": st_me_fresh}

srv.shutdown()

# 9. second boot with B2_REGISTER=open: /api/config -> "open" and register accepts a valid signup
S.B2_REGISTER = "open"
srv2 = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
S.PORT = srv2.server_address[1]
threading.Thread(target=srv2.serve_forever, daemon=True).start()
URL2 = f"http://127.0.0.1:{S.PORT}"

st_cfg2, body_cfg2 = req(URL2, "GET", "/api/config")
cfg2 = json.loads(body_cfg2)
assert st_cfg2 == 200 and cfg2.get("register") == "open", f"bad open config: {cfg2}"
st_reg2, body_reg2 = req(URL2, "POST", "/api/register", {"name": "bob", "password": "correct-horse-9"})
reg2 = json.loads(body_reg2)
assert st_reg2 == 200 and reg2.get("token"), f"open register failed: {st_reg2} {body_reg2}"
out["9_register_open"] = {"register": cfg2["register"], "signup": st_reg2}

srv2.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
