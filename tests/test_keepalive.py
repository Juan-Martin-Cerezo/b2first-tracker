"""Phase H: HTTP/1.1 keep-alive against the real server.

Runs `isolated_server()` with a 1 s idle timeout so the timeout case stays fast.
Covers the four behaviours the phase promises:

  1. many sequential requests on one socket stay on that socket (no reconnect);
  2. a rejected request whose body was never read answers `Connection: close`;
  3. an idle client is dropped after the keep-alive timeout and the server keeps
     serving new connections;
  4. a conditional 304 on the same socket carries no body and is reusable.

Run: cd tests && python3 test_keepalive.py
"""
import http.client
import json
import os
import socket
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

URL = helpers.isolated_server({"B2_DEMO": "0", "B2_REGISTER": "open",
                               "B2_KEEPALIVE_TIMEOUT": "1"})
import server as S  # noqa: E402

PARSED = urllib.parse.urlsplit(URL)
HOST, PORT = PARSED.hostname, PARSED.port

failed = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FALLO ") + name + ("" if cond else f" -- {detail}"))
    if not cond:
        failed.append(name)


def read_response(sock):
    """Read one full response (headers + Content-Length body) from a raw socket."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            raise AssertionError("connection closed mid-headers: %r" % buf[:200])
        buf += chunk
    head, _, body = buf.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    parts = lines[0].split()
    status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    headers = {}
    for line in lines[1:]:
        key, _, value = line.partition(b":")
        headers[key.decode("latin-1").strip().lower()] = value.decode("latin-1").strip()
    length = int(headers.get("content-length", "0") or 0)
    while len(body) < length:
        chunk = sock.recv(65536)
        if not chunk:
            break
        body += chunk
    return status, headers, body


# 1. Fifty sequential requests must all ride the same socket.
conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
statuses = []
reused_sock = None
same_socket = True
saw_close = False
try:
    for i in range(50):
        conn.request("GET", "/")
        resp = conn.getresponse()
        data = resp.read()
        statuses.append(resp.status)
        if (resp.getheader("Connection") or "").lower() == "close":
            saw_close = True
        if conn.sock is None:
            same_socket = False
        elif reused_sock is None:
            reused_sock = conn.sock
        elif conn.sock is not reused_sock:
            same_socket = False
        if not data:
            statuses.append(0)
finally:
    conn.close()

check("01_fifty_requests_all_200", statuses == [200] * 50, statuses[:5])
check("02_one_socket_reused", same_socket, "client had to reconnect")
check("03_no_close_header", not saw_close, "server announced Connection: close")

# 2. A rejected POST whose body is never read must close the connection.
sock = socket.create_connection((HOST, PORT), timeout=10)
try:
    sock.sendall(
        ("POST /api/login HTTP/1.1\r\nHost: %s:%d\r\n"
         "Content-Length: 300000\r\nConnection: keep-alive\r\n\r\n"
         % (HOST, PORT)).encode("latin-1"))
    status, headers, _body = read_response(sock)
finally:
    sock.close()
check("04_unread_body_413", status == 413, status)
check("05_unread_body_closes", headers.get("connection", "").lower() == "close",
      headers.get("connection"))

# 3. An idle client is dropped after the timeout; the server keeps serving.
sock = socket.create_connection((HOST, PORT), timeout=10)
try:
    sock.sendall(("GET / HTTP/1.1\r\nHost: %s:%d\r\n\r\n" % (HOST, PORT)).encode("latin-1"))
    status, headers, _body = read_response(sock)
    check("06_idle_first_200", status == 200 and headers.get("connection") != "close",
          (status, headers.get("connection")))
    time.sleep(S.KEEPALIVE_TIMEOUT + 1.5)
    sock.settimeout(5)
    leftover = sock.recv(1)
finally:
    sock.close()
check("07_idle_socket_closed", leftover == b"", leftover[:20])

fresh = http.client.HTTPConnection(HOST, PORT, timeout=10)
try:
    fresh.request("GET", "/")
    resp = fresh.getresponse()
    resp.read()
    check("08_server_still_serving", resp.status == 200, resp.status)
finally:
    fresh.close()

# 4. Conditional 304 on the same socket: no body, connection still usable.
conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
try:
    conn.request("GET", "/app")
    first = conn.getresponse()
    first.read()
    etag = first.getheader("ETag")
    sock_after_first = conn.sock

    conn.request("GET", "/app", headers={"If-None-Match": etag or ""})
    cond = conn.getresponse()
    cond_body = cond.read()
    check("09_conditional_304", cond.status == 304, cond.status)
    check("10_304_no_body", cond_body == b"",
          cond_body[:40])
    check("11_304_content_length_zero",
          (cond.getheader("Content-Length") or "0") in ("0", ""),
          cond.getheader("Content-Length"))
    check("12_socket_survives_304", conn.sock is sock_after_first and etag is not None,
          "connection was dropped after 304")

    conn.request("GET", "/app")
    again = conn.getresponse()
    again_body = again.read()
    check("13_reusable_after_304", again.status == 200 and again_body != b"",
          again.status)
finally:
    conn.close()

# Instrumentation: /api/health carries numeric keep-alive counters.
conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
try:
    conn.request("GET", "/api/health")
    health = conn.getresponse()
    payload = json.loads(health.read().decode("utf-8"))
finally:
    conn.close()
ka = payload.get("keepalive") or {}
check("14_health_keepalive_counters",
      set(("connections_open", "reused", "requests_total")) <= set(ka)
      and ka.get("reused", 0) >= 1 and ka.get("requests_total", 0) >= 50,
      ka)

print()
if failed:
    print(f"{len(failed)} FAILED: " + ", ".join(failed))
    sys.exit(1)
print("all keep-alive checks passed")
