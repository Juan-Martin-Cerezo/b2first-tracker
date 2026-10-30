"""Hardening tests (fase 11): id validation, concurrent writes, security headers,
request-id logging, /api/health, versioned progress migration, error containment
and the owner password-reset tool.

Boots its own server with a temporary DATA_DIR, so nothing touches the real data/.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S  # noqa: E402
import store  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_tmp = tempfile.mkdtemp(prefix="b2hard-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
os.environ["B2_DEMO"] = "0"
os.environ["B2_REGISTER"] = "open"
S.B2_DEMO = False
S.B2_REGISTER = "open"
S.B2_PUBLIC_HEALTH = False

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
S.PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{S.PORT}"

out = {}
failed = []


def check(name, cond, detail=""):
    if cond:
        out[name] = {"assert": f"OK {name}"}
    else:
        out[name] = {"assert": f"FALLO {name}" + (f" -- {detail}" if detail else "")}
        failed.append(name)


def req(method, path, body=None, token=None, headers=None, raw=None):
    """HTTP helper: returns (status, body_text, response_headers)."""
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    hdrs = {}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = "Bearer " + token
    if headers:
        hdrs.update(headers)
    r = urllib.request.Request(URL + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def register(name, password):
    S._AI_RATE.clear()  # keep the test independent of the per-IP signup limit
    st, body, _ = req("POST", "/api/register", {"name": name, "password": password})
    assert st == 200, f"register {name} failed: {st} {body}"
    return json.loads(body)


def login(name, password):
    return req("POST", "/api/login", {"name": name, "password": password})


def safe_uid(raw):
    try:
        return store._safe_uid(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# A. Sanitized identifiers (path traversal)
# ---------------------------------------------------------------------------
ok_ids = ["owner", "user-2", "a.b", "Abc_123"]
bad_ids = ["../../etc/passwd", "..%2f..%2froot", "a/b", "a\\b", "..", "a..b"]
bad_ids_2 = [".hidden", "", "x" * 200, "x" * 65, "user name", "user\x00", None, 123]

check("A1_safe_uid_accepts_valid",
      all(safe_uid(i) == i for i in ok_ids),
      f"{[(i, safe_uid(i)) for i in ok_ids]}")
check("A2_safe_uid_rejects_traversal",
      all(safe_uid(i) is None for i in bad_ids),
      f"{[(i, safe_uid(i)) for i in bad_ids]}")
check("A3_safe_uid_rejects_dots_empty_long",
      all(safe_uid(i) is None for i in bad_ids_2),
      f"{[(i, safe_uid(i)) for i in bad_ids_2]}")

http_bad = ["../../etc/passwd", "..%2f..%2froot", ".hidden", "", "x" * 200]
codes = {}
for payload in http_bad:
    st_g, body_g, _ = req("GET", "/api/progress?user=" + payload)
    st_p, body_p, _ = req("PUT", "/api/progress?user=" + payload,
                          raw=b'{"log": [], "errs": []}')
    codes[payload] = (st_g, st_p, body_g, body_p)
check("A4_http_400_invalid_user",
      all(g == 400 and p == 400 and "invalid user id" in bg and "invalid user id" in bp
          for g, p, bg, bp in codes.values()),
      f"{codes}")

cands = [
    os.path.normpath(os.path.join(_tmp, "users", "../../etc/passwd")),
    os.path.normpath(os.path.join(_tmp, "users", "../../root")),
    os.path.join(_tmp, "users", ".hidden"),
    os.path.join(_tmp, "users", "x" * 200),
    os.path.join(_tmp, "users", "a..b"),
]
check("A5_no_files_outside_users",
      not any(os.path.exists(p) for p in cands),
      f"{[p for p in cands if os.path.exists(p)]}")

# ---------------------------------------------------------------------------
# C. Security headers + closed CORS
# ---------------------------------------------------------------------------
SEC = ["X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy",
       "Permissions-Policy", "Content-Security-Policy", "X-Request-Id"]
st_root, body_root, h_root = req("GET", "/")
check("C1_security_headers_root",
      st_root == 200 and all(k in h_root for k in SEC)
      and h_root.get("X-Content-Type-Options") == "nosniff"
      and h_root.get("X-Frame-Options") == "DENY"
      and h_root.get("Referrer-Policy") == "no-referrer"
      and "camera=()" in h_root.get("Permissions-Policy", "")
      and "frame-ancestors 'none'" in h_root.get("Content-Security-Policy", "")
      and "Access-Control-Allow-Origin" not in h_root,
      f"{h_root}")
st_cfg, _, h_cfg = req("GET", "/api/config")
check("C2_security_headers_api_config",
      st_cfg == 200 and all(k in h_cfg for k in SEC)
      and h_cfg.get("Cache-Control") == "no-store"
      and "Access-Control-Allow-Origin" not in h_cfg
      and "Cache-Control" not in h_root,
      f"{h_cfg}")
st_opt, _, h_opt = req("OPTIONS", "/api/progress")
check("C3_options_no_cors",
      st_opt in (200, 204) and not any(k.lower().startswith("access-control") for k in h_opt),
      f"{st_opt} {h_opt}")
check("C4_csp_allows_inline_js",
      "script-src 'self' 'unsafe-inline'" in h_root.get("Content-Security-Policy", "")
      and "<script" in body_root,
      f"csp={h_root.get('Content-Security-Policy', '')}")

# ---------------------------------------------------------------------------
# B. Concurrent writes (20 PUTs, same user)
# ---------------------------------------------------------------------------
u_b = register("hard-conc", "correct-horse-9")
tok_b, uid_b = u_b["token"], u_b["id"]

put_codes = []

def one_put(i):
    st, _b, _h = req("PUT", f"/api/progress?user={uid_b}", token=tok_b,
                     raw=json.dumps({"log": [{"type": "ue", "part": i}], "errs": [], "stage": 1}).encode())
    put_codes.append(st)

threads = [threading.Thread(target=one_put, args=(i,)) for i in range(20)]
for t in threads:
    t.start()
for t in threads:
    t.join()

check("B1_concurrent_puts_200", put_codes.count(200) == 20, f"{sorted(set(put_codes))}")

prog_path = os.path.join(_tmp, "users", uid_b, "progress.json")
try:
    with open(prog_path, encoding="utf-8") as f:
        json.load(f)
    prog_ok = True
except (OSError, ValueError) as exc:
    prog_ok = False
    prog_err = str(exc)
check("B2_progress_json_valid", prog_ok, locals().get("prog_err", ""))
try:
    with open(os.path.join(_tmp, "users.json"), encoding="utf-8") as f:
        json.load(f)
    users_ok = True
except (OSError, ValueError) as exc:
    users_ok = False
    users_err = str(exc)
check("B3_users_json_valid", users_ok, locals().get("users_err", ""))

tmps = []
for dirpath, _dirs, files in os.walk(_tmp):
    tmps += [os.path.join(dirpath, fn) for fn in files if fn.endswith(".tmp")]
check("B4_no_tmp_orphans", not tmps, f"{tmps}")

# ---------------------------------------------------------------------------
# D. Request-id logs without secrets
# ---------------------------------------------------------------------------
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    st_d1, _, h_d1 = req("GET", "/api/config")
    st_d2, _, h_d2 = req("GET", f"/api/progress?download=1&user={uid_b}", token=tok_b)
    st_d3, _, h_d3 = req("PUT", f"/api/progress?user={uid_b}",
                         raw=b'{"log": [], "errs": []}', token=tok_b)
    time.sleep(0.3)
log_lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
log_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z rid=[0-9a-f]{8} "
                    r"(GET|POST|PUT|DELETE|HEAD|OPTIONS) /\S* \d{3} \d+ms ip=\S+$")
check("D1_log_lines_rid_format",
      st_d1 == 200 and st_d2 == 200 and st_d3 == 200
      and len(log_lines) == 3 and all(log_re.match(ln) for ln in log_lines),
      f"{log_lines}")
log_text = "\n".join(log_lines)
check("D2_no_token_in_logs", tok_b not in log_text and "Bearer" not in log_text
      and "password" not in log_text.lower(),
      f"{log_text}")
rids = [h_d1.get("X-Request-Id", ""), h_d2.get("X-Request-Id", ""), h_d3.get("X-Request-Id", "")]
check("D3_request_ids_distinct",
      all(re.fullmatch(r"[0-9a-f]{8}", r) for r in rids)
      and len(set(rids)) == 3 and all(f"rid={r}" in log_text for r in rids),
      f"{rids}")

# ---------------------------------------------------------------------------
# E. /api/health
# ---------------------------------------------------------------------------
st_h, body_h, _ = req("GET", "/api/health")
hj = json.loads(body_h)
check("E1_health_ok",
      st_h == 200 and hj.get("ok") is True and isinstance(hj.get("users"), int)
      and hj.get("version") == "1.0.0" and isinstance(hj.get("uptime_s"), int)
      and hj.get("uptime_s", -1) >= 0 and "/" not in str(hj.get("data_dir", "/")),
      f"{st_h} {hj}")
S.B2_PUBLIC_HEALTH = True
st_h2, body_h2, _ = req("GET", "/api/health")
S.B2_PUBLIC_HEALTH = False
hj2 = json.loads(body_h2)
check("E2_health_public_path",
      st_h2 == 200 and hj2.get("data_dir") == _tmp, f"{st_h2} {hj2}")
os.chmod(_tmp, 0o500)
st_h3, body_h3, _ = req("GET", "/api/health")
os.chmod(_tmp, 0o700)
hj3 = json.loads(body_h3)
check("E3_health_readonly_503",
      st_h3 == 503 and hj3.get("ok") is False and hj3.get("check") == "data_dir",
      f"{st_h3} {hj3}")

# ---------------------------------------------------------------------------
# F. Versioned progress migration (v1 -> PROGRESS_SCHEMA)
# ---------------------------------------------------------------------------
u_f = register("hard-f", "correct-horse-9")
uid_f, tok_f = u_f["id"], u_f["token"]
v1 = {"log": [{"date": "2026-01-01", "type": "ue"}], "errs": [], "stage": 1,
      "future_field": "keep-me", "settings": {"planMin": 25}}
store._write_json(store._prog_file(uid_f), v1)

st_m, body_m, _ = req("GET", f"/api/progress?download=1&user={uid_f}", token=tok_f)
m1 = json.loads(body_m)
check("F1_migration_to_v2",
      st_m == 200 and m1.get("schema_version") == store.PROGRESS_SCHEMA
      and m1.get("profile") is None and m1.get("onboarded") is False
      and m1.get("settings", {}).get("__v") == 2,
      f"{st_m} {m1}")
check("F2_migration_preserves_unknown",
      m1.get("future_field") == "keep-me" and m1.get("settings", {}).get("planMin") == 25
      and m1.get("log", [{}])[0].get("type") == "ue",
      f"{m1}")
bk_f = os.path.join(_tmp, "users", uid_f, "backups")
pre = sorted(f for f in os.listdir(bk_f) if f.startswith("pre-migration-"))
pre_ok = False
if len(pre) == 1:
    with open(os.path.join(bk_f, pre[0]), encoding="utf-8") as f:
        pre_ok = json.load(f) == v1
check("F3_migration_backup_original", pre_ok, f"{pre}")

st_m2, body_m2, _ = req("GET", f"/api/progress?download=1&user={uid_f}", token=tok_f)
m2 = json.loads(body_m2)
pre2 = [f for f in os.listdir(bk_f) if f.startswith("pre-migration-")]
check("F4_migration_idempotent",
      st_m2 == 200 and m2.get("schema_version") == store.PROGRESS_SCHEMA
      and len(pre2) == 1 and m2 == m1,
      f"{st_m2} {pre2}")

# ---------------------------------------------------------------------------
# G. Errors never 500 by saturation
# ---------------------------------------------------------------------------
orig_portal = S.portal


def _boom():
    raise RuntimeError("forced failure")


S.portal = _boom
st_g1, body_g1, h_g1 = req("GET", "/libros")
S.portal = orig_portal
try:
    g1_obj = json.loads(body_g1)
except ValueError:
    g1_obj = {}
check("G1_unexpected_500_with_rid",
      st_g1 == 500 and g1_obj.get("error") == "internal"
      and g1_obj.get("rid") == h_g1.get("X-Request-Id")
      and re.fullmatch(r"[0-9a-f]{8}", str(g1_obj.get("rid", ""))) is not None
      and "Traceback" not in body_g1,
      f"{st_g1} {body_g1}")

lock_b = store._prog_lock(uid_b)
lock_b.acquire()
old_timeout = store._LOCK_TIMEOUT
store._LOCK_TIMEOUT = 0.2
st_g2, body_g2, h_g2 = req("PUT", f"/api/progress?user={uid_b}",
                           raw=b'{"log": [], "errs": []}', token=tok_b)
store._LOCK_TIMEOUT = old_timeout
lock_b.release()
try:
    g2_obj = json.loads(body_g2)
except ValueError:
    g2_obj = {}
check("G2_busy_429_retry_after",
      st_g2 == 429 and g2_obj.get("error") == "busy" and g2_obj.get("retry_after") == 2
      and h_g2.get("Retry-After") == "2",
      f"{st_g2} {body_g2} {h_g2}")

# ---------------------------------------------------------------------------
# H. Owner password reset (tools/reset_password.py)
# ---------------------------------------------------------------------------
u_h = register("hard-reset", "oldpassword1")
uid_h, tok_old = u_h["id"], u_h["token"]
env = dict(os.environ)
env["DATA_DIR"] = _tmp
proc = subprocess.run(
    [sys.executable, os.path.join(REPO, "tools", "reset_password.py"), "hard-reset", "--generate"],
    capture_output=True, text=True, env=env, cwd=REPO,
)
new_pass = proc.stdout.strip()
rec_h = store.get_user(uid_h) or {}
check("H1_reset_password_cli",
      proc.returncode == 0 and len(new_pass) >= 8
      and rec_h.get("hash") not in proc.stdout and rec_h.get("algo") == "pbkdf2"
      and "hash" not in proc.stdout.lower(),
      f"rc={proc.returncode} out={proc.stdout!r} err={proc.stderr!r}")
st_new, body_new, _ = login("hard-reset", new_pass)
check("H2_login_new_password",
      st_new == 200 and json.loads(body_new).get("token"), f"{st_new} {body_new}")
st_old, body_old, _ = login("hard-reset", "oldpassword1")
check("H3_old_password_401", st_old == 401, f"{st_old} {body_old}")
st_me, body_me, _ = req("GET", "/api/me", token=tok_old)
check("H4_old_token_invalidated", st_me == 401, f"{st_me} {body_me}")

# ---------------------------------------------------------------------------
srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
print("HARDENING_EXIT", 1 if failed else 0)
sys.exit(1 if failed else 0)
