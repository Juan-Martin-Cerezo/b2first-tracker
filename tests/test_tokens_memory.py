"""Phase B1: the session store lives in memory and persists in the background.

The measured baseline (docs/internal/LOADTEST-BASELINE.md) showed every authenticated
request reading and rewriting the whole data/tokens.json just to slide
`last_seen`/`exp`: 33.5 ms per request at ~500 sessions, serialised behind one
lock. This suite proves the file is off the hot path and that the guarantees
around it still hold:

  1. 200 concurrent authenticated GETs never touch tokens.json (mtime/inode/size
     unchanged) and all answer 200;
  2. login, logout, password change and account delete write immediately, so a
     revocation is durable before the response leaves;
  3. `last_seen`/`exp` slides are debounced and land on disk via the flusher
     (B2_TOKENS_FLUSH_S=1), and the flusher drops expired rows;
  4. expired, absolute-expired and cross-user tokens answer exactly as before
     (401 "session expired", 401 "invalid session", 403);
  5. an external rewrite of tokens.json is picked up (reload) and never
     overwritten by a later flush.

Runs against an isolated server over a throwaway DATA_DIR.

Run: cd tests && python3 test_tokens_memory.py
"""
import http.client
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

URL = helpers.isolated_server({"B2_DEMO": "0", "B2_REGISTER": "open",
                               "B2_TOKENS_FLUSH_S": "60"})
import server as S  # noqa: E402
import store  # noqa: E402

PARSED = urllib.parse.urlsplit(URL)
HOST, PORT = PARSED.hostname, PARSED.port

failed = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FALLO ") + name + ("" if cond else f" -- {detail}"))
    if not cond:
        failed.append(name)


