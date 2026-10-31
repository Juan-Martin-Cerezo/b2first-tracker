#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate and report the real graded samples used to calibrate the marker.

Reads material/writing-samples.json, the Cambridge-graded responses that
prompts.py turns into the compact examiner-calibration block. It checks that
every sample carries the four subscale marks (0-5) and a verbatim examiner
comment, then prints samples per task type, the overall band distribution and
the subscale means.

Stdlib only. Read-only: material/ is never written.

Usage:
    python3 tools/calibrate.py [--path FILE] [--strict]

Exit codes:
    0 = file valid (warnings are allowed unless --strict)
    1 = broken file (unreadable, invalid JSON, bad schema, bad mark)
    2 = only warnings found, and --strict was requested
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "material" / "writing-samples.json"
SUBSCALES = (
    ("content", "Content"),
    ("communicative_achievement", "Communicative Achievement"),
    ("organisation", "Organisation"),
    ("language", "Language"),
)

sys.path.insert(0, str(ROOT))
try:  # the app's genres, so this report cannot drift from the marker
    from prompts import CALIBRATION_EXEMPLARS, TASK_ALIASES, TASK_TYPES
except Exception:  # pragma: no cover - report must still work standalone
    CALIBRATION_EXEMPLARS = {}
    TASK_TYPES = ("essay", "article", "report", "review", "email")
    TASK_ALIASES = {"email/letter": "email", "letter": "email"}


def normalise_task_type(value):
    task_type = str(value or "").strip().lower()
    return TASK_ALIASES.get(task_type, task_type)


class Broken(Exception):
    """The samples file cannot be used as calibration."""


def load(path):
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Broken(f"cannot read {path}: {exc}")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise Broken(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        raise Broken("top level must be a JSON object")
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise Broken("`samples` must be a non-empty list")
    return data


def _is_mark(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 5


def check_samples(data):
    """Return (errors, warnings). Errors make the file unusable."""
    errors, warnings = [], []
    for index, sample in enumerate(data["samples"]):
        where = f"samples[{index}]"
        if not isinstance(sample, dict):
            errors.append(f"{where}: not an object")
            continue

        task_type = sample.get("task_type")
        if not isinstance(task_type, str) or not task_type.strip():
            errors.append(f"{where}: missing task_type")

        score = sample.get("score")
        if not isinstance(score, dict):
            errors.append(f"{where}: missing score object")
            score = {}

        marks = []
        for key, label in SUBSCALES:
            mark = score.get(key)
            if mark is None:
                warnings.append(f"{where}: missing {label} mark")
            elif not _is_mark(mark):
                errors.append(f"{where}: {label} mark must be an integer 0-5, got {mark!r}")
            else:
                marks.append(mark)

        comment = sample.get("examiner_comment")
        if not isinstance(comment, str) or not comment.strip():
            warnings.append(f"{where}: missing examiner_comment")

        if len(marks) == len(SUBSCALES):
            overall = score.get("overall")
            if overall is None:
                warnings.append(f"{where}: missing overall band")
            elif (isinstance(overall, bool)
                  or not isinstance(overall, (int, float))
                  or not 0 <= overall <= 5):
                errors.append(f"{where}: overall band must be a number 0-5, got {overall!r}")
            else:
                mean = sum(marks) / len(marks)
                if abs(float(overall) - mean) > 0.01:
                    warnings.append(
                        f"{where}: overall {overall:g} differs from subscale mean {mean:g}"
                    )
    return errors, warnings


def _overall(sample):
    try:
        return float((sample.get("score") or {}).get("overall") or 0)
    except (TypeError, ValueError):
        return 0.0


def check_calibration(data):
    """Warn when the block in prompts.py no longer matches the samples."""
    if not CALIBRATION_EXEMPLARS:
        return []
    warnings = []
    by_type = {}
    for sample in data["samples"]:
        if not isinstance(sample, dict):
            continue
        task_type = normalise_task_type(sample.get("task_type"))
        if task_type:
            by_type.setdefault(task_type, []).append(sample)

    for task_type, exemplar in CALIBRATION_EXEMPLARS.items():
        samples = by_type.get(task_type)
        if not samples:
            continue
        best = max(samples, key=_overall)
        score = best.get("score") if isinstance(best.get("score"), dict) else {}
        marks = tuple(score.get(key) for key, _label in SUBSCALES)
        expected = tuple(exemplar["marks"])
        band = _band_label(best)
        expected_band = f"Band {exemplar['band']}"
        if marks != expected or band != expected_band:
            warnings.append(
                f"prompts.py {task_type} exemplar is stale: file has {band} "
                f"{marks}, prompt says {expected_band} {expected}"
            )
    return warnings


def _band_label(sample):
    score = sample.get("score") if isinstance(sample, dict) else None
    if not isinstance(score, dict):
        return "unknown"
    label = score.get("band_label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    overall = score.get("overall")
    return f"Band {overall:g}" if isinstance(overall, (int, float)) else "unknown"


def _band_order(label):
    digits = "".join(ch for ch in label if ch.isdigit() or ch == ".")
    try:
        return float(digits)
    except ValueError:
        return -1.0


def report(data, path):
    samples = [sample for sample in data["samples"] if isinstance(sample, dict)]
    print(f"File: {path}")
    print(f"Samples: {len(samples)}")

    per_type = Counter(
        normalise_task_type(sample["task_type"])
        for sample in samples
        if isinstance(sample.get("task_type"), str) and sample["task_type"].strip()
    )
    app_types = {key: count for key, count in per_type.items() if key in TASK_TYPES}
    other_types = {key: count for key, count in per_type.items() if key not in TASK_TYPES}
    print("Per task type:")
    for task_type, count in sorted(app_types.items()):
        print(f"  {task_type:<10} {count}")
    if other_types:
        print("Other sample types (not graded by the app):")
        for task_type, count in sorted(other_types.items()):
            print(f"  {task_type:<10} {count}")

    bands = Counter(_band_label(sample) for sample in samples)
    print("Band distribution (overall):")
    for band in sorted(bands, key=_band_order, reverse=True):
        print(f"  {band:<10} {bands[band]}")

    print("Subscale means:")
    for key, label in SUBSCALES:
        values = [
            sample["score"][key]
            for sample in samples
            if isinstance(sample.get("score"), dict) and _is_mark(sample["score"].get(key))
        ]
        if values:
            print(f"  {label:<26} {sum(values) / len(values):.2f} (n={len(values)})")

    missing = [task_type for task_type in TASK_TYPES if task_type not in per_type]
    print(f"Coverage: {len(TASK_TYPES) - len(missing)}/{len(TASK_TYPES)} task types")
    if missing:
        print(f"  no sample: {', '.join(missing)}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate the Cambridge writing calibration samples."
    )
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH,
                        help=f"samples file (default: {DEFAULT_PATH})")
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero when there are warnings")
    args = parser.parse_args(argv)

    try:
        data = load(args.path)
    except Broken as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    report(data, args.path)
    errors, warnings = check_samples(data)
    warnings += check_calibration(data)
    if CALIBRATION_EXEMPLARS:
        try:
            import prompts
            size = len(prompts.CALIBRATION)
            if size > 1200:
                warnings.append(
                    f"prompts.py CALIBRATION is {size} characters (budget ~1200)"
                )
        except Exception:  # pragma: no cover - already imported above
            pass
    for warning in warnings:
        print(f"WARN {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)

    if errors:
        return 1
    if warnings and args.strict:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
