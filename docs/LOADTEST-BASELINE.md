# Load-test baseline

Mixed anonymous load: one public IP, N keep-alive connections, each alternating
between `/` (landing), `/app` (tracker) and `/api/config` (cheap anonymous API).
Run it against a real, warm server:

```sh
python3 tools/loadtest.py --url http://127.0.0.1:8088 \
    --connections 200 --duration 10
```

The tool is stdlib-only. It reports throughput, status counts, transport
failures and p50/p95/p99 latency. Percentiles cover **served** answers only:
`429`/`503` are counted as load shedding, because their near-zero latency would
otherwise flatter the result. Exit code is non-zero on any 5xx or transport
error, never on a clean 429.

## Baseline (phase A)

Not recorded in this worktree: `docs/LOADTEST-BASELINE.md`, `tools/loadtest.py`
and phase A's measurements were not present here (`git log --all` has no
`LOADTEST-BASELINE`). The reference ceiling that does exist is
`tests/test_capacity.py`: 100 clients, cache ON, p95 under 700 ms with zero
429/503. That suite disables the IP buckets to isolate capacity, so it is not
directly comparable to the mixed run below.

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
