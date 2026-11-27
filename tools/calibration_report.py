#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the writing calibration fixtures against the configured AI provider.

Reads material/writing-calibration/expected.json and runs each essay through
server.run_writing_pipeline (the exact audit -> score -> guardrails -> optional
re-score pipeline used by /api/ai/writing). Loads provider settings from
~/.config/b2first/ai.env (or --env) without ever printing secrets.

Stdlib only.

Usage:
    python3 tools/calibration_report.py [--dry-run] [--baseline] [--env FILE]
"""
import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "material" / "writing-calibration"
DEFAULT_ENV = Path.home() / ".config" / "b2first" / "ai.env"
CRITERIA = ("content", "communicative_achievement", "organisation", "language")
SHORT_LABELS = {
    "content": "C",
    "communicative_achievement": "CA",
    "organisation": "O",
    "language": "L",
}

sys.path.insert(0, str(ROOT))
import prompts  # noqa: E402
import server as S  # noqa: E402
import writing_grade as wg  # noqa: E402


def load_env_file(path):
    """Parse simple KEY=VALUE lines from an env file without mutating os.environ."""
    env = {}
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return env
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            env[k] = v
    return env


def resolve_provider(env_path):
    """Resolve provider wire, base URL, model, and API key (same defaults as server.py)."""
    file_env = load_env_file(env_path)

    def get(key, default=""):
        return (os.environ.get(key) or file_env.get(key) or default).strip()

    wire = (get("B2_AI_PROVIDER", S.DEFAULT_AI_PROVIDER) or S.DEFAULT_AI_PROVIDER).lower()
    if wire not in ("deepseek", "gemini"):
        raise SystemExit(f"Unsupported B2_AI_PROVIDER: {wire!r}")
    default_base = S.DEFAULT_DEEPSEEK_BASE if wire == "deepseek" else S.DEFAULT_GEMINI_BASE
    default_model = S.DEFAULT_DEEPSEEK_MODEL if wire == "deepseek" else S.DEFAULT_GEMINI_MODEL
    base = get("B2_AI_BASE", default_base)
    model = get("B2_AI_MODEL", default_model)
    api_key = get("B2_AI_KEY", "")
    return wire, base, model, api_key


def check_must(must, bands, expected, guards_applied):
    """Evaluate all discriminating `must` assertions for one fixture."""
    failures = []
    if not isinstance(must, dict):
        return failures
    if "max_abs_deviation" in must:
        lim = int(must["max_abs_deviation"])
        for k in CRITERIA:
            if abs(bands[k] - expected[k]) > lim:
                failures.append(f"{SHORT_LABELS[k]}={bands[k]} deviates >{lim} from {expected[k]}")
    for k in CRITERIA:
        if f"{k}_max" in must and bands[k] > int(must[f"{k}_max"]):
            failures.append(f"{SHORT_LABELS[k]}={bands[k]} > max {must[f'{k}_max']}")
        if f"{k}_min" in must and bands[k] < int(must[f"{k}_min"]):
            failures.append(f"{SHORT_LABELS[k]}={bands[k]} < min {must[f'{k}_min']}")
    if must.get("at_least_two_criteria_at_or_below_2"):
        n_low = sum(1 for k in CRITERIA if bands[k] <= 2)
        if n_low < 2:
            failures.append(f"only {n_low} criteria <= 2 (need >= 2)")
    for req_guard in must.get("guards_include") or []:
        if req_guard not in guards_applied:
            failures.append(f"guard {req_guard!r} not in {guards_applied}")
    return failures


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil((p / 100.0) * len(ordered)) - 1))
    return ordered[idx]


def run_baseline_single_call(clean_text, kind, task_prompt, base, api_key, model, wire):
    """Single-call measurement (no audit, no guardrails, no re-score) for before/after comparison."""
    student_block, _nonce = prompts.student_message(
        S._fit_ai_text(clean_text), kind, task_prompt=task_prompt or None
    )
    payload = S._build_writing_payload(prompts.WRITING_SCORE_SYSTEM, student_block, model, wire)
    t0 = time.monotonic()
    up_json, up_err = S._provider_complete(base, api_key, model, payload, wire=wire)
    wall = round(time.monotonic() - t0, 3)
    usage = S._extract_writing_usage(up_json, wire)
    bands = None
    if not up_err and up_json:
        txt = S._extract_writing_text(up_json, wire)
        if txt:
            txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt.strip())
            try:
                obj = json.loads(txt)
                val = S._validate_ai_payload(obj)
                if val:
                    bands = val["bands"]
            except (ValueError, TypeError):
                pass
    return {"wall_s": wall, "usage": usage, "bands": bands, "error": up_err}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run writing calibration fixtures against the AI provider.")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts and fixture list without calling the API.")
    parser.add_argument("--baseline", action="store_true", help="Also run single-call baseline for latency/cost comparison.")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV, help=f"Env file with provider config (default: {DEFAULT_ENV}).")
    parser.add_argument("--cases", default="", help="Optional comma-separated substring filter on fixture filenames.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional path to dump detailed JSON results.")
    args = parser.parse_args(argv)

    spec = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))
    task_prompt = spec["task"]
    cases = spec["cases"]
    if args.cases:
        filters = [f.strip().lower() for f in args.cases.split(",") if f.strip()]
        cases = [c for c in cases if any(f in c["file"].lower() for f in filters)]

    if args.dry_run:
        print("=== DRY RUN ===")
        print(f"Task prompt: {task_prompt}")
        print(f"Audit system prompt: {len(prompts.WRITING_AUDIT_SYSTEM)} chars")
        print(f"Score system prompt: {len(prompts.WRITING_SCORE_SYSTEM)} chars")
        print("\n--- WRITING_AUDIT_SYSTEM ---")
        print(prompts.WRITING_AUDIT_SYSTEM)
        print("\n--- WRITING_SCORE_SYSTEM ---")
        print(prompts.WRITING_SCORE_SYSTEM)
        print("\n--- FIXTURES ---")
        for c in cases:
            text = (FIXTURE_DIR / c["file"]).read_text(encoding="utf-8")
            facts = wg.text_facts(text)
            exp = "/".join(str(c["expected"][k]) for k in CRITERIA)
            print(
                f"  {c['file']:<30} words={facts['words']:<3} paras={facts['paragraphs']} "
                f"contr={len(facts['contractions'])} inf={len(facts['informal_markers'])} "
                f"form={len(facts['formal_markers'])} expected={exp}"
            )
        return 0

    wire, base, model, api_key = resolve_provider(args.env)
    if not api_key:
        print(f"ERROR: B2_AI_KEY not found in environment or {args.env}", file=sys.stderr)
        return 1

    print(f"Provider: {wire} | Model: {model} | Fixtures: {len(cases)}")
    print(f"Task: {task_prompt}\n")

    rows = []
    baseline_rows = []
    abs_errors = {k: [] for k in CRITERIA}
    must_failed_any = False

    header = (
        f"{'Case':<28} {'Expected':<10} {'Got':<10} {'Must':<6} "
        f"{'Calls':<5} {'Audit':<5} {'Clps':<5} {'Wall':<6} {'Tok(in/out)':<13} Guards"
    )
    print(header)
    print("-" * len(header))

    for c in cases:
        raw_text = (FIXTURE_DIR / c["file"]).read_text(encoding="utf-8")
        clean_text = S._sanitize_ai_text(raw_text)
        t0 = time.monotonic()
        status, resp, _leak, metrics = S.run_writing_pipeline(
            clean_text, "Essay", task_prompt, base, api_key, model, wire, collect_metrics=True
        )
        total_wall = round(time.monotonic() - t0, 3)

        if status != 200 or "bands" not in resp:
            must_failed_any = True
            print(f"{c['file']:<28} ERROR status={status} resp={resp}")
            rows.append({"file": c["file"], "error": resp, "status": status, "wall_s": total_wall})
            continue

        bands = resp["bands"]
        expected = c["expected"]
        guards = resp.get("guards_applied") or []
        must_errs = check_must(c.get("must"), bands, expected, guards)
        if must_errs:
            must_failed_any = True

        for k in CRITERIA:
            abs_errors[k].append(abs(bands[k] - expected[k]))

        call_list = (metrics or {}).get("calls") or []
        tok_in = sum(item["usage"]["prompt_tokens"] for item in call_list)
        tok_out = sum(item["usage"]["completion_tokens"] for item in call_list)

        exp_s = "-".join(str(expected[k]) for k in CRITERIA)
        got_s = "-".join(str(bands[k]) for k in CRITERIA)
        must_s = "PASS" if not must_errs else "FAIL"
        aud_s = "yes" if resp.get("audit_used") else "no"
        clps_s = "yes" if resp.get("collapsed") else "no"
        g_s = ",".join(guards) if guards else "-"

        print(
            f"{c['file']:<28} {exp_s:<10} {got_s:<10} {must_s:<6} "
            f"{len(call_list):<5} {aud_s:<5} {clps_s:<5} {total_wall:<6.2f} "
            f"{tok_in}/{tok_out:<7} {g_s}"
        )
        if must_errs:
            for me in must_errs:
                print(f"    MUST FAIL: {me}")

        rows.append({
            "file": c["file"],
            "expected": expected,
            "got": bands,
            "must_ok": not must_errs,
            "must_errors": must_errs,
            "guards_applied": guards,
            "audit_used": resp.get("audit_used"),
            "collapsed": resp.get("collapsed"),
            "audit": resp.get("audit"),
            "facts": resp.get("facts"),
            "wall_s": total_wall,
            "calls": len(call_list),
            "prompt_tokens": tok_in,
            "completion_tokens": tok_out,
        })

        if args.baseline:
            b_res = run_baseline_single_call(clean_text, "Essay", task_prompt, base, api_key, model, wire)
            baseline_rows.append({"file": c["file"], **b_res})

    print()
    mae_per_criterion = {}
    all_errs = []
    for k in CRITERIA:
        vals = abs_errors[k]
        mae = sum(vals) / len(vals) if vals else 99.0
        mae_per_criterion[k] = mae
        all_errs.extend(vals)
        print(f"MAE {k:<26}: {mae:.3f}")
    overall_mae = sum(all_errs) / len(all_errs) if all_errs else 99.0
    print(f"MAE {'overall':<26}: {overall_mae:.3f}")

    ok_rows = [r for r in rows if "got" in r]
    if ok_rows:
        walls = [r["wall_s"] for r in ok_rows]
        calls_n = [r["calls"] for r in ok_rows]
        avg_in = sum(r["prompt_tokens"] for r in ok_rows) / len(ok_rows)
        avg_out = sum(r["completion_tokens"] for r in ok_rows) / len(ok_rows)
        # DeepSeek-V3 reference pricing (cache miss): $0.27/1M input, $1.10/1M output
        est_cost = (avg_in * 0.27 + avg_out * 1.10) / 1_000_000.0
        print(
            f"\nPipeline latency/cost (n={len(ok_rows)}): "
            f"mean={sum(walls)/len(walls):.2f}s  p95={percentile(walls, 95):.2f}s  "
            f"max_calls={max(calls_n)}  avg_tokens={avg_in:.0f} in / {avg_out:.0f} out  "
            f"est_cost=${est_cost:.5f}/correction"
        )

    if baseline_rows:
        b_ok = [r for r in baseline_rows if not r.get("error")]
        if b_ok:
            b_walls = [r["wall_s"] for r in b_ok]
            b_in = sum(r["usage"]["prompt_tokens"] for r in b_ok) / len(b_ok)
            b_out = sum(r["usage"]["completion_tokens"] for r in b_ok) / len(b_ok)
            b_cost = (b_in * 0.27 + b_out * 1.10) / 1_000_000.0
            print(
                f"Baseline single-call (n={len(b_ok)}):  "
                f"mean={sum(b_walls)/len(b_walls):.2f}s  p95={percentile(b_walls, 95):.2f}s  "
                f"avg_tokens={b_in:.0f} in / {b_out:.0f} out  "
                f"est_cost=${b_cost:.5f}/correction"
            )
            if ok_rows:
                p95_add = percentile([r["wall_s"] for r in ok_rows], 95) - percentile(b_walls, 95)
                print(f"Delta p95 latency: {p95_add:+.2f}s")

    if args.json_out:
        args.json_out.write_text(
            json.dumps(
                {
                    "provider": wire,
                    "model": model,
                    "mae": mae_per_criterion,
                    "overall_mae": overall_mae,
                    "rows": rows,
                    "baseline": baseline_rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    mae_failed = any(v > 0.5 for v in mae_per_criterion.values()) or overall_mae > 0.5
    if mae_failed or must_failed_any:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
