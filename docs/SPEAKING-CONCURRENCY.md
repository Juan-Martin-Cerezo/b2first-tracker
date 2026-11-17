# Speaking: bounded upstream concurrency (phase C2)

`POST /api/speaking/turn` spent one upstream call per turn with **no cap on
simultaneous calls**. Twenty mocks opened at once parked twenty handler threads
on the provider: on the Pi 5 that ends in socket timeouts, provider `429`s and a
CPU spike, with no queue and no backpressure of our own. Per-account and
per-instance quotas were already there; concurrency was the missing dimension.

This phase adds a gate, not a new budget. Plan limits, the monthly money guard
and the per-minute buckets are untouched: everything below sits **on top** of
them.

## What changed

| Knob | Default | Meaning |
| --- | --- | --- |
| `B2_SPK_MAX_INFLIGHT` | `4` | Simultaneous upstream calls for the whole instance (turn reply, TTS, report, partner, PA all share it). |
| `B2_SPK_QUEUE_WAIT` | `8` s | How long a caller may wait for a slot before it gets `503 busy`. |
| `SPK_TURN_DEADLINE` | `SPK_TURN_TIMEOUT + 5` = `25` s | Hard budget for one turn, across both of its upstream calls. |

* **One global gate.** Every path that spends the provider key acquires the
  same slot. A caller that cannot get one within `B2_SPK_QUEUE_WAIT` is refused
  with `503 {"error":"busy","retry_after":5}` and `Retry-After: 5`, **without a
  provider call**.
* **A turn cannot hang.** The blocking stdlib socket read runs on a daemon
  worker; the handler waits at most until the deadline and then answers `504`
  with a JSON body and drops the connection. The worker releases its slot when
  the provider really answers (or its own socket timeout fires), so capacity is
  never booked against a thread that is gone. No `join()` on a stuck thread.
* **Counters in `/api/health`** under `speaking_upstream`, numbers only,
  never an account or any content:
  `inflight`, `waiting`, `peak_inflight`, `queue_rejected` (gate refusals),
  `busy_503`, `timeout_504`, `rate_limited_429`, plus `max_inflight`,
  `queue_wait_s` and `turn_deadline_s` so the operator sees the live setting.

## Measured table

Local loopback, real `server.py`, Gemini `:generateContent` stub with fixed
latency, one load account (`B2_OWNER_UIDS` so plan limits never interfere).
`tests/test_speaking_concurrency.py` reproduces the shape of the first two rows;
the numbers below were taken with a throwaway harness on the same box.

Cap 4, queue wait 8 s, upstream 1 s for every turn:

| Concurrency | Cap | Wait (s) | Upstream (s) | 200 | 503 | 504 | p50 (ms) | p95 (ms) | Peak at stub | Wall (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 4 | 8 | 1.0 | 4 | 0 | 0 | 1016 | 1018 | 4 | 1.02 |
| 8 | 4 | 8 | 1.0 | 8 | 0 | 0 | 1527 | 2030 | 4 | 2.03 |
| 12 | 4 | 8 | 1.0 | 12 | 0 | 0 | 2036 | 3035 | 4 | 3.05 |
| 20 | 4 | 8 | 1.0 | 20 | 0 | 0 | 3038 | 5042 | 4 | 5.05 |
| 20 | 4 | 2 | 3.0 | 7 | 13 | 0 | 2022 | 6027 | 4 | 6.03 |

Reading it:

* The stub never sees more than **4** simultaneous calls, whatever the client
  concurrency. Latency grows in queue order instead of the provider melting.
* With a healthy provider and an 8 s wait, 20 parallel turns all succeed:
  capacity is queued, not thrown away. p95 stays under the 25 s deadline.
* With a slow provider (3 s) and a short wait (2 s), the surplus is refused
  fast with `503 busy` + `Retry-After: 5`; the client backs off instead of
  adding a 21st thread to the pile.
* A provider stuck for 60 s answers `504` at the deadline: the worst turn in
  `tests/test_speaking_concurrency.py` is ~20 s (the server-side read timeout
  fires first), never 60 s, and no handler thread is lost.

`/api/health` after the overload row:

```json
"speaking_upstream": {
  "inflight": 0, "waiting": 0, "peak_inflight": 4,
  "queue_rejected": 13, "busy_503": 13, "timeout_504": 0,
  "rate_limited_429": 0, "max_inflight": 4,
  "queue_wait_s": 2.0, "turn_deadline_s": 25
}
```

## Verifying

```sh
cd tests
uv run --no-project --quiet python test_speaking_concurrency.py
uv run --no-project --quiet --with playwright python test_speaking_preload.py
uv run --no-project --quiet --with playwright python test_ai_guard.py
uv run --no-project --quiet --with playwright python test_ai.py
```

`test_speaking_concurrency.py` asserts three things: 12 concurrent turns against
a 1 s stub reach the provider at most `B2_SPK_MAX_INFLIGHT` times at once with no
exceptions (each response is `200` or `503` + `Retry-After`); a 60 s stuck stub
answers every turn within 30 s with `503`/`504`; and `/api/health` reports the
counters with no account id in them.
