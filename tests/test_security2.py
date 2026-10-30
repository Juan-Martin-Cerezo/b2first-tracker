"""Security round 2 tests (fase 12): brute-force lockout per username, constant-time
auth paths, hashed tokens at rest (with legacy migration), progress payload schema,
global per-IP limit and the auth audit log.

Boots its own server with a temporary DATA_DIR, so nothing touches the real data/.
"""
import hashlib
import json
import os
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2sec2-")
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

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
S.PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{S.PORT}"

AUDIT_PATH = os.path.join(_tmp, "audit.log")
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
    S._RATE.clear()  # keep the test independent of the per-IP signup limit
    st, body, _ = req("POST", "/api/register", {"name": name, "password": password})
    assert st == 200, f"register {name} failed: {st} {body}"
    return json.loads(body)


def audit_events():
    events = []
    for path in (AUDIT_PATH + ".1", AUDIT_PATH):
        try:
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        events.append(json.loads(ln))
        except OSError:
            pass
    return events


def key(tok):
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# A. Brute force: 5 failures lock the username across IPs, 429 + retry_after
# ---------------------------------------------------------------------------
u1 = register("brute-user", "correct-horse-9")
S._LOGIN_FAIL.clear()
S._RATE.clear()
codes = []
for ip in ("203.0.113.1", "203.0.113.2", "203.0.113.3", "203.0.113.1", "203.0.113.2"):
    st, _body, _h = req("POST", "/api/login",
                        {"name": "brute-user", "password": "wrong-password-9"},
                        headers={"X-Forwarded-For": ip})
    codes.append(st)
st6, body6, h6 = req("POST", "/api/login",
                     {"name": "brute-user", "password": "correct-horse-9"},
                     headers={"X-Forwarded-For": "203.0.113.3"})
b6 = json.loads(body6)
check("1_lockout_5_fails_cross_ip",
      codes == [401] * 5 and st6 == 429, f"{codes} -> {st6}")
check("1b_lockout_retry_after",
      st6 == 429 and b6.get("retry_after", 0) >= 1 and h6.get("Retry-After", "") != "",
      f"{st6} {body6} {h6}")
u_free = register("free-user", "correct-horse-9")
st_free, _b, _h = req("POST", "/api/login", {"name": "free-user", "password": "correct-horse-9"})
check("1c_other_username_not_locked", st_free == 200, f"{st_free}")

# ---------------------------------------------------------------------------
# A2. Unknown user vs wrong password: same ballpark (dummy hash, no delays)
# ---------------------------------------------------------------------------
u_t = register("timing-user", "correct-horse-9")


def timed_login(name, password):
    S._LOGIN_FAIL.clear()
    S._RATE.clear()
    t0 = time.perf_counter()
    req("POST", "/api/login", {"name": name, "password": password})
    return time.perf_counter() - t0


t_unknown = sorted(timed_login(f"ghost-{i}", "whatever-9") for i in range(3))
t_wrong = sorted(timed_login("timing-user", "wrong-password-9") for _ in range(3))
mu, mw = t_unknown[1], t_wrong[1]
check("2_timing_dummy_hash",
      mu < 2 * mw and mw < 2 * mu,
      f"unknown={mu:.3f}s wrong={mw:.3f}s ({t_unknown} vs {t_wrong})")

# ---------------------------------------------------------------------------
# B. Tokens at rest: sha256 only + metadata + legacy plaintext migration + UA
# ---------------------------------------------------------------------------
u3 = register("token-user", "correct-horse-9")
tok3, uid3 = u3["token"], u3["id"]
key3 = hashlib.sha256(tok3.encode("utf-8")).hexdigest()
raw_tokens = open(os.path.join(_tmp, "tokens.json"), encoding="utf-8").read()
check("3_token_not_plaintext", tok3 not in raw_tokens and key3 in raw_tokens,
      f"plaintext present: {tok3 in raw_tokens}")
rec3 = json.loads(raw_tokens).get(key3, {})
check("3b_token_metadata",
      all(k in rec3 for k in ("issued", "last_seen", "ua_hash")),
      f"{rec3}")

legacy_tok = "deadbeef" * 6
toks = S.load_tokens()
toks[legacy_tok] = {"user_id": uid3, "exp": time.time() + 3600}
S.save_tokens(toks)
st4, body4, _ = req("GET", "/api/me", token=legacy_tok)
toks_after = json.load(open(os.path.join(_tmp, "tokens.json"), encoding="utf-8"))
check("4_legacy_token_migrates",
      st4 == 200 and key(legacy_tok) in toks_after and legacy_tok not in toks_after
      and toks_after.get(key(legacy_tok), {}).get("user_id") == uid3,
      f"{st4} {body4[:80]}")

req("GET", "/api/me", token=tok3, headers={"User-Agent": "UA-One/1.0"})
st4b, _b4b, _h4b = req("GET", "/api/me", token=tok3, headers={"User-Agent": "UA-Two/2.0"})
ua_events = [e for e in audit_events() if e.get("event") == "ua_changed"]
check("4b_ua_changed_logged", st4b == 200 and len(ua_events) >= 1,
      f"{st4b} {ua_events}")


# ---------------------------------------------------------------------------
# C. Progress payload schema
# ---------------------------------------------------------------------------
def put_progress(payload, raw=None):
    return req("PUT", f"/api/progress?user={uid3}", token=tok3, raw=raw,
               body=payload)


