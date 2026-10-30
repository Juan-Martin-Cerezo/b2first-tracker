#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the hash chain of data/audit.log (tamper detection).

Every audit line stores `prev` = sha256 hex of the previous raw line (UTF-8,
without the trailing newline); the first line of a fresh log uses 64 zeros.
Editing, deleting or reordering a line breaks the chain and this script exits
non-zero.

Usage:
    python3 tools/verify_audit.py [DATA_DIR] [--quiet]

DATA_DIR defaults to $DATA_DIR, then to <repo>/data. Exit codes:
    0 = chain intact (a rotated head is reported but not a failure)
    1 = broken chain (bad prev, missing prev, invalid JSON)
    2 = no audit log found
"""
import hashlib
import json
import os
import sys

GENESIS = "0" * 64


def audit_paths(data_dir):
    """Oldest first: audit.log.1 (rotated) then audit.log (current)."""
    base = os.path.join(data_dir, "audit.log")
    return [p for p in (base + ".1", base) if os.path.exists(p)]


def verify(paths):
    """Return (ok, checked, errors, notes). Never raises on a corrupt line.

    Lines written before the chain existed have no `prev`: they are accepted
    only as a *prefix* and reported as unverifiable history. The first chained
    line must link to the previous raw line (the transition is verified), and
    from then on every `prev` must match sha256 of the previous line.
    """
    errors = []
    notes = []
    checked = 0
    legacy = 0
    expected = None          # sha256 of the previous line, once one was seen
    seen_chained = False
    rotated_head = len(paths) > 1

    for path in paths:
        try:
            handle = open(path, "rb")
        except OSError as exc:
            errors.append(f"{path}: cannot read ({exc})")
            continue
        with handle:
            for lineno, raw in enumerate(handle, 1):
                line = raw.rstrip(b"\r\n")
                if not line.strip():
                    continue
                where = f"{os.path.basename(path)}:{lineno}"
                try:
                    obj = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    errors.append(f"{where}: not valid JSON")
                    continue
                if not isinstance(obj, dict):
                    errors.append(f"{where}: not a JSON object")
                    continue
                prev = obj.get("prev")
                if prev is None:
                    if seen_chained:
                        errors.append(f"{where}: missing prev field")
                    else:
                        legacy += 1
                    expected = hashlib.sha256(line).hexdigest()
                    checked += 1
                    continue
                if not seen_chained:
                    seen_chained = True
                    if expected is None:
                        if prev != GENESIS and not rotated_head:
                            errors.append(f"{where}: first line prev is not {GENESIS}")
                        elif prev != GENESIS:
                            notes.append(
                                f"{where}: chain head is older than the retained "
                                "rotation window (cannot verify before it)")
                    elif prev != expected:
                        errors.append(
                            f"{where}: prev mismatch at the legacy/chain boundary "
                            f"(expected {expected[:16]}…, got {str(prev)[:16]}…)")
                elif prev != expected:
                    errors.append(
                        f"{where}: prev mismatch (expected {expected[:16]}…, "
                        f"got {str(prev)[:16]}…)")
                expected = hashlib.sha256(line).hexdigest()
                checked += 1
    if legacy:
        notes.append(f"{legacy} line(s) predate the hash chain (unverifiable prefix)")
    return not errors, checked, errors, notes


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    quiet = "--quiet" in argv[1:]
    data_dir = args[0] if args else os.environ.get("DATA_DIR", "")
    if not data_dir:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    paths = audit_paths(data_dir)
    if not paths:
        print(f"no audit log under {data_dir}", file=sys.stderr)
        return 2
    ok, checked, errors, notes = verify(paths)
    for note in notes:
        print("NOTE " + note)
    for err in errors:
        print("FAIL " + err)
    if ok:
        print(f"OK audit chain intact ({checked} lines, {len(paths)} file(s))")
        return 0
    print(f"FAIL audit chain broken ({len(errors)} problem(s), {checked} lines checked)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
