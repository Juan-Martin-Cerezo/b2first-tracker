"""Network hardening tests (fase 16).

Covers the raw-HTTP surface an attacker reaches before any auth logic: request
limits (URI/headers/body), method allowlist, traversal and hidden-file guards,
response headers, banner hygiene and error responses that never leak.

Boots its own server on a temporary DATA_DIR, so nothing touches the real data/.
"""
import contextlib
import io
import json
import os
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request

# B2_HOST must be unset before importing the module: the constant is read at import.
os.environ.pop("B2_HOST", None)
os.environ.pop("B2_ALLOWED_HOSTS", None)
os.environ["B2_DEMO"] = "0"
os.environ["B2_REGISTER"] = "open"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2srvhard-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
S.PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{S.PORT}"

failed = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FALLO ") + name + ("" if cond else f" -- {detail}"))
    if not cond:
        failed.append(name)


def raw(payload, timeout=10):
    """Send bytes over a fresh socket; return (status, headers, body)."""
    s = socket.create_connection(("127.0.0.1", S.PORT), timeout=timeout)
    try:
        s.sendall(payload)
        chunks = []
        while True:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        s.close()
    data = b"".join(chunks)
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    parts = lines[0].split() if lines else []
    status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    headers = {}
    for line in lines[1:]:
        if b":" in line:
            k, v = line.split(b":", 1)
            headers[k.decode("latin-1").strip().lower()] = v.decode("latin-1").strip()
    return status, headers, body


def raw_req(method, target, extra_headers=""):
    return raw(
        f"{method} {target} HTTP/1.1\r\nHost: localhost\r\n"
        f"Connection: close\r\n{extra_headers}\r\n".encode("latin-1")
    )


def get(path, headers=None):
    req = urllib.request.Request(URL + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)


def tree(root):
    out = []
    for dirpath, dirs, files in os.walk(root):
        out += [os.path.join(dirpath, d) for d in dirs]
        out += [os.path.join(dirpath, f) for f in files]
    return sorted(out)


before = tree(_tmp)

# 1. URI longer than 2048 chars -> 414
st, _h, _b = raw_req("GET", "/" + "a" * 3000)
check("01_uri_too_long_414", st == 414, f"{st}")

# 2. More than 60 headers -> 431
extra = "".join(f"X-Pad-{i}: v\r\n" for i in range(70))
st, _h, _b = raw_req("GET", "/", extra)
check("02_too_many_headers_431", st == 431, f"{st}")

# 3. Content-Length over 3 MB is rejected before the body is read -> 413
st, _h, _b = raw(
    b"POST /api/events HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
    b"Content-Type: application/json\r\nContent-Length: 5000000\r\n\r\n"
)
check("03_body_too_large_413", st == 413, f"{st}")

# 4. TRACE is always 405 with the Allow header
st, h, _b = raw_req("TRACE", "/")
check("04_trace_405_allow",
      st == 405 and "GET" in h.get("allow", "") and "POST" in h.get("allow", ""),
      f"{st} {h.get('allow')}")

# 5. An invented method is 405 as well
st, h, _b = raw_req("FROB", "/")
check("05_unknown_method_405", st == 405 and "allow" in h, f"{st} {h.get('allow')}")

# 6. Literal traversal -> 400
st, _h, _b = raw_req("GET", "/../../etc/passwd")
check("06_literal_traversal_400", st == 400, f"{st}")

# 7. Percent-encoded traversal -> 400
st, _h, _b = raw_req("GET", "/%2e%2e%2f%2e%2e%2fetc%2fpasswd")
check("07_encoded_traversal_400", st == 400, f"{st}")

# 8. Mixed dots + encoded slash (double encoding) -> 400/404, never 200
st, _h, _b = raw_req("GET", "/..%2f..%2fetc/passwd")
check("08_double_encoded_traversal", st in (400, 404), f"{st}")

# 9. Hidden files -> 403/404 and never their content
hidden = {}
for target in ("/.env", "/.git/config", "/.events_salt"):
    st, _h, body = raw_req("GET", target)
    hidden[target] = (st, body)
check("09_hidden_files_blocked",
      all(st in (403, 404) for st, _b in hidden.values())
      and all(b"B2_" not in body and len(body) < 200 for _st, body in hidden.values()),
      f"{ {k: v[0] for k, v in hidden.items()} }")

# 10. NUL byte (percent-encoded) -> 400
st, _h, _b = raw_req("GET", "/material/%00.txt")
check("10_nul_byte_400", st == 400, f"{st}")

# 11. Security headers on /
st, _b, h = get("/")
check("11_security_headers",
      st == 200
      and h.get("Strict-Transport-Security") == "max-age=63072000; includeSubDomains; preload"
      and h.get("Cross-Origin-Opener-Policy") == "same-origin"
      and h.get("Cross-Origin-Resource-Policy") == "same-origin",
      f"{st} {h}")

# 12. No version banner (no interpreter, no "product/version") and no X-Powered-By
server = h.get("Server", "")
check("12_banner_hygiene",
      "X-Powered-By" not in h and "Python" not in server and "/" not in server,
      f"server={server!r} xpb={h.get('X-Powered-By')}")

# 13. A forced 500 leaks no traceback and no filesystem path
orig_portal = S.portal


def _boom():
    raise RuntimeError("forced failure")


S.portal = _boom
err = io.StringIO()
with contextlib.redirect_stderr(err):
    st, body, h500 = get("/libros")
S.portal = orig_portal
check("13_internal_error_no_leak",
      st == 500 and "Traceback" not in body and "/home/" not in body
      and "/tmp/" not in body and json.loads(body).get("error") == "internal"
      and json.loads(body).get("rid") == h500.get("X-Request-Id"),
      f"{st} {body[:120]}")

# 14. None of the hostile requests created files under DATA_DIR
check("14_no_data_writes", tree(_tmp) == before, f"{tree(_tmp)} != {before}")

# 15. The bind address defaults to loopback
check("15_bind_default_loopback", S.B2_HOST == "127.0.0.1", f"{S.B2_HOST!r}")

# 16. With every connection permit held, the next request gets 503 + Retry-After
held = 0
try:
    while S._CONN_SEM.acquire(blocking=False):
        held += 1
    st, h, body = raw_req("GET", "/")
finally:
    for _ in range(held):
        S._CONN_SEM.release()
payload = json.loads(body) if body else {}
check("16_connection_cap_503",
      st == 503 and h.get("retry-after") == "1"
      and payload.get("error") == "busy" and payload.get("retry_after") == 1,
      f"{st} {h.get('retry-after')} {body[:120]}")

srv.shutdown()
print("SERVER_HARDENING_EXIT", 1 if failed else 0)
sys.exit(1 if failed else 0)
