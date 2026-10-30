"""Regression test: the unauthenticated "legacy owner" path must not be reachable
through a proxy (Tailscale Funnel always adds X-Forwarded-For).

Background: /api/progress used to accept requests with no token when the target user
was "owner". That was fine on a LAN-only instance, but the moment the app was exposed
publicly it meant anyone could read or overwrite the owner's progress with no
credentials. The guard is: no token + proxied request -> 401.

Boots its own server with a temporary DATA_DIR, so nothing touches the real data/.
"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2-first-legacy-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
os.environ["B2_DEMO"] = "0"

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
S.PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{S.PORT}"

results = {}


def req(method, path, data=None, headers=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(URL + path, data=body, method=method)
    r.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


PROXY = {"X-Forwarded-For": "203.0.113.9"}

# 1. Proxied GET of the owner's progress must be rejected.
results["1_proxied_get_download"] = req("GET", "/api/progress?download=1", headers=PROXY)

# 2. Proxied GET of the backup list must be rejected.
results["2_proxied_get_list"] = req("GET", "/api/progress", headers=PROXY)

# 3. Proxied PUT must be rejected (this was the write hole).
results["3_proxied_put"] = req("PUT", "/api/progress", {"log": []}, headers=PROXY)

# 4. Proxied GET for another user without a token must be rejected.
results["4_proxied_other_user"] = req("GET", "/api/progress?user=someone", headers=PROXY)

# 5. X-Real-IP alone is enough to mark the request as proxied.
results["5_real_ip_header"] = req("GET", "/api/progress?download=1", headers={"X-Real-IP": "203.0.113.9"})

# 6. Direct local request (no proxy headers) keeps working for the owner's own machine.
results["6_direct_local_get"] = req("GET", "/api/progress?download=1")

# 7. A registered user with a token can still write and read their own progress.
try:
    body = json.dumps({"name": "guard-user", "password": "correct-horse-9"}).encode()
    r = urllib.request.Request(URL + "/api/register", data=body, method="POST")
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=15) as resp:
        payload = json.loads(resp.read())
    tok, uid = payload["token"], payload["id"]
    auth = {"Authorization": "Bearer " + tok}
    results["7_authed_put"] = req("PUT", f"/api/progress?user={uid}", {"log": [{"type": "ue"}]}, headers=auth)
    results["8_authed_get"] = req("GET", f"/api/progress?user={uid}&download=1", headers=auth)
    results["9_authed_cross_user"] = req("GET", "/api/progress?user=owner&download=1", headers=auth)
except Exception as exc:  # pragma: no cover - surfaced as a failure below
    results["7_authed_put"] = f"EXCEPTION {exc}"
    results["8_authed_get"] = "skipped"
    results["9_authed_cross_user"] = "skipped"

expected = {
    "1_proxied_get_download": 401,
    "2_proxied_get_list": 401,
    "3_proxied_put": 401,
    "4_proxied_other_user": 401,
    "5_real_ip_header": 401,
    "6_direct_local_get": 200,
    "7_authed_put": 200,
    "8_authed_get": 200,
    "9_authed_cross_user": 403,
}

failed = []
for key, want in expected.items():
    got = results.get(key)
    ok = got == want
    if not ok:
        failed.append(key)
    print(f'  "{key}": "{"OK" if ok else "FALLO"} (esperado {want}, obtuvo {got})"')

print("LEGACY_GUARD_EXIT", 1 if failed else 0)
sys.exit(1 if failed else 0)
