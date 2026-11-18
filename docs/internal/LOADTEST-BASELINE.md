# Load-test baseline — the Pi 5 ceiling, measured

Status: phase A measurement (no application changes). Tools: `tools/loadtest.py`
(stdlib load client) and `tools/loadtest_run.sh` (server + seed + ladder + /proc
sampling). Everything below was measured on the real `server.py`, with the
production code untouched.

Measurement window: **2026-11-17 12:37–12:54 UTC**.
Machine: the Pi that serves the app, also running the rest of the owner's stack
(see [Conditions](#conditions)). The absolute numbers are a **lower bound**;
the bottleneck *ranking* is the robust result.

## TL;DR

* **Sustained mixed ceiling: ~60–100 req/s, and it falls as concurrency rises**
  (102 req/s at 10 connections → 60 req/s at 200). It is not CPU-bound: peak
  CPU was 271 % of 400 %.
* **First bottleneck: the session store, not the progress JSON.** Every
  authenticated request runs `auth_from_token()` (`server.py:2204`), which takes
  `_TOKENS_LOCK`, reads **and atomically rewrites the whole `data/tokens.json`**
  just to slide `last_seen`/`exp`; every login rewrites the same file through
  `new_token()`. At ~500 sessions that rewrite costs **33.5 ms
  on the SD card** (9.8 ms on tmpfs). It serialises all authenticated traffic:
  at 200 connections, `api`/`write`/`login` all queue to **p50 ≈ 8 s** while
  `read` (no auth) keeps **5–7 ms of server time**.
* **Second bottleneck: login PBKDF2.** 600,000 iterations = **179 ms per login**
  on this Pi; 4 threads scale only 2.1×. Login-only tops out at **12–14
  logins/s**, with CPU at **214 % avg / 383 % peak** and 79.3 °C.
* **Third bottleneck: one TCP connection + one OS thread per request**
  (`HTTP/1.0`, no keep-alive). The static path plateaus at **~450–560 req/s**
  with only **5–7 ms** of handler time; a second client process or logging to
  `/dev/null` does not move it.
* No 5xx, no timeouts, no 429, RSS ≤ 61 MB in any run. Memory is not the limit.

## Conditions

| Item | Value |
| --- | --- |
| Board | Raspberry Pi 5 (BCM2712), 4× Cortex-A76 @ 2.4 GHz, 8 GB RAM |
| Storage | `/dev/mmcblk0p2` (ext4, SD/eMMC); data dir under `/var/tmp` (ext4), **not** tmpfs |
| OS / Python | Linux 6.18.34+rpt-rpi-2712 (aarch64), Python 3.13.5 |
| Thermals | 70–79 °C during the runs; 79.3 °C peak in the login-only run |
| Co-tenancy | immich, PostgreSQL, php-fpm pool, next-server, tsserver and several agent processes were running; the live app instance on `:8088` was up but idle. During part of the session a Playwright/Chromium job used ~100 % of one core and the box showed **46–74 % iowait** and full swap. |

Because the box is shared, the *same* 5-connection `read` test produced
**330, 432, 561, 581 and 896 req/s** at different moments of the session, while
the handler time stayed at 5–7 ms. Treat the throughput columns as the capacity
observed *while sharing the Pi*, not as an isolated lab number.

## What was measured

Each measurement runs the real `server.py` on a free port, with a throwaway
`B2_DATA_DIR`, `B2_REGISTER=open`, and the env-configurable anti-abuse buckets
disabled (`B2_RATE_IP_AUTH=0`, `B2_RATE_IP_ANON=0`, `B2_RATE_USER_API=0`).
The hard-coded per-IP/per-user buckets are neutralised by giving every synthetic
request its own `X-Forwarded-For` (`--xff-pool 4096`) and rotating the account
per request over the seeded pool; otherwise the run would measure the rate
limiter, not capacity.

* **Accounts**: `POST /api/register` + a 33,642-byte `PUT /api/progress` per
  account, 8 parallel registrations (400 accounts in 28–37 s). Tokens come from
  the register response, so the load run does not pay PBKDF2 for auth.
* **Snapshot per step**: after seeding, the data dir is copied once and
  restored before every step. Each rung starts from 400 sessions, no extra
  tokens, no backups and no rate-limit state left by the previous rung.
* **Client**: `threading` + `http.client`, one connection per request (what the
  server forces), gzip responses read as raw bytes, latency measured from
  `connect` to the end of the body. Server processing is read separately from
  the `Server-Timing: app;dur=` header.
* **Server metrics**: `/proc/<pid>/{stat,status,fd}` sampled at 1 Hz (CPU ticks,
  RSS, threads, FDs) plus `thermal_zone0`, by `tools/loadtest_run.sh`.

## Results

### 1. Required staircase — `mixed` 60/20/15/5, 400 accounts, 30 s per step

Command:

```bash
bash tools/loadtest_run.sh --users 400 --steps "10 25 50 100 200" \
    --duration 30 --scenario mixed --out /var/tmp/b2-results/mixed
```

| connections | req/s | p50 ms | p95 ms | p99 ms | errors | CPU avg | CPU peak | RSS MB | threads | FDs | °C |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 102.1 | 26.7 | 358.3 | 556.8 | 0.00 % | 165.9 % | 237.1 % | 50 | 11 | 17 | 75.5 |
| 25 | 84.1 | 38.8 | **985.0** | 1418.1 | 0.00 % | 131.1 % | 236.8 % | 51 | 26 | 33 | 75.5 |
| 50 | 76.9 | 64.5 | **2048.8** | 2403.9 | 0.00 % | 124.7 % | 191.3 % | 56 | 52 | 60 | 77.1 |
| 100 | 70.9 | 50.9 | **4296.6** | 5049.1 | 0.00 % | 115.1 % | 247.9 % | 56 | 102 | 109 | 75.5 |
| 200 | 59.9 | 240.1 | **9128.9** | 9581.5 | 0.00 % | 121.3 % | 271.1 % | 60 | 202 | 206 | 71.6 |

Per-operation latency (ms, client side) for the same rungs:

| connections | read p50/p95 | api p50/p95 | write p50/p95 | login p50/p95 |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 16 / 40 | 145 / 326 | 211 / 388 | 421 / 689 |
| 25 | 22 / 62 | 547 / 837 | 833 / 1130 | 882 / 1257 |
| 50 | 30 / 116 | 1397 / 2129 | 1573 / 2391 | 1736 / 2570 |
| 100 | 15 / 467 | 3235 / 4727 | 3441 / 4993 | 3473 / 4935 |
| 200 | 16 / 690 | 7996 / 9488 | 8188 / 9526 | 8191 / 9574 |

Read server time (`Server-Timing`, p50) stayed at **4.9–8.5 ms on every rung**.
Everything that touches the session store grows together to seconds: `api` and
`write` share `_auth()`, and `login` shares the same `tokens.json` lock through
`new_token()`.

Thresholds asked for:

* **p95 > 500 ms**: first crossed at **25 connections** (985 ms). At 10 it is
  358 ms. Per operation, `login` already exceeds it at 10 (689 ms).
* **errors > 1 %**: **never**. Every response was `200` in all runs; no
  timeouts, no transport errors, no 429.
* **CPU saturated**: **not in this mix** (peak 271 % of 400 %). It *does* saturate
  in the login-only run (214 % avg, 383 % peak), i.e. PBKDF2, not the mixed load.

### 2. Isolated scenarios

| scenario | conns | accounts | req/s | p50 ms | p95 ms | p99 ms | errors | CPU avg/peak | RSS MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| read (`GET /`) | 100 | 400 | 400.6 | 245.3 | 382.5 | 586.3 | 0 % | 137 / 229 % | 50 |
| read (`GET /`) | 200 | 400 | 499.2 | 273.7 | 1069.7 | 2390.0 | 0 % | 169 / 253 % | 57 |
| api (`GET /api/progress`) | 100 | 200 | 92.8 | 1045.4 | 1444.9 | 1554.6 | 0 % | 67 / 86 % | 50 |
| write (`PUT /api/progress`, 33,642 B) | 100 | 200 | 59.5 | 1482.0 | 3088.5 | 3539.4 | 0 % | 63 / 102 % | 46 |
| login (`POST /api/login`) | 25 | 200 | 12.2 | 2007.7 | 2963.5 | 3809.4 | 0 % | **214 / 383 %** | 49 |

The isolated API numbers were taken **after** the Playwright/e2e job started
(12:51–12:54 UTC); the mixed staircase (12:37–12:40) and the read staircase
(12:42–12:44) ran before it. That is why `api` (92.8 req/s, 200 sessions) is
faster than the mixed run (400 sessions): the token file is half the size. The
isolated runs actually had *more* co-tenant load, so the token count is the
dominant difference. The rewrite cost scales with the number of sessions — see
the microbenchmark below.

### 3. Static-path curve and controls

`GET /` (71,786-byte `landing.html`, re-read and gzipped per request by the
server), 10 s per point, no auth:

| connections | 5 | 10 | 25 | 50 | 100 | 200 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| req/s | 432 | 421 | 384 | 458 | 492 | 523 |
| p50 ms | 11 | 23 | 59 | 108 | 183 | 384 |

Controls at 100 connections (10 s):

| change | req/s | conclusion |
| --- | ---: | --- |
| one client process | 492 | — |
| two client processes, 50 connections each | 245 + 246 = **490** | the cap is **not** the load client |
| server stdout to `/dev/null` instead of a file | 440 | the cap is **not** the access log |
| server handler time (`Server-Timing`, p50) | **5–7 ms** | the cap is not request processing |

So the static path is limited by the per-request connection path (accept + one
thread per connection + GIL), not by rendering, logging or the client.

### 4. Microbenchmarks (the mechanism)

| Measurement | Result |
| --- | --- |
| PBKDF2-HMAC-SHA256, 600k iterations, 1 thread | **179.4 ms/op** |
| same, 4 threads (32 hashes total) | 2.71 s vs 1.44 s sequential → **2.1× speedup**, not 4× |
| `tokens.json` with 500 sessions (137,390 B): read + atomic rewrite on `/var/tmp` (ext4/SD) | **33.5 ms/op** |
| same on `/dev/shm` (tmpfs) | 9.8 ms/op |
| realistic progress payload | 33,642 B |

## Where it breaks, in order

### 1. Session store (`data/tokens.json`) — the first ceiling

`_auth()` → `auth_from_token()` runs for **every authenticated** `/api/`
request (and `new_token()` does the same rewrite for every login). To slide the
expiry it does `load_tokens()` (parse the whole file), mutates one record and
`save_tokens()` (serialise the whole file, write a tmp file, `os.replace`,
`chmod`) — all inside `_TOKENS_LOCK`. The cost is O(number of sessions) and it
is serialised across every handler thread.

Evidence:

* `read` server time is flat at 5–7 ms; `api`, `write` and `login` — the three
  operations that touch the session store — degrade **together** to p50 ≈ 8 s
  at 200 connections. The only thing they share is that lock.
* The lock is already saturated on the first rung: at 10 connections the mix
  does ~41 session-store requests/s; at ~25–27 ms per rewrite (400 sessions)
  that is **1.0–1.1 lock-seconds per wall second**, i.e. the lock is busy all
  the time while the rest of the server sits at 166 % of 400 % CPU.
* At 200 connections: ~24 session-store requests/s × ~42 ms each ≈ 200 requests
  in flight (Little's law) — exactly the number of client threads. The queue is
  the lock.
* Rewrite cost measured independently: 33.5 ms for 500 sessions on this SD
  card. With 400 sessions the mixed run measures ≈ 25–40 session-store
  requests/s. With 200 sessions the isolated `api` run reaches 92.8/s.
* **Anti-scaling**: a login mints a token, so the file grows *during* the run.
  More concurrency → more logins → bigger file → slower auth. That is why the
  mixed throughput goes **down** (102 → 60 req/s) while concurrency goes up.

### 2. Login PBKDF2 — CPU

600k iterations cost 179 ms per login and do not scale across the 4 cores
(2.1× on 4 threads). Login-only: **12–14 logins/s**, CPU **214 % avg / 383 %
peak**, 79.3 °C. In the mixed run, the 5 % login share is only 3–7 logins/s, so
it does not saturate CPU by itself, but it burns ~27 CPU-seconds per 30 s at
10 connections and it is the operation with the worst tail (p95 689 ms already
at 10 connections).

### 3. Connection/thread per request — the static path

`server.py` speaks HTTP/1.0 (`BaseHTTPRequestHandler.protocol_version` is not
overridden), so every response closes the connection and every request costs a
new TCP connection plus a new OS thread (`ThreadingHTTPServer`). The result is a
flat **~450–560 req/s** ceiling for `GET /` regardless of 5 or 200 connections,
with p50 growing linearly with concurrency, while the handler itself takes only
5–7 ms. Two parallel client processes do not increase the total, and removing
the access log does not either. The remaining cost is in the accept/thread
path, not in the app code that handles the request.

Progress writes are not the first bottleneck, but they are the second disk cost:
each `PUT` copies the previous 33 KB file into `backups/`, writes the new one,
lists the backup dir and prunes it. The isolated write run does 59.5 req/s at
100 connections, mostly waiting on the same auth serialisation.

## What this does and does not prove

* It proves the **ordering**: session store first, login CPU second,
  connection-per-request third, progress JSON later.
* It proves the session store cost is real: the 33.5 ms rewrite is an
  independent microbenchmark, and the queue arithmetic matches the measured
  latencies.
* Absolute req/s are a **lower bound** measured on a shared Pi: other services
  and other agents were using CPU and disk (46–74 % iowait during part of the
  session), and the same `read` test moved ~2× between quiet and busy minutes.
  Re-run the harness on a quiet box before quoting these numbers as the
  machine's maximum.
* The load client shares the 4 cores with the server. The client-side cap was
  ruled out for the static path (two client processes gave the same total), but
  it still inflates absolute latency a little at 200 threads.

## What this means for SQLite vs caching

1. **Do not start with progress-document caching.** The document is not what
   saturates the box; the per-request rewrite of the session file is. Caching
   `index.html`/`landing.html` would not move the authenticated ceiling.
2. **The highest-leverage change is the session store.** Either stop writing
   `tokens.json` on every request (update `last_seen` lazily / in the
   background) or move sessions to SQLite with WAL and a per-row update. That
   turns an O(sessions) 33 ms serialised rewrite into an O(1) few-ms write and
   removes the global lock. Expect the mixed/auth ceiling to move to the next
   limit (PBKDF2 on login, then the connection path).
3. **Then re-measure progress writes.** With auth fixed, the 33 KB
   backup+write per PUT and the 20-backup rotation become visible. Only then is
   it worth deciding whether progress itself deserves SQLite or a different
   backup strategy.
4. **Keep-alive is the next static win**, but it is a protocol change, not a
   storage change; it does not help the authenticated path until the token
   rewrite is gone. It was not measured here because `server.py` cannot be
   changed in this phase.

## Next phase

Phase B: replace the per-request token rewrite (session store in SQLite/WAL, or
write-behind for `last_seen`), then run this same staircase and compare against
this baseline. Success criterion for that phase: the authenticated operations
stop being the tail (mixed p95 at 100 connections well below 1 s, and no
throughput drop as concurrency rises), and the next bottleneck becomes visible
(PBKDF2 on login or the connection path).

## Reproduce

Prerequisites: none beyond the repo's Python (stdlib only). Run from the repo
root.

```bash
# Required staircase: mixed 60/20/15/5, 400 accounts, 30 s per step
bash tools/loadtest_run.sh --users 400 --steps "10 25 50 100 200" \
    --duration 30 --scenario mixed --out /var/tmp/b2-results/mixed

# Isolated scenarios
bash tools/loadtest_run.sh --users 400 --steps "100 200" --duration 30 \
    --scenario read  --out /var/tmp/b2-results/read
bash tools/loadtest_run.sh --users 200 --steps "100" --duration 30 \
    --scenario api   --out /var/tmp/b2-results/api
bash tools/loadtest_run.sh --users 200 --steps "100" --duration 30 \
    --scenario write --out /var/tmp/b2-results/write
bash tools/loadtest_run.sh --users 200 --steps "25"  --duration 30 \
    --scenario login --out /var/tmp/b2-results/login
```

Each invocation prints the per-step table, the per-operation breakdown and the
JSON report; `--out DIR` keeps `step-<conn>.json`, `step-<conn>.cpu.json` and
`summary.json`.

Manual client (useful when the server is already running):

```bash
python3 tools/loadtest.py --url http://127.0.0.1:9000 --seed 200 \
    --creds-out /tmp/creds.json
python3 tools/loadtest.py --url http://127.0.0.1:9000 --scenario mixed \
    --concurrency 100 --duration 30 --creds /tmp/creds.json --xff-pool 4096 \
    --json /tmp/mixed-100.json
```

Never point the runner at the production port (8088) unless you really mean
it: the runner refuses it without `--prod`, and `--prod` never seeds — it uses
the credentials file you give it.

## after C1

2026-11-17, this machine, temporary `B2_DEMO=1` server on loopback with the new
defaults (`B2_RATE_IP_AUTH=120/min`, `B2_REGISTER_PER_HOUR=20`,
`B2_LOGIN_IP_PER_10MIN=60`, `B2_RATE_IP_ANON=300/min`), static cache warm:

| metric | value |
| --- | --- |
| connections | 200 |
| duration | 10.24 s |
| requests | 6787 (662.6 req/s) |
| statuses | `200: 6118`, `429: 669` |
| transport errors | 0 |
| p50 | 270.8 ms |
| p95 | **404.7 ms** |
| p99 | 433.4 ms |

All 669 sheds are `/api/config` hits over the 300/min anonymous bucket; the
landing and tracker keep answering 200 with no 5xx and no dropped connection.
Re-test with `--json` for a machine-readable copy.
