"""Hackathon spike (fase C1): NAT-friendly limits, clean backpressure, demo mode.

Runs against `isolated_server()` so the real server.py answers over a throwaway
DATA_DIR. Covers the four guarantees the judges' visit depends on:

  1. twenty signups from one public IP in under a minute all succeed;
  2. forty failed logins for one username stay bounded by the per-username
     lockout/backoff (the strict per-account bucket, untouched by this phase);
  3. 500 concurrent GET / never answer 5xx, and the anonymous bucket still
     answers 429 + Retry-After when it is exceeded;
  4. B2_DEMO=1 loads the app without an account and keeps the demo contract.

Run: cd tests && python3 test_spike.py
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

URL = helpers.isolated_server({"B2_DEMO": "0", "B2_REGISTER": "open"})
import server as S  # noqa: E402

PARSED = urllib.parse.urlsplit(URL)
HOST, PORT = PARSED.hostname, PARSED.port

failed = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FALLO ") + name + ("" if cond else f" -- {detail}"))
    if not cond:
        failed.append(name)


def api(method, path, payload=None, timeout=30):
    """Return (status, headers dict, body text); HTTP errors are data, not raises."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8")


def clear_rate():
    with S._RATE_LOCK:
        S._RATE.clear()


def reset_login_guard():
    with S._LOGIN_FAIL_LOCK:
        S._LOGIN_FAIL.clear()


# ---------------------------------------------------------------------------
# 0. Defaults are the conservative NAT-friendly ones.
# ---------------------------------------------------------------------------
check("default_rate_ip_auth_240", S.RATE_IP_AUTH == 240, S.RATE_IP_AUTH)
check("default_register_per_hour_30", S.REGISTER_PER_HOUR == 30, S.REGISTER_PER_HOUR)
check("default_login_ip_per_10min_120", S.LOGIN_IP_PER_10MIN == 120,
      S.LOGIN_IP_PER_10MIN)
check("default_rate_ip_anon_600", S.RATE_IP_ANON == 600, S.RATE_IP_ANON)

# The per-account backoff is the primary brute-force guard and must not drift.
BACKOFF = tuple(S.LOGIN_BACKOFF)
check("login_backoff_unchanged", BACKOFF == (0.0, 0.0, 5.0, 15.0, 60.0), BACKOFF)
check("login_lock_unchanged",
      S.LOGIN_FAIL_MAX == 5 and S.LOGIN_LOCK_S == 15 * 60,
      (S.LOGIN_FAIL_MAX, S.LOGIN_LOCK_S))
# Speed only: the production delays were asserted above, so the 40-attempt run
# below does not spend 80 s sleeping.
S.LOGIN_BACKOFF = (0.0, 0.0, 0.0, 0.0, 0.0)

# ---------------------------------------------------------------------------
# 1. Twenty signups from the same IP inside one minute (was 5/hour).
# ---------------------------------------------------------------------------
clear_rate()
codes, bodies = [], []
for i in range(20):
    st, _h, body = api("POST", "/api/register",
                       {"name": f"spike-juror-{i:02d}", "password": "spike-pass-9x"})
    codes.append(st)
    bodies.append(body[:120])
check("20_signups_same_ip_all_200", codes == [200] * 20, codes)

statuses = []
locked_headers, locked_body = {}, ""
for i in range(40):
    st, headers, body = api("POST", "/api/login",
                            {"name": "spike-juror-00", "password": "wrong-password"})
    statuses.append(st)
    if i == 5:
        locked_headers, locked_body = headers, body
check("failed_logins_first_five_401", statuses[:5] == [401] * 5, statuses[:5])
check("failed_logins_then_locked",
      all(st == 429 for st in statuses[5:]), statuses[5:])
obj = json.loads(locked_body)
check("lockout_keeps_contract",
      obj.get("error") == "too many failed attempts"
      and obj.get("retry_after", 0) > 0
      and locked_headers.get("Retry-After") == str(obj["retry_after"]),
      (locked_body[:120], locked_headers.get("Retry-After")))

reset_login_guard()
clear_rate()

# ---------------------------------------------------------------------------
# 2. 500 concurrent GET /: no 5xx, no transport failure.
# ---------------------------------------------------------------------------
N = 500
barrier = threading.Barrier(N, timeout=60)
results = []
errors = []


