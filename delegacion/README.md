# Delegated phase loop

How project phases are handed to coding agents and verified. The phase prompts
(`prompt-faseNN.md`) are in Spanish and stay as they are; this README is the map.

## Running a phase

```bash
delegacion/run-fase.sh <fase> [agy|cc]
```

- `delegacion/prompt-fase<NN>.md` is the prompt sent to the agent.
- `delegacion/queue.json` lists every phase with the test suites that gate it and its status
  (`done` / `pending`).
- State is written to `~/.cache/b2f/deleg.json` (fase, harness, verdict, log path, timestamps);
  a watchdog that reads it every 10 minutes re-runs or switches harness as needed. Logs land in
  `~/.cache/b2f/fase<NN>-<harness>-<timestamp>.log`.

## Harness chain

`agy gemini-4-argon-medium` runs first. When it runs out of quota (the runner exits with code 2
on `cuota_agotada`), the watchdog falls back to `command-code -m xiaomi/mimo-v2.6-pro`. Both
models are overridable with `AGY_MODEL` and `CC_MODEL`.

Hard cap: **75 minutes** per agent run (`timeout 4500` on the command-code branch;
`--print-timeout 45m` on agy), so a hung agent cannot leave a phase open forever.

## Gates

1. **Baseline before launching**: `node --check` on the JS extracted from `index.html`, and
   `GET /` on the live service must answer `200`. A red baseline blocks the run
   (verdict `blocked`, nothing is launched).
2. **After the agent**: any uncommitted leftovers are rescued into a
   `wip(delegacion): ...` commit; then the hard verification runs — `RUN_TESTS` (default
   `test_sync.py test_personalization.py`, up to 300 s each) must pass.
3. **Verdicts** recorded in `deleg.json`: `ok`, `sin_commits` (nothing committed),
   `js_roto` (broken JS), `cuota_agotada` (quota exhausted — switch harness),
   `tests_rojo` (project suites failed), `exit_<code>` (agent itself failed).
