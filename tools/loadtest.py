#!/usr/bin/env python3
<<<<<<< HEAD
# -*- coding: utf-8 -*-
"""Load generator for the B2 First tracker (stdlib only).

Two modes:

  * seed: create N accounts through the real API and save their tokens, so a
    load run never has to pay the PBKDF2 login cost just to authenticate.
  * load: hammer the server for a fixed window with a fixed number of threads
    and report req/s, latency percentiles and errors per operation class.

Scenarios:
  read   GET / (landing HTML)
  api    GET /api/progress?user=<id>&download=1 with Bearer (full document)
  write  PUT /api/progress?user=<id> with a realistic ~30 KB document
  login  POST /api/login with valid credentials of the seeded users
  mixed  60% read / 20% api / 15% write / 5% login (the expected traffic)

The server speaks HTTP/1.0 and closes every connection, so the client opens a
fresh TCP connection per request: that is what the app really costs a browser.

Anti-abuse buckets: the per-IP credential limits are part of the product, not
of its capacity. --xff-pool gives every synthetic request its own
X-Forwarded-For value (the loopback peer is a trusted proxy in server.py), and
--users spreads logins over the seeded accounts, so a capacity run measures
CPU/JSON/GIL/connections instead of the rate limiter. The runner disables the
env-configurable buckets as well.

Examples:
  python3 tools/loadtest.py --url http://127.0.0.1:9000 --seed 200 \
      --creds-out /tmp/creds.json
  python3 tools/loadtest.py --url http://127.0.0.1:9000 --scenario mixed \
      --concurrency 100 --duration 30 --creds /tmp/creds.json --xff-pool 4096
=======
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
>>>>>>> feat/queue-c1
"""
import argparse
import http.client
import json
<<<<<<< HEAD
import math
import os
import re
import socket
import ssl
import sys
import threading
import time
from urllib.parse import quote, urlsplit

VERSION = "1.0"
UA = "b2first-loadtest/" + VERSION
DEFAULT_PASSWORD = "loadtest-pass-9"
CLK_TCK = os.sysconf("SC_CLK_TCK")
SERVER_TIMING_RE = re.compile(r"app;dur=([0-9.]+)")
SKILLS = ("Reading", "Listening", "Writing", "Speaking", "Use of English")
SCENARIOS = ("read", "api", "write", "login", "mixed")
DEFAULT_WEIGHTS = "60,20,15,5"


# ---------------------------------------------------------------------------
# Realistic progress document (validated by server._validate_progress)
# ---------------------------------------------------------------------------
def progress_doc(seq=0, log_entries=95):
    """A progress payload that passes the server schema and weighs 20-40 KB."""
    note = ("Timed practice on part {part}: reviewed every wrong answer, wrote down the "
            "collocations and linking devices to reuse next session, and redid the two "
            "questions that took longest. ")
    doc = {
        "schema_version": 2,
        "onboarded": True,
        "profile": {
            "name": "Load Test Student", "exam": "B2 First",
            "examDate": "2027-06-12", "target": 168, "native": "es",
        },
        "settings": {
            "lang": "en", "theme": "auto", "dailyMin": 45, "weekStart": 1,
            "notify": True, "updated": "2026-11-17T09:00:00Z",
        },
        "stage": 3,
        "log": [],
        "errs": [],
        "examDates": ["2027-06-12"],
        "overrides": {"2026-11-16": "writing", "2026-11-18": "listening"},
        "weekOverrides": {"2026-W46": {"focus": "listening"}},
        "mat": {"done": ["unit-%02d" % i for i in range(1, 30)]},
        "diag": {"taken": "2026-10-02", "reading": 18, "listening": 17,
                 "writing": 14, "speaking": 15},
    }
    for i in range(log_entries):
        doc["log"].append({
            "id": "lt%d-%04d" % (seq, i),
            "date": "2026-%02d-%02d" % ((i % 12) + 1, (i % 27) + 1),
            "skill": SKILLS[i % 5],
            "part": (i % 4) + 1,
            "kind": "mock" if i % 11 == 0 else "practice",
            "mins": 5 + (i * 7) % 40,
            "score": (i * 3) % 21,
            "note": note.format(part=(i % 4) + 1),
        })
    for i in range(24):
        doc["errs"].append({
            "id": "err%d-%03d" % (seq, i),
            "date": "2026-%02d-%02d" % ((i % 12) + 1, (i % 27) + 1),
            "skill": SKILLS[i % 5],
            "tag": ("collocation", "articles", "linkers", "spelling",
                    "paraphrase")[i % 5],
            "text": ("Wrote 'make a photo' instead of 'take a photo'; checked the "
                     "collocation list and wrote three new sentences with the "
                     "correct verb."),
            "fixed": i % 2 == 0,
        })
    return doc


