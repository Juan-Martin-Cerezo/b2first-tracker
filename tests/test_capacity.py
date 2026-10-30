"""Capacity tests (fase 23): cached static payload, ETag/304 and per-user limits.

Runs the real server (a subprocess of `server.py`), measures with httpx and
fails when the numbers regress. It needs no Playwright:

    uv run --with httpx python test_capacity.py

Two measurements are taken on the same machine, same 100 clients, 10 seconds:
  * cache ON:  GET / must stay under p95 700 ms with zero 503/429.
  * cache OFF: B2_NO_CACHE=1 is the old behaviour (gzip on every request); the
               cached p95 must be at least 2x better than this baseline.

The per-IP rate limit would distort a capacity run, so every measurement server
starts with the buckets disabled (B2_RATE_IP_ANON/B2_RATE_IP_API=0). The real
per-user limit is exercised separately at the end with a tiny bucket.
"""
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
import asyncio

try:
    import httpx
except ImportError:  # pragma: no cover - the documented runner installs it
    sys.exit("missing httpx: run `uv run --with httpx python test_capacity.py`")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server.py")
INDEX = os.path.join(ROOT, "index.html")

DURATION_S = 10.0
CONCURRENCY = 100
CACHED_P95_MAX_MS = 700.0

failed = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FALLO ") + name + ("" if cond else f" -- {detail}"))
    if not cond:
        failed.append(name)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(extra_env=None):
    """Boot the real server on an ephemeral port with a temporary data dir."""
    port = free_port()
    tmp = tempfile.mkdtemp(prefix="b2cap-")
    env = os.environ.copy()
    env.update({
        "PORT": str(port),
        "B2_HOST": "127.0.0.1",
        "DATA_DIR": tmp,
        "B2_DEMO": "0",
        "B2_REGISTER": "open",
        "B2_OWNER_PASSWORD": "capacity-owner-pass-9",
        # Capacity is measured with the IP buckets off; see the module docstring.
        "B2_RATE_USER_API": "0",
        "B2_RATE_IP_ANON": "0",
        "B2_RATE_IP_API": "0",
        "B2_RATE_IP_AUTH": "0",
    })
    env.update(extra_env or {})
    log_path = os.path.join(tmp, "server.log")
    log = open(log_path, "wb")
    proc = subprocess.Popen([sys.executable, SERVER], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        try:
            r = httpx.get(url + "/api/health", timeout=1.0)
            if r.status_code in (200, 503):
                return proc, url, log_path
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    proc.terminate()
    proc.wait(timeout=5)
    with open(log_path, "r", errors="replace") as f:
        raise RuntimeError("server did not start:\n" + f.read()[-3000:])


def stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def load(url, duration=DURATION_S, concurrency=CONCURRENCY, headers=None):
    """Hammer GET / for `duration` seconds; return (statuses, p95 ms, errors).

    Async client on purpose: 100 Python threads would spend the run fighting
    over the GIL and hide the server-side difference we are measuring.
    """
    deadline = time.perf_counter() + duration
    statuses = {}
    lats = []
    errors = 0
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=0)

    async def worker(client):
        nonlocal errors
        while time.perf_counter() < deadline:
            t0 = time.perf_counter()
            try:
                # Raw stream: consuming the compressed bytes without decoding keeps
                # the client from becoming the bottleneck (unzipping 434 KB per
                # response would measure zlib, not the server).
                async with client.stream("GET", "/") as r:
                    body_len = 0
                    async for chunk in r.aiter_raw():
                        body_len += len(chunk)
                    status = r.status_code
            except httpx.HTTPError:
                errors += 1
                continue
            lats.append(time.perf_counter() - t0)
            statuses[status] = statuses.get(status, 0) + 1
            if status == 304 and body_len:
                errors += 1

    async def run():
        async with httpx.AsyncClient(base_url=url, timeout=10.0,
                                     headers=headers or {}, limits=limits) as client:
            await asyncio.gather(*[worker(client) for _ in range(concurrency)])

    asyncio.run(run())
    return statuses, percentile(lats, 95), errors


def percentile(values, p):
    if not values:
        return float("inf")
    ordered = sorted(values)
    idx = max(0, math.ceil(p / 100.0 * len(ordered)) - 1)
    return ordered[idx] * 1000.0