st5, body5, _ = put_progress({"log": [{} for _ in range(5001)], "errs": []})
check("5_log_5001_422",
      st5 == 422 and json.loads(body5).get("field") == "log", f"{st5} {body5[:120]}")

st6b, body6b, _ = put_progress({"log": [{"type": "x" * 600}], "errs": []})
check("6_long_string_422",
      st6b == 422 and json.loads(body6b).get("field") == "log[0].type",
      f"{st6b} {body6b[:120]}")

st7, body7, _ = put_progress(None, raw=b'{"log": [], "errs": [], "score": NaN}')
check("7_nan_422_never_500",
      st7 in (400, 422) and st7 != 500 and "NaN" not in body7,
      f"{st7} {body7[:120]}")

deep = 1
for _ in range(7):
    deep = {"a": deep}
st8, body8, _ = put_progress({"log": [], "errs": [], "settings": deep})
check("8_depth_422",
      st8 == 422 and json.loads(body8).get("field") == "settings", f"{st8} {body8[:120]}")

st9, body9, _ = put_progress({"log": [], "errs": [], "foo": "bar"})
st9g, body9g, _ = req("GET", f"/api/progress?download=1&user={uid3}", token=tok3)
check("9_unknown_key_kept",
      st9 == 200 and st9g == 200 and json.loads(body9g).get("foo") == "bar",
      f"{st9} {st9g} {body9g[:120]}")

# ---------------------------------------------------------------------------
# D. Global per-IP limit: 300/min on /api/*, /api/health excluded
# ---------------------------------------------------------------------------
S._RATE.clear()
codes10 = []
for _ in range(301):
    st, _b, _h = req("GET", "/api/config")
    codes10.append(st)
check("10_global_rate_301st_429",
      codes10[:300] == [200] * 300 and codes10[300] == 429,
      f"{codes10[:3]}...{codes10[-3:]}")
st11, body11, _ = req("GET", "/api/health")
check("11_health_not_counted",
      st11 == 200 and json.loads(body11).get("ok") is True, f"{st11} {body11[:80]}")

# ---------------------------------------------------------------------------
# E. Audit log: auth events, 0600, per-user endpoint
# ---------------------------------------------------------------------------
S._RATE.clear()
uA = register("audit-alice", "correct-horse-9")
uB = register("audit-bob", "correct-horse-9")
st12, _b12, _h12 = req("GET", "/api/audit")
st12b, body12b, _ = req("GET", "/api/audit?limit=50", token=uB["token"])
evB = json.loads(body12b).get("events", []) if st12b == 200 else []
check("12_audit_401_without_token", st12 == 401, f"{st12}")
check("12b_audit_own_events_only",
      st12b == 200 and len(evB) >= 1
      and all(str(e.get("user", "")).lower() in ("audit-bob", uB["id"].lower()) for e in evB)
      and "alice" not in json.dumps(evB).lower(),
      f"{st12b} {evB}")
check("12c_audit_file_0600",
      stat.S_IMODE(os.stat(AUDIT_PATH).st_mode) == 0o600
      and any(e.get("event") == "register" and e.get("user") == "audit-alice"
              for e in audit_events()),
      f"{oct(stat.S_IMODE(os.stat(AUDIT_PATH).st_mode))}")

# password change: audited + every other session invalidated
st13l, body13l, _ = req("POST", "/api/login", {"name": "audit-bob", "password": "correct-horse-9"})
tokB2 = json.loads(body13l).get("token", "")
st13, body13, _ = req("POST", "/api/password",
                      {"current": "correct-horse-9", "next": "new-horse-10"},
                      token=uB["token"])
st13m, _b13m, _h13m = req("GET", "/api/me", token=tokB2)
st13n, body13n, _ = req("GET", "/api/audit?limit=50", token=uB["token"])
evB2 = json.loads(body13n).get("events", []) if st13n == 200 else []
check("13_password_change_audited",
      st13 == 200 and any(e.get("event") == "password_change" for e in evB2)
      and any(e.get("event") == "password_change" and e.get("user") == "audit-bob"
              for e in audit_events()),
      f"{st13} {body13[:80]} {evB2}")
check("13b_password_change_revokes_others",
      st13m == 401 and st13n == 200, f"other={st13m} current={st13n}")

# ---------------------------------------------------------------------------
# F. Password strength: register + password change
# ---------------------------------------------------------------------------
S._RATE.clear()
st14a, body14a, _ = req("POST", "/api/register", {"name": "policy-user", "password": "password123"})
st14b, _b14b, _h14b = req("POST", "/api/register", {"name": "policy-user", "password": "correct-horse-9"})
check("14_password_policy_register",
      st14a == 400 and "common" in json.loads(body14a).get("error", "").lower() and st14b == 200,
      f"{st14a} {body14a[:80]} {st14b}")
st14c, _b14c, _h14c = req("POST", "/api/register", {"name": "same-name-user", "password": "same-name-user"})
check("14b_password_not_username", st14c == 400, f"{st14c}")
st14d, body14d, _ = req("POST", "/api/password",
                        {"current": "new-horse-10", "next": "password123"},
                        token=uB["token"])
check("14c_password_change_rejects_common",
      st14d == 400 and "common" in json.loads(body14d).get("error", "").lower(),
      f"{st14d} {body14d[:80]}")

srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
print("SECURITY2_EXIT", 1 if failed else 0)
sys.exit(1 if failed else 0)