def req(method, path, body=None, token=None, headers=None, timeout=30):
    """Return (status, body text, headers dict); HTTP errors are data."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = dict(headers or {})
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = "Bearer " + token
    r = urllib.request.Request(URL + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)


def toks_meta():
    """Identity of tokens.json: an atomic write always changes mtime_ns/inode."""
    try:
        st = os.stat(S.TOKENS_FILE)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_ino, st.st_size)


def disk_tokens():
    try:
        with open(S.TOKENS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def disk_record(token):
    return disk_tokens().get(S._token_key(token), {})


def clear_rate():
    with S._RATE_LOCK:
        S._RATE.clear()


def register(name, password):
    clear_rate()
    st, body, _ = req("POST", "/api/register", {"name": name, "password": password})
    if st != 200:
        raise SystemExit(f"register {name} failed: {st} {body}")
    return json.loads(body)


def login(name, password):
    clear_rate()
    st, body, _ = req("POST", "/api/login", {"name": name, "password": password})
    if st != 200:
        raise SystemExit(f"login {name} failed: {st} {body}")
    return json.loads(body)["token"]


# ---------------------------------------------------------------------------
# 1. Seed 200 sessions (and their accounts) in one commit, so the measurement
#    window starts clean and no request has to migrate anything.
# ---------------------------------------------------------------------------
N = 200
now = time.time()
seed = {}
seed_tokens = []
seed_users = {}
for i in range(N):
    uid = "loaduser%03d" % i
    token = "seed-token-%03d" % i
    seed_tokens.append(token)
    seed_users[uid] = {"id": uid, "name": uid, "salt": "", "hash": "",
                       "color": "#1b2b48", "created": ""}
    seed[S._token_key(token)] = {
        "user_id": uid, "exp": now + S.TOKEN_TTL, "issued": now,
        "absolute_exp": now + S.TOKEN_ABSOLUTE_TTL, "last_seen": now,
        "ua_hash": S._ua_hash("seed-agent/1.0"),
    }
store.write_json_private(S.USERS_FILE, seed_users)
S.save_tokens(seed)
check("seed_200_sessions_on_disk", len(disk_tokens()) == N, len(disk_tokens()))

# No debounce trigger and no background flush may fire inside the window: the
# point is that ordinary authenticated traffic does not write the file at all.
S._TOKENS_FLUSH_S = 3600
S.TOKENS_FLUSH_MAX_CHANGES = 10_000
S.flush_tokens()
before = toks_meta()

# ---------------------------------------------------------------------------
# 2. 200 concurrent authenticated GETs: all 200, zero writes to tokens.json.
# ---------------------------------------------------------------------------
results = []
errors = []


def hammer(i):
    token = seed_tokens[i]
    uid = "loaduser%03d" % i
    conn = None
    try:
        conn = http.client.HTTPConnection(HOST, PORT, timeout=60)
        conn.request("GET", "/api/progress?download=1&user=" + uid,
                     headers={"Authorization": "Bearer " + token})
        resp = conn.getresponse()
        results.append((i, resp.status, resp.read()[:80]))
    except Exception as exc:  # noqa: BLE001 - report any transport failure
        errors.append((i, repr(exc)))
    finally:
        if conn is not None:
            conn.close()


threads = [threading.Thread(target=hammer, args=(i,)) for i in range(N)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(120)

after = toks_meta()
statuses = sorted({status for _i, status, _b in results})
check("200_concurrent_no_transport_errors", not errors, errors[:3])
check("200_concurrent_all_answered", len(results) == N, len(results))
check("200_concurrent_all_200", statuses == [200], statuses)
check("200_concurrent_zero_token_writes", after == before,
      f"before={before} after={after}")

# The slides did happen in memory, they simply were not persisted yet.
mem_after = S.load_tokens()
first_five = [S._token_key(t) for t in seed_tokens[:5]]
check("slides_applied_in_memory",
      all(mem_after.get(key) for key in first_five)
      and all(mem_after[key]["last_seen"] > now for key in first_five),
      "the memory index did not slide")
check("slides_not_persisted_yet",
      disk_record(seed_tokens[0]).get("last_seen") == now,
      disk_record(seed_tokens[0]).get("last_seen"))

# ---------------------------------------------------------------------------
# 3. Security mutations persist immediately.
# ---------------------------------------------------------------------------
PASS = "b1-password-9x"
NEW_PASS = "b1-password-9y"
reg = register("b1-user", PASS)
tok_a = reg["token"]
check("1a_register_persisted_immediately",
      S._token_key(tok_a) in disk_tokens(), "new session missing from disk")

tok_b = login("b1-user", PASS)
check("1b_login_persisted_immediately",
      S._token_key(tok_b) in disk_tokens(), "login token missing from disk")

st, body, _ = req("POST", "/api/logout", {"token": tok_b})
check("2a_logout_200", st == 200, f"{st} {body[:80]}")
check("2b_logout_persisted_immediately",
      S._token_key(tok_b) not in disk_tokens(), "revoked token still on disk")
check("2c_logout_token_refused",
      req("GET", "/api/me", token=tok_b)[0] == 401, "revoked token still accepted")

# A password change revokes every session, including the one asking.
tok_c = login("b1-user", PASS)
st, body, _ = req("POST", "/api/password",
                  {"current": PASS, "next": NEW_PASS}, token=tok_a)
fresh = json.loads(body).get("token", "") if st == 200 else ""
check("3a_password_change_200", st == 200 and bool(fresh), f"{st} {body[:120]}")
check("3b_all_old_sessions_revoked",
      req("GET", "/api/me", token=tok_a)[0] == 401
      and req("GET", "/api/me", token=tok_c)[0] == 401,
      "an old session survived the password change")
check("3c_replacement_token_valid", req("GET", "/api/me", token=fresh)[0] == 200)
check("3d_revocation_persisted",
      all(S._token_key(t) not in disk_tokens() for t in (tok_a, tok_c))
      and S._token_key(fresh) in disk_tokens(),
      "disk does not reflect the revocation")

# ---------------------------------------------------------------------------
# 4. Expiry and cross-user rules are unchanged.
# ---------------------------------------------------------------------------
tok_exp = login("b1-user", NEW_PASS)
recs = S.load_tokens()
recs[S._token_key(tok_exp)]["exp"] = time.time() - 60
S.save_tokens(recs)
st, body, _ = req("GET", "/api/me", token=tok_exp)
check("4a_expired_token_401",
      st == 401 and "session expired" in body, f"{st} {body[:80]}")
check("4b_expired_dropped_from_memory",
      S._token_key(tok_exp) not in S.load_tokens(), "expired record survived")

tok_abs = login("b1-user", NEW_PASS)
recs = S.load_tokens()
recs[S._token_key(tok_abs)]["absolute_exp"] = time.time() - 5
recs[S._token_key(tok_abs)]["exp"] = time.time() + 3600
S.save_tokens(recs)
st, body, _ = req("GET", "/api/me", token=tok_abs)
check("4c_absolute_expired_401",
      st == 401 and "session expired" in body, f"{st} {body[:80]}")

register("b1-other", "b1-other-pass-9x")
tok_other = login("b1-other", "b1-other-pass-9x")
st, body, _ = req("GET", "/api/progress?download=1&user=" + reg["id"], token=tok_other)
check("4d_cross_user_progress_403",
      st == 403 and "not authorized" in body, f"{st} {body[:80]}")
check("4e_cross_user_token_still_valid",
      req("GET", "/api/me", token=tok_other)[0] == 200
      and req("GET", "/api/me", token=fresh)[0] == 200,
      "cross-user read broke a valid session")

# ---------------------------------------------------------------------------
# 5. The flusher persists slides and drops expired rows.
# ---------------------------------------------------------------------------
tok_f = login("b1-other", "b1-other-pass-9x")
key_f = S._token_key(tok_f)
issued_seen = disk_record(tok_f).get("last_seen")
time.sleep(1.2)  # a later last_seen must be measurably different

st, _body, _ = req("GET", "/api/me", token=tok_f)
check("5a_request_ok", st == 200, st)
check("5b_slide_not_written_immediately",
      disk_record(tok_f).get("last_seen") == issued_seen,
      f"{disk_record(tok_f).get('last_seen')} vs {issued_seen}")

S._TOKENS_FLUSH_S = 1  # the running flusher picks the new interval up
flushed = None
deadline = time.time() + 8
while time.time() < deadline:
    if disk_record(tok_f).get("last_seen", 0) > issued_seen:
        flushed = disk_record(tok_f)["last_seen"]
        break
    time.sleep(0.2)
check("5c_flusher_writes_last_seen", flushed is not None,
      f"last_seen still {disk_record(tok_f).get('last_seen')} after 8 s")

# An expired row is removed from memory AND from disk by the flusher.
expired_token = "expired-row-token"
recs = S.load_tokens()
recs[S._token_key(expired_token)] = {
    "user_id": "b1-other", "exp": time.time() - 60, "issued": time.time() - 120,
    "absolute_exp": time.time() + 3600, "last_seen": time.time() - 60, "ua_hash": "",
}
S.save_tokens(recs)
check("5d_expired_row_written_for_the_test",
      S._token_key(expired_token) in disk_tokens(), "setup failed")
deadline = time.time() + 8
while time.time() < deadline and S._token_key(expired_token) in disk_tokens():
    time.sleep(0.2)
check("5e_flusher_prunes_expired_row",
      S._token_key(expired_token) not in disk_tokens()
      and S._token_key(expired_token) not in S.load_tokens(),
      "expired row survived the flush")

# Crossing TOKENS_FLUSH_MAX_CHANGES writes at once instead of waiting for the
# interval, and the counter is cleared at snapshot time: sustained traffic past
# the threshold must not degenerate into one rewrite per request (that bug
# produced 23 writes in 8 s with a 60 s interval, measured before the fix).
S._TOKENS_FLUSH_S = 3600
S.TOKENS_FLUSH_MAX_CHANGES = 10
S.flush_tokens()
quiet = toks_meta()
for _ in range(15):
    req("GET", "/api/me", token=tok_f)
crossed = toks_meta()
check("5f_threshold_forces_immediate_write", crossed != quiet,
      f"quiet={quiet} crossed={crossed}")

# Past the crossing, the next batch of 15 stays at zero writes until the
# counter is exhausted again.
writes = 0
seen = crossed
for _ in range(12):
    req("GET", "/api/me", token=tok_f)
    now_meta = toks_meta()
    if now_meta != seen:
        writes += 1
        seen = now_meta
check("5g_no_write_per_request_past_threshold", writes <= 1,
      f"{writes} writes in 12 requests after the crossing")
S.TOKENS_FLUSH_MAX_CHANGES = 10_000

# ---------------------------------------------------------------------------
# 6. An external rewrite of tokens.json wins: reloaded, never overwritten.
# ---------------------------------------------------------------------------
removed_key = S._token_key(tok_f)
external = disk_tokens()
external.pop(removed_key, None)
store.write_json_private(S.TOKENS_FILE, external)

st, body, _ = req("GET", "/api/me", token=tok_f)
check("6a_external_removal_seen", st == 401, f"{st} {body[:80]}")
check("6b_external_removal_loaded_in_memory",
      removed_key not in S.load_tokens(), "index kept a token removed on disk")

# Dirtied index + external write: the flush must reload instead of persisting
# the stale snapshot (the on-disk version is what other tools wrote).
req("GET", "/api/me", token=fresh)
external = disk_tokens()
external["external-only-key"] = {"user_id": "b1-other", "exp": time.time() + 3600,
                                 "issued": time.time(), "last_seen": time.time(),
                                 "absolute_exp": time.time() + 7200, "ua_hash": ""}
store.write_json_private(S.TOKENS_FILE, external)
S.flush_tokens()
check("6c_flush_does_not_overwrite_external_write",
      "external-only-key" in disk_tokens(),
      "flush persisted a stale snapshot over the external write")

# ---------------------------------------------------------------------------
# 7. Delete account removes every session immediately.
# ---------------------------------------------------------------------------
victim = register("b1-victim", "b1-victim-pass-9x")
victim_tok = victim["token"]
check("7a_victim_token_on_disk", S._token_key(victim_tok) in disk_tokens())
st, body, _ = req("DELETE", "/api/account", {"password": "b1-victim-pass-9x"},
                  token=victim_tok)
check("7b_delete_account_200", st == 200, f"{st} {body[:80]}")
check("7c_delete_account_revokes_immediately",
      S._token_key(victim_tok) not in disk_tokens()
      and req("GET", "/api/me", token=victim_tok)[0] == 401,
      "deleted account's session survived")

print()
if failed:
    print(f"{len(failed)} FAILED: " + ", ".join(failed))
    sys.exit(1)
print("all in-memory token store checks passed")
