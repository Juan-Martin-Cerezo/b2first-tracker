#!/usr/bin/env python3
"""Mixed anonymous load test for the b2first server (stdlib only).

Models the traffic a hackathon jury produces: one public IP, many browsers,
each opening a few keep-alive connections and alternating between the landing
page, the tracker and a cheap anonymous API call. It measures throughput and
latency percentiles and reports rate-limit/backpressure answers separately,
so a 429 storm cannot make the latency numbers look better than they are.

Usage:
  python3 tools/loadtest.py --url http://127.0.0.1:8088
  python3 tools/loadtest.py --url http://127.0.0.1:8088 \
      --connections 200 --duration 10 --json

The default mix is 40% /, 40% /app and 20% /api/config. Exit code is 0 unless
a 5xx or a transport failure appears (429/503 are recorded, not failures: the
server is expected to shed load cleanly).
"""
import argparse
import http.client
import json
import sys
import threading
import time
import urllib.parse

PATHS = ("/", "/app", "/api/config")
MIX = (0, 0, 0, 1, 1, 1, 2)  # 3/7 /, 3/7 /app, 1/7 /api/config


def percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def worker(url, deadline, index, latencies, statuses, errors, lock):
    host = url.hostname
    port = url.port or (443 if url.scheme == "https" else 80)
    http_cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    conn = None
    n = index
    while time.time() < deadline:
        path = PATHS[MIX[n % len(MIX)]]
        n += 1
        started = time.perf_counter()
        try:
            if conn is None:
                conn = http_cls(host, port, timeout=10)
            conn.request("GET", path, headers={"Connection": "keep-alive"})
            resp = conn.getresponse()
            resp.read()
            elapsed = (time.perf_counter() - started) * 1000.0
            with lock:
                statuses[resp.status] = statuses.get(resp.status, 0) + 1
                if resp.status not in (429, 503):
                    latencies.append(elapsed)
            if resp.status >= 500 or resp.getheader("Connection", "").lower() == "close":
                conn.close()
                conn = None
        except Exception as exc:  # noqa: BLE001 - count and reconnect
            with lock:
                errors.append(repr(exc))
            if conn is not None:
                conn.close()
                conn = None
    if conn is not None:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8088",
                        help="base URL of the running server")
    parser.add_argument("--connections", type=int, default=200,
                        help="concurrent connections (default 200)")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="seconds to run (default 10)")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    args = parser.parse_args()

    url = urllib.parse.urlsplit(args.url)
    if url.scheme not in ("http", "https") or not url.hostname:
        parser.error("--url must be an absolute http(s) URL")

    deadline = time.time() + args.duration
    latencies, errors = [], []
    statuses = {}
    lock = threading.Lock()
    threads = [threading.Thread(target=worker,
                                args=(url, deadline, i, latencies, statuses, errors, lock))
               for i in range(args.connections)]
    started = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = max(0.001, time.time() - started)

    # Latencies cover served answers only; load shedding is fast by design and
    # would flatter the percentile, so it is reported as its own number.
    statuses_sorted = dict(sorted(statuses.items()))
    total = sum(statuses.values())
    shed = sum(n for st, n in statuses.items() if st in (429, 503))
    report = {
        "url": args.url,
        "connections": args.connections,
        "duration_s": round(wall, 2),
        "requests": total,
        "rps": round(total / wall, 1),
        "statuses": statuses_sorted,
        "shed": shed,
        "errors": len(errors),
        "p50_ms": round(percentile(latencies, 50), 1),
        "p95_ms": round(percentile(latencies, 95), 1),
        "p99_ms": round(percentile(latencies, 99), 1),
        "note": "p50/p95/p99 cover served (non-429/503) answers only",
    }
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print(f"{report['connections']} connections, {report['duration_s']}s: "
              f"{report['requests']} req, {report['rps']} req/s")
        print(f"statuses: {statuses_sorted}  shed: {shed}  transport errors: {len(errors)}")
        print(f"latency p50 {report['p50_ms']} ms, p95 {report['p95_ms']} ms, "
              f"p99 {report['p99_ms']} ms")
        if errors:
            print("first errors: " + "; ".join(errors[:3]))

    bad = len(errors) + sum(n for st, n in statuses.items() if st >= 500)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