def main():
    served = os.path.getsize(INDEX)
    print(f"index.html: {served} bytes")

    # ---------------- cache ON ----------------
    proc, url, _log = start_server()
    try:
        warm = httpx.get(url + "/", headers={"Accept-Encoding": "gzip"}, timeout=10)
        etag = warm.headers.get("etag")
        last_modified = warm.headers.get("last-modified")
        check("GET / is 200", warm.status_code == 200, warm.status_code)
        check("GET / sends an ETag", bool(etag), warm.headers)
        check("GET / sends Last-Modified", bool(last_modified), warm.headers)
        check("GET / sends Vary: Accept-Encoding",
              "accept-encoding" in (warm.headers.get("vary") or "").lower(),
              warm.headers.get("vary"))
        check("GET / is gzipped for a gzip client",
              warm.headers.get("content-encoding") == "gzip",
              warm.headers.get("content-encoding"))

        raw = httpx.get(url + "/", headers={"Accept-Encoding": "identity"}, timeout=10)
        check("identity client gets the uncompressed body",
              raw.headers.get("content-encoding") is None and len(raw.content) == served,
              (raw.headers.get("content-encoding"), len(raw.content)))

        # Revalidation: every response is a 304 with no body.
        statuses, p95_304, bad = load(url, duration=3.0, concurrency=20,
                                      headers={"If-None-Match": etag})
        check("revalidation returns only 304", set(statuses) == {304}, statuses)
        check("revalidation sends no body", bad == 0, bad)

        # A touch invalidates the entry on the next request (no restart).
        st = os.stat(INDEX)
        try:
            os.utime(INDEX, None)
            touched = httpx.get(url + "/", timeout=10)
        finally:
            os.utime(INDEX, ns=(st.st_atime_ns, st.st_mtime_ns))
        new_etag = touched.headers.get("etag")
        check("touch index.html changes the ETag", new_etag != etag,
              f"{etag} -> {new_etag}")

        # Capacity, cache ON.
        statuses, p95_cached, errors = load(url)
        total = sum(statuses.values())
        print(f"cache ON : {total} req, p95 {p95_cached:.1f} ms, statuses {statuses}")
        check("cache ON: no 503/429", not ({503, 429} & set(statuses)), statuses)
        check("cache ON: no transport errors", errors == 0, errors)
        check(f"cache ON: p95 < {CACHED_P95_MAX_MS:.0f} ms",
              p95_cached < CACHED_P95_MAX_MS, f"{p95_cached:.1f} ms")
        check("cache ON: enough requests measured", total >= 200, total)
    finally:
        stop_server(proc)

    # ---------------- cache OFF (baseline) ----------------
    proc, url_off, _log = start_server({"B2_NO_CACHE": "1"})
    try:
        plain = httpx.get(url_off + "/", headers={"Accept-Encoding": "gzip"}, timeout=10)
        check("B2_NO_CACHE=1 disables the ETag", not plain.headers.get("etag"),
              plain.headers.get("etag"))
        statuses, p95_baseline, errors = load(url_off)
        total = sum(statuses.values())
        print(f"cache OFF: {total} req, p95 {p95_baseline:.1f} ms, statuses {statuses}")
        check("baseline: no transport errors", errors == 0, errors)
        check("cache ON is at least 2x better than the uncached baseline",
              p95_cached * 2 <= p95_baseline,
              f"cached {p95_cached:.1f} ms vs baseline {p95_baseline:.1f} ms")
    finally:
        stop_server(proc)

    # ---------------- per-user rate limit (point B) ----------------
    # Same source IP for both accounts: user A burns its bucket, user B must
    # keep getting 200. The IP buckets are disabled so only the user bucket acts.
    proc, url_rl, _log = start_server({"B2_RATE_USER_API": "5"})
    try:
        def register(name):
            r = httpx.post(url_rl + "/api/register",
                           json={"name": name, "password": "capacity-pass-9"},
                           timeout=10)
            return r

        a = register("capacity-abuser")
        b = register("capacity-honest")
        check("both accounts register behind one IP",
              a.status_code == 200 and b.status_code == 200,
              (a.status_code, b.status_code))
        tok_a = a.json().get("token", "")
        tok_b = b.json().get("token", "")

        def me(token):
            return httpx.get(url_rl + "/api/me",
                             headers={"Authorization": "Bearer " + token}, timeout=10)

        codes = [me(tok_a).status_code for _ in range(7)]
        limited = me(tok_a)
        check("abusing user is rate limited", 429 in codes, codes)
        check("429 keeps Retry-After", bool(limited.headers.get("retry-after")),
              limited.headers.get("retry-after"))
        check("429 keeps the JSON error",
              limited.status_code == 429
              and limited.json().get("error") == "too many requests",
              (limited.status_code, limited.text[:120]))
        check("a different user on the same IP is not blocked",
              me(tok_b).status_code == 200, me(tok_b).status_code)

        owner = httpx.post(url_rl + "/api/login",
                           json={"name": "owner",
                                 "password": "capacity-owner-pass-9"}, timeout=10)
        if owner.status_code == 200:
            metrics = httpx.get(url_rl + "/api/metrics",
                                headers={"Authorization": "Bearer "
                                         + owner.json().get("token", "")}, timeout=10)
            body = metrics.json() if metrics.status_code == 200 else {}
            check("/api/metrics exposes rate_limited_by_user",
                  body.get("rate_limited_by_user", 0) >= 1, metrics.text[:200])
            check("/api/metrics exposes rate_limited_by_ip",
                  "rate_limited_by_ip" in body, metrics.text[:200])
    finally:
        stop_server(proc)

    print()
    if failed:
        print(f"{len(failed)} FAILED: " + ", ".join(failed))
        return 1
    print("all capacity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