def doc_bytes(seq=0):
    return json.dumps(progress_doc(seq), ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------------------
# Small HTTP helpers
# ---------------------------------------------------------------------------
def new_conn(args):
    parts = urlsplit(args.url)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if parts.scheme == "https":
        return http.client.HTTPSConnection(
            host, port, timeout=args.timeout,
            context=ssl.create_default_context())
    return http.client.HTTPConnection(host, port, timeout=args.timeout)


def fake_ip(index, pool):
    """A stable-looking IPv4 for X-Forwarded-For, from a private range."""
    n = index % max(1, pool)
    return "10.%d.%d.%d" % ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def base_headers(args, xff_index=None):
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip",
               "Connection": "close"}
    if args.xff_pool and xff_index is not None:
        headers["X-Forwarded-For"] = fake_ip(xff_index, args.xff_pool)
    return headers


def http_once(args, method, path, body=None, headers=None):
    """One request on a fresh connection. Returns (status, body bytes)."""
    conn = new_conn(args)
    try:
        hdrs = base_headers(args)
        hdrs.update(headers or {})
        conn.request(method, path, body=body, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, data
    finally:
        try:
            conn.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
def read_creds(path):
    with open(path, "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    if isinstance(obj, dict):
        obj = obj.get("users") or []
    return [c for c in obj if isinstance(c, dict) and c.get("name")]


def write_creds(path, creds):
    if not path:
        return
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(creds, fh, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _login_one(args, cred, xff_index):
    body = json.dumps({
        "name": cred["name"],
        "password": cred.get("password") or args.password,
    }).encode("utf-8")
    status, data = http_once(
        args, "POST", "/api/login", body,
        {"Content-Type": "application/json",
         "X-Forwarded-For": fake_ip(xff_index, 1 << 20)})
    if status != 200:
        raise RuntimeError("login %s -> HTTP %d %r" %
                           (cred["name"], status, data[:120]))
    obj = json.loads(data.decode("utf-8"))
    cred["token"] = obj["token"]
    cred["user_id"] = obj["id"]
    return cred


def load_creds(args):
    """Load the credentials file and log in anyone missing a token."""
    if not args.creds:
        return []
    creds = read_creds(args.creds)
    if args.users and args.users > 0:
        creds = creds[:args.users]
    missing = [c for c in creds
               if not c.get("token") or not c.get("user_id")]
    if not missing:
        return creds
    print("logging in %d credential(s) without a token..." % len(missing),
          flush=True)

    errors = []
    lock = threading.Lock()

    def worker(tid):
        for i in range(tid, len(missing), 8):
            try:
                _login_one(args, missing[i], 1000000 + i + tid)
            except Exception as exc:  # noqa: BLE001 - reported after the join
                with lock:
                    errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(tid,), daemon=True)
               for tid in range(min(8, len(missing)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        sys.exit("could not log in the seeded accounts: %s" % errors[0])
    return creds


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------
def _seed_one(args, index):
    name = "%s%d" % (args.user_prefix, index + 1)
    xff = fake_ip(index, max(args.seed, 1))
    headers = {"Content-Type": "application/json", "X-Forwarded-For": xff}
    body = json.dumps({"name": name,
                       "password": args.password}).encode("utf-8")
    status, data = http_once(args, "POST", "/api/register", body, headers)
    if status == 409:
        status, data = http_once(args, "POST", "/api/login", body, headers)
    if status != 200:
        raise RuntimeError("register %s -> HTTP %d %r" %
                           (name, status, data[:120]))
    obj = json.loads(data.decode("utf-8"))
    token, uid = obj["token"], obj["id"]
    pb = doc_bytes(index)
    pstatus, pdata = http_once(
        args, "PUT", "/api/progress?user=" + quote(uid), pb,
        {"Content-Type": "application/json",
         "Authorization": "Bearer " + token, "X-Forwarded-For": xff})
    if pstatus != 200:
        raise RuntimeError("seed progress %s -> HTTP %d %r" %
                           (name, pstatus, pdata[:120]))
    return {"name": name, "user_id": uid, "token": token,
            "password": args.password}


def seed(args):
    total = args.seed
    if total < 1:
        sys.exit("--seed expects a positive number")
    results = [None] * total
    errors = []
    lock = threading.Lock()
    done = [0]

    def run_slice(tid, nthreads):
        for i in range(tid, total, nthreads):
            try:
                rec = _seed_one(args, i)
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                with lock:
                    errors.append((i, str(exc)))
            else:
                with lock:
                    results[i] = rec
            with lock:
                done[0] += 1
                if done[0] % 50 == 0 or done[0] == total:
                    print("  seeded %d/%d" % (done[0], total), flush=True)

    nthreads = max(1, min(args.seed_threads, total))
    started = time.perf_counter()
    threads = [threading.Thread(target=run_slice, args=(tid, nthreads),
                                daemon=True)
               for tid in range(nthreads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - started
    ok = [c for c in results if c]
    doc_len = len(doc_bytes(0))
    print("seeded %d/%d users in %.1fs (payload %d bytes/account)" %
          (len(ok), total, elapsed, doc_len), flush=True)
    for index, msg in errors[:10]:
        print("  user %d failed: %s" % (index + 1, msg), file=sys.stderr)
    if len(errors) > 10:
        print("  ... %d more failures" % (len(errors) - 10), file=sys.stderr)
    write_creds(args.creds_out, ok)
    if args.creds_out:
        print("credentials written to %s" % args.creds_out, flush=True)
    return 0 if not errors else 1


# ---------------------------------------------------------------------------
# Load loop
# ---------------------------------------------------------------------------
def build_pattern(weights):
    """Weighted schedule as a list of ops (mixed scenario)."""
    values = [int(x) for x in weights.split(",")]
    if len(values) != 4 or sum(values) <= 0:
        sys.exit("--weights needs four positive integers: read,api,write,login")
    names = ("read", "api", "write", "login")
    pattern = []
    for name, weight in zip(names, values):
        pattern.extend([name] * weight)
    return tuple(pattern)


def new_local():
    return {"ops": {}}


def slot(local, op):
    s = local["ops"].get(op)
    if s is None:
        s = local["ops"][op] = {
            "lat": [], "server_ms": [], "status": {}, "timeouts": 0,
            "transport": 0, "transport_kinds": {}, "bytes": 0,
        }
    return s


def _next_request(args, creds, worker, seq, pattern):
    """Return (op, method, path, body, headers) for one request."""
    if args.scenario == "mixed":
        op = pattern[seq % len(pattern)]
    else:
        op = args.scenario
    headers = base_headers(args, worker * 104729 + seq)
    if op == "read":
        return op, "GET", "/", None, headers
    # Rotate the account per request: a stickier mapping would hit the 60
    # writes/min per-user bucket long before the server runs out of capacity.
    cred = creds[seq % len(creds)]
    if op == "login":
        body = json.dumps({
            "name": cred["name"],
            "password": cred.get("password") or args.password,
        }).encode("utf-8")
        headers["Content-Type"] = "application/json"
        return op, "POST", "/api/login", body, headers
    headers["Authorization"] = "Bearer " + cred["token"]
    if op == "write":
        headers["Content-Type"] = "application/json"
        return op, "PUT", "/api/progress?user=" + quote(cred["user_id"]), \
            args.write_body, headers
    return op, "GET", "/api/progress?user=" + quote(cred["user_id"]) + \
        "&download=1", None, headers


def run_worker(args, creds, worker, deadline, pattern, local, sequence, lock):
    while True:
        if time.perf_counter() >= deadline:
            break
        with lock:
            seq = sequence[0]
            sequence[0] = seq + 1
        op, method, path, body, headers = _next_request(
            args, creds, worker, seq, pattern)
        s = slot(local, op)
        conn = None
        started = time.perf_counter()
        try:
            conn = new_conn(args)
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            timing = resp.getheader("Server-Timing")
            data = resp.read()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            s["lat"].append(elapsed_ms)
            s["bytes"] += len(data)
            s["status"][resp.status] = s["status"].get(resp.status, 0) + 1
            if timing:
                match = SERVER_TIMING_RE.search(timing)
                if match:
                    s["server_ms"].append(float(match.group(1)))
        except (TimeoutError, socket.timeout):
            s["timeouts"] += 1
        except (OSError, http.client.HTTPException) as exc:
            s["transport"] += 1
            kind = type(exc).__name__
            s["transport_kinds"][kind] = s["transport_kinds"].get(kind, 0) + 1
        finally:
            if conn is not None:
                try:
                    conn.close()
                except OSError:
                    pass


def merge_locals(locals_):
    merged = {}
    for local in locals_:
        for op, s in local["ops"].items():
            agg = merged.setdefault(op, {
                "lat": [], "server_ms": [], "status": {}, "timeouts": 0,
                "transport": 0, "transport_kinds": {}, "bytes": 0,
            })
            agg["lat"].extend(s["lat"])
            agg["server_ms"].extend(s["server_ms"])
            for code, count in s["status"].items():
                agg["status"][code] = agg["status"].get(code, 0) + count
            agg["timeouts"] += s["timeouts"]
            agg["transport"] += s["transport"]
            for kind, count in s["transport_kinds"].items():
                agg["transport_kinds"][kind] = \
                    agg["transport_kinds"].get(kind, 0) + count
            agg["bytes"] += s["bytes"]
    return merged


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(p / 100.0 * len(ordered)) - 1)
    return ordered[index]


def summarise_op(s, elapsed):
    requests = sum(s["status"].values())
    attempts = requests + s["timeouts"] + s["transport"]
    errors = sum(n for code, n in s["status"].items() if code >= 400)
    return {
        "requests": requests,
        "attempts": attempts,
        "rps": round(attempts / elapsed, 1) if elapsed > 0 else 0.0,
        "p50_ms": round(percentile(s["lat"], 50), 1),
        "p95_ms": round(percentile(s["lat"], 95), 1),
        "p99_ms": round(percentile(s["lat"], 99), 1),
        "max_ms": round(max(s["lat"]), 1) if s["lat"] else 0.0,
        "server_p50_ms": round(percentile(s["server_ms"], 50), 1),
        "server_p95_ms": round(percentile(s["server_ms"], 95), 1),
        "errors": errors,
        "error_rate": round(errors / requests, 4) if requests else 0.0,
        "timeouts": s["timeouts"],
        "transport_errors": s["transport"],
        "transport_kinds": dict(sorted(s["transport_kinds"].items())),
        "bytes": s["bytes"],
        "status": {str(k): v for k, v in sorted(s["status"].items())},
    }


def combine_ops(ops):
    total = {
        "lat": [], "server_ms": [], "status": {}, "timeouts": 0,
        "transport": 0, "transport_kinds": {}, "bytes": 0,
    }
    for s in ops.values():
        total["lat"].extend(s["lat"])
        total["server_ms"].extend(s["server_ms"])
        for code, count in s["status"].items():
            total["status"][code] = total["status"].get(code, 0) + count
        total["timeouts"] += s["timeouts"]
        total["transport"] += s["transport"]
        for kind, count in s["transport_kinds"].items():
            total["transport_kinds"][kind] = \
                total["transport_kinds"].get(kind, 0) + count
        total["bytes"] += s["bytes"]
    return total


def _process_ticks(pid="self"):
    with open("/proc/%s/stat" % pid, "r", encoding="utf-8") as fh:
        raw = fh.read()
    fields = raw[raw.rfind(")") + 2:].split()
    return int(fields[11]) + int(fields[12])


def print_table(result):
    ops = result["ops"]
    order = [name for name in ("read", "api", "write", "login") if name in ops]
    header = ("op        reqs      rps     p50     p95     p99    errs  "
              "to  tr  status")
    print(header)
    print("-" * len(header))
    rows = [(name, ops[name]) for name in order]
    rows.append(("ALL", result["overall"]))
    for name, row in rows:
        status = ",".join("%s:%d" % (k, v)
                          for k, v in row["status"].items()) or "-"
        print("%-8s %8d %8.1f %7.1f %7.1f %7.1f %7d %3d %3d  %s" % (
            name, row["requests"], row["rps"], row["p50_ms"], row["p95_ms"],
            row["p99_ms"], row["errors"], row["timeouts"],
            row["transport_errors"], status))


def warmup(args, creds, needed):
    """One request per operation so cold paths and bad tokens show up early."""
    if not needed:
        return
    xff = 2000000
    try:
        if "read" in needed:
            http_once(args, "GET", "/", None,
                      {"X-Forwarded-For": fake_ip(xff, 1 << 20)})
        if creds and "api" in needed:
            cred = creds[0]
            status, data = http_once(
                args, "GET", "/api/progress?user=%s&download=1"
                % quote(cred["user_id"]), None,
                {"Authorization": "Bearer " + cred["token"],
                 "X-Forwarded-For": fake_ip(xff + 1, 1 << 20)})
            if status in (401, 403):
                sys.exit("warmup GET /api/progress -> HTTP %d %r"
                         % (status, data[:200]))
            if status != 200:
                print("warning: warmup GET -> HTTP %d" % status, file=sys.stderr)
        if creds and "write" in needed:
            cred = creds[0]
            status, data = http_once(
                args, "PUT", "/api/progress?user=" + quote(cred["user_id"]),
                args.write_body,
                {"Content-Type": "application/json",
                 "Authorization": "Bearer " + cred["token"],
                 "X-Forwarded-For": fake_ip(xff + 2, 1 << 20)})
            if status in (401, 403):
                sys.exit("warmup PUT /api/progress -> HTTP %d %r"
                         % (status, data[:200]))
            if status != 200:
                print("warning: warmup PUT -> HTTP %d" % status, file=sys.stderr)
        if creds and "login" in needed:
            try:
                _login_one(args, creds[0], xff + 3)
            except RuntimeError as exc:
                print("warning: warmup login: %s" % exc, file=sys.stderr)
    except (OSError, http.client.HTTPException) as exc:
        sys.exit("warmup failed: %s" % exc)


def run_load(args):
    pattern = build_pattern(args.weights)
    needed = {args.scenario} if args.scenario != "mixed" else set(pattern)
    creds = load_creds(args)
    if needed & {"api", "write", "login"} and not creds:
        sys.exit("scenario %r needs credentials: pass --creds FILE or --seed"
                 % args.scenario)
    args.write_body = doc_bytes(0)
    warmup(args, creds, needed)

    locals_ = [new_local() for _ in range(args.concurrency)]
    state = {"deadline": 0.0}
    sequence = [0]
    sequence_lock = threading.Lock()
    barrier = threading.Barrier(args.concurrency + 1)

    def worker(index):
        barrier.wait()
        run_worker(args, creds, index, state["deadline"], pattern,
                   locals_[index], sequence, sequence_lock)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True)
               for i in range(args.concurrency)]
    cpu0 = _process_ticks()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()
    state["deadline"] = started + args.duration
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(args.duration + args.timeout + 60)
    elapsed = max(1e-9, time.perf_counter() - started)
    cpu_pct = (_process_ticks() - cpu0) / CLK_TCK / elapsed * 100.0
    alive = sum(1 for thread in threads if thread.is_alive())

    merged = merge_locals(locals_)
    ops = {name: summarise_op(merged[name], elapsed)
           for name in sorted(merged)}
    overall = summarise_op(combine_ops(merged), elapsed)
    result = {
        "tool": "b2first-loadtest",
        "version": VERSION,
        "url": args.url,
        "scenario": args.scenario,
        "weights": args.weights if args.scenario == "mixed" else None,
        "concurrency": args.concurrency,
        "duration_s": args.duration,
        "elapsed_s": round(elapsed, 2),
        "users_available": len(creds),
        "xff_pool": args.xff_pool,
        "write_bytes": len(args.write_body),
        "started_at": started_at,
        "client_cpu_pct": round(cpu_pct, 1),
        "workers_alive_after_join": alive,
        "overall": overall,
        "ops": ops,
    }
    print("url=%s scenario=%s concurrency=%d duration=%ss users=%d "
          "client_cpu=%.0f%%" % (args.url, args.scenario, args.concurrency,
                                 args.duration, len(creds), cpu_pct))
    print_table(result)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.json:
        parent = os.path.dirname(os.path.abspath(args.json))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Load generator for the B2 First tracker (stdlib only).")
    parser.add_argument("--url", default="http://127.0.0.1:8088",
                        help="base URL (default: %(default)s)")
    parser.add_argument("--duration", type=float, default=30.0,
                        help="measured window in seconds (default: 30)")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="simultaneous client threads (default: 10)")
    parser.add_argument("--scenario", choices=SCENARIOS, default="mixed",
                        help="traffic shape (default: mixed)")
    parser.add_argument("--users", type=int, default=0,
                        help="how many credentials to use (0 = all)")
    parser.add_argument("--weights", "--weight", dest="weights",
                        default=DEFAULT_WEIGHTS,
                        help="mixed weights read,api,write,login "
                             "(default: %(default)s)")
    parser.add_argument("--json", metavar="PATH",
                        help="also write the JSON report to PATH")
    parser.add_argument("--creds", metavar="PATH",
                        help="credentials JSON produced by --seed")
    parser.add_argument("--password", default=os.environ.get(
        "B2_LOADTEST_PASSWORD", DEFAULT_PASSWORD),
        help="password for seeded accounts")
    parser.add_argument("--user-prefix", default="load",
                        help="account name prefix when seeding (default: load)")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="socket timeout per request in seconds")
    parser.add_argument("--xff-pool", type=int, default=0,
                        help="size of the synthetic X-Forwarded-For pool; "
                             "0 = send no XFF")
    parser.add_argument("--seed", type=int, default=0, metavar="N",
                        help="create N accounts through the API and exit")
    parser.add_argument("--seed-threads", type=int, default=8,
                        help="parallel registrations while seeding")
    parser.add_argument("--creds-out", metavar="PATH",
                        help="where --seed writes the credentials JSON")
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.duration <= 0:
        parser.error("--duration must be > 0")
    return args


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    parts = urlsplit(args.url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        sys.exit("--url must be http(s)://host[:port]")
    if args.seed:
        return seed(args)
    return run_load(args)
=======
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
>>>>>>> feat/queue-c1


if __name__ == "__main__":
    sys.exit(main())
