"""Phase C2: bounded upstream concurrency for the speaking examiner.

The turn endpoint used to make one upstream call per turn with no cap on
simultaneous calls, so N parallel mocks parked N threads on the provider.
These checks run the real server against a local Gemini stub and assert:

  A. 12 concurrent turns, stub latency 1 s: at most B2_SPK_MAX_INFLIGHT
     simultaneous calls reach the stub, every response is 200 or a 503 with
     Retry-After, and no handler thread is lost.
  B. stub stuck for 60 s: every turn is answered within 30 s with 503/504.
  C. /api/health reports the instance counters (numbers only).

Run:  uv run --no-project --quiet --with playwright --with httpx python test_speaking_concurrency.py
"""
import base64
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

import helpers  # noqa: E402

TURNS = 12
MAX_INFLIGHT = 4
QUEUE_WAIT_S = 8
STUCK_S = 60
HARD_LIMIT_S = 30

STUB = {"latency": 1.0, "active": 0, "peak": 0, "calls": 0,
        "lock": threading.Lock()}


class StubHandler(BaseHTTPRequestHandler):
    """Gemini `:generateContent` stub: sleeps `latency` and answers one turn."""

    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > 0:
            self.rfile.read(length)
        with STUB["lock"]:
            STUB["active"] += 1
            STUB["calls"] += 1
            STUB["peak"] = max(STUB["peak"], STUB["active"])
        try:
            time.sleep(STUB["latency"])
        finally:
            with STUB["lock"]:
                STUB["active"] -= 1
        text = json.dumps({"transcript": "I think so.",
                           "reply": "Why do you think so?"})
        body = json.dumps({
            "candidates": [{"content": {"parts": [{"text": text}]}}],
        }).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass  # the server already closed the socket on its deadline


def free_stub():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


stub_srv, STUB_URL = free_stub()
URL = helpers.isolated_server({
    "B2_SPK_GOOGLE_KEY": "c2-test-key",
    "B2_SPK_TURN_BASE": STUB_URL,
    "B2_SPK_MAX_INFLIGHT": str(MAX_INFLIGHT),
    "B2_SPK_QUEUE_WAIT": str(QUEUE_WAIT_S),
    # The load account runs as owner so plan mocks never turn this into a 429
    # test; capacity is the only thing measured here.
    "B2_OWNER_UIDS": "c2-load",
})

import server as S  # noqa: E402  (imported by isolated_server already)

AUDIO = base64.b64encode(b"\x00\x00" * 8000).decode("ascii")  # 1 s, 16 kHz PCM


def request(path, payload=None, token=None, timeout=45):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(URL + path, data=data,
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or "{}"
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"raw": raw}
        return exc.code, dict(exc.headers), body


def account():
    name, password = "c2-load", "c2-load-pass-9"
    try:
        st, _h, body = request("/api/register", {"name": name, "password": password})
        if st == 200:
            return body["token"]
    except urllib.error.HTTPError:
        pass
    st, _h, body = request("/api/login", {"name": name, "password": password})
    assert st == 200, "could not open the load account: %s %s" % (st, body)
    return body["token"]


def reset_buckets():
    S._RATE.clear()
    with STUB["lock"]:
        STUB["peak"] = 0
        STUB["calls"] = 0
        STUB["active"] = 0


def turn_body(index):
    return {
        "audio_b64": AUDIO,
        "mime": "audio/pcm;rate=16000",
        "part": 1,
        "role": "examiner",
        "tts": "none",
        "session_id": "c2-sess-%d" % index,
        "history": [],
    }


def run_turns(token, limit_s=HARD_LIMIT_S):
    """Fire TURNS turns at once; return [(status, headers, body, elapsed_s)]."""
    out = [None] * TURNS

    def worker(i):
        started = time.time()
        try:
            st, headers, body = request("/api/speaking/turn", turn_body(i), token,
                                        timeout=limit_s + 10)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            st, headers, body = "EXC", {}, {"error": repr(exc)}
        out[i] = (st, headers, body, time.time() - started)

    threads = [threading.Thread(target=worker, args=(i,), name="c2-turn-%d" % i)
               for i in range(TURNS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(limit_s + 15)
    lost = [t.name for t in threads if t.is_alive()]
    assert not lost, "handler threads never finished: %s" % lost
    assert all(r is not None for r in out), "a turn produced no result"
    return out


def statuses(results):
    return [r[0] for r in results]


def main():
    token = account()
    report = {}

    # A. 1 s upstream, 12 at once: the gate bounds the stub.
    reset_buckets()
    STUB["latency"] = 1.0
    started = time.time()
    results = run_turns(token)
    elapsed = time.time() - started
    peak = STUB["peak"]
    ok = [r for r in results if r[0] == 200]
    busy = [r for r in results if r[0] == 503]
    other = [r for r in results if r[0] not in (200, 503)]

    assert not other, "unexpected statuses: %s" % [(r[0], r[2]) for r in other]
    assert len(ok) + len(busy) == TURNS, statuses(results)
    assert peak <= MAX_INFLIGHT, "stub saw %d simultaneous calls (cap %d)" % (
        peak, MAX_INFLIGHT)
    assert not busy or all("Retry-After" in r[1] for r in busy), \
        "a 503 arrived without Retry-After: %s" % [(r[0], r[1]) for r in busy]
    for r in busy:
        assert r[2].get("error") == "busy", r[2]
        assert r[2].get("retry_after") == 5, r[2]
    report["A_12x1s"] = {
        "ok": len(ok), "busy": len(busy), "peak_at_stub": peak,
        "elapsed_s": round(elapsed, 2),
        "p50_ms": int(statistics.median([r[3] for r in results]) * 1000),
    }

    # B. Stuck upstream: nobody waits past the turn deadline.
    reset_buckets()
    STUB["latency"] = STUCK_S
    results = run_turns(token)
    for status, _headers, body, took in results:
        assert status in (503, 504), "stuck upstream answered %s %s" % (status, body)
        assert took <= HARD_LIMIT_S, "a turn held its thread %.1fs" % took
    report["B_stuck_60s"] = {
        "504": statuses(results).count(504),
        "503": statuses(results).count(503),
        "worst_s": round(max(r[3] for r in results), 2),
    }

    # C. /api/health exposes the counters, numbers only.
    st, _headers, health = request("/api/health")
    assert st == 200, health
    counters = health.get("speaking_upstream")
    assert isinstance(counters, dict), health
    for key in ("inflight", "peak_inflight", "queue_rejected", "busy_503",
                "timeout_504", "rate_limited_429", "max_inflight",
                "queue_wait_s", "turn_deadline_s"):
        assert isinstance(counters.get(key), int) or isinstance(
            counters.get(key), float), "health is missing %s: %s" % (key, counters)
    assert counters["max_inflight"] == MAX_INFLIGHT, counters
    assert counters["peak_inflight"] <= MAX_INFLIGHT, counters
    assert counters["busy_503"] >= report["A_12x1s"]["busy"], counters
    assert counters["timeout_504"] >= report["B_stuck_60s"]["504"], counters
    assert "c2-load" not in json.dumps(health), "health leaked an account id"
    report["C_health"] = counters

    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("OK: bounded upstream concurrency with clean backpressure")


if __name__ == "__main__":
    main()