def hammer(_i):
    conn = None
    try:
        barrier.wait()
        conn = http.client.HTTPConnection(HOST, PORT, timeout=60)
        conn.request("GET", "/", headers={"Connection": "close"})
        resp = conn.getresponse()
        resp.read()
        results.append(resp.status)
    except Exception as exc:  # noqa: BLE001 - report any transport failure
        errors.append(repr(exc))
    finally:
        if conn is not None:
            conn.close()


time.sleep(0.2)
threads = [threading.Thread(target=hammer, args=(i,)) for i in range(N)]
for t in threads:
    t.start()
for t in threads:
    t.join(90)
check("500_concurrent_no_transport_errors", not errors, errors[:3])
check("500_concurrent_all_answered", len(results) == N, len(results))
check("500_concurrent_no_5xx", all(200 <= st < 500 for st in results),
      sorted({st for st in results if st >= 500}))

# ---------------------------------------------------------------------------
# 3. Anonymous bucket still stops a flood with 429 + Retry-After.
# ---------------------------------------------------------------------------
clear_rate()
S.RATE_IP_ANON = 50
try:
    last = None
    for _ in range(60):
        last = api("GET", "/api/config")
        if last[0] != 200:
            break
    st, headers, body = last
    obj = json.loads(body)
    check("anon_bucket_429", st == 429, (st, body[:120]))
    check("anon_bucket_retry_after", headers.get("Retry-After", "").isdigit(),
          headers.get("Retry-After"))
    check("anon_bucket_json_contract",
          obj.get("error") == "too many requests"
          and isinstance(obj.get("retry_after"), int) and obj["retry_after"] >= 1,
          body[:120])
finally:
    S.RATE_IP_ANON = 600
    clear_rate()

# ---------------------------------------------------------------------------
# 4. Exhausted connection slots: 503 with Retry-After, JSON vs HTML body.
# ---------------------------------------------------------------------------
old_sem = S._CONN_SEM
S._CONN_SEM = threading.BoundedSemaphore(0)
try:
    st, headers, body = api("GET", "/api/config")
    obj = json.loads(body)
    check("conn_limit_api_503",
          st == 503 and headers.get("Retry-After") == "1"
          and obj == {"error": "busy", "retry_after": 1},
          (st, body[:120], headers.get("Retry-After")))

    st, headers, body = api("GET", "/")
    check("conn_limit_html_503",
          st == 503 and headers.get("Retry-After") == "1"
          and headers.get("Content-Type", "").startswith("text/html")
          and "Busy right now" in body and "Traceback" not in body,
          (st, headers.get("Content-Type"), body[:80]))
finally:
    S._CONN_SEM = old_sem

# ---------------------------------------------------------------------------
# 5. B2_DEMO=1: the app is usable without an account and the contract holds.
# ---------------------------------------------------------------------------
clear_rate()
S.B2_DEMO = True
S.B2_REGISTER = "open"
try:
    st, _h, body = api("GET", "/api/config")
    cfg = json.loads(body)
    check("demo_config_true", st == 200 and cfg.get("demo") is True, body[:120])

    st, _h, body = api("POST", "/api/register",
                       {"name": "demo-juror", "password": "demo-pass-9x"})
    check("demo_register_blocked",
          st == 403 and "demo mode" in json.loads(body).get("error", ""),
          (st, body[:120]))

    st, _h, body = api("POST", "/api/login",
                       {"name": "demo-juror", "password": "demo-pass-9x"})
    check("demo_login_blocked",
          st == 403 and "demo mode" in json.loads(body).get("error", ""),
          (st, body[:120]))

    st, _h, body = api("GET", "/")
    check("demo_home_no_account", st == 200 and len(body) > 500, st)

    st, _h, body = api("GET", "/app")
    check("demo_app_banner", st == 200 and "Demo mode" in body, st)

    # AI stays reachable (quota-gated), not swallowed by the demo account block.
    st, _h, body = api("POST", "/api/ai/writing", {})
    check("demo_ai_not_account_blocked",
          st != 403 and "demo mode" not in body, (st, body[:120]))
finally:
    S.B2_DEMO = False

print()
if failed:
    print(f"{len(failed)} FAILED: " + ", ".join(failed))
    sys.exit(1)
print("all spike checks passed")
