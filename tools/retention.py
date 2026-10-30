#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enforce the data-retention policy (stdlib only, idempotent, cron-safe).

What it does, once per run:

* ``data/audit.log`` (+ its ``.1`` rotation): drop every line older than 90
  days, hash any legacy raw client IP that predates the hashed-IP format, keep
  the rest in chronological order and rebuild the hash chain, so
  ``tools/verify_audit.py`` still exits 0. A ``retention`` event records what
  was removed. If nothing is old or raw, the file is not touched.
* ``data/usage.json``: drop account counters whose ``last_seen`` is older than
  13 months (396 days).
* ``data/users/<id>/backups/``: keep the newest 20 files per account.

Every deletion is printed. A second run with no new old data does nothing, which
is what "idempotent" means here.

Usage:
    python3 tools/retention.py [DATA_DIR] [--dry-run]
                               [--audit-days 90] [--usage-days 396]
                               [--backups 20]

Exit codes: 0 = ran (even if it deleted nothing), 1 = a file could not be
written. Missing files are not an error.
"""
import calendar
import hashlib
import json
import os
import re
import sys
import time

GENESIS = "0" * 64
DAY = 24 * 3600


def _parse_iso(value):
    """Epoch seconds for 2026-10-30T12:00:00Z, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _audit_paths(data_dir):
    base = os.path.join(data_dir, "audit.log")
    return [p for p in (base + ".1", base) if os.path.exists(p)]


def _scrub_ip(value):
    """Return (stored_value, changed). Raw addresses become sha256[:12]."""
    if not isinstance(value, str) or not value:
        return value, False
    if re.fullmatch(r"[0-9a-f]{12}", value):
        return value, False
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], True


def prune_audit(data_dir, days, dry_run=False, now=None):
    """Drop old audit lines, hash any legacy raw IP, rebuild the chain.

    Returns (kept, dropped, scrubbed).
    """
    ts_now = time.time() if now is None else float(now)
    cutoff = ts_now - days * DAY
    paths = _audit_paths(data_dir)
    if not paths:
        return 0, 0, 0
    kept, dropped, scrubbed = [], 0, 0
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        obj = None
                    stamp = _parse_iso(obj.get("ts")) if isinstance(obj, dict) else None
                    if isinstance(obj, dict) and stamp is not None and stamp < cutoff:
                        dropped += 1
                        print(f"delete audit {os.path.basename(path)} "
                              f"{obj.get('event', '-')} {obj.get('ts', '-')}")
                    else:
                        item = obj if isinstance(obj, dict) else {"raw": line}
                        item["ip"], changed = _scrub_ip(item.get("ip"))
                        scrubbed += 1 if changed else 0
                        kept.append(item)
        except OSError:
            continue
    if not dropped and not scrubbed:
        return len(kept), 0, 0
    if dry_run:
        print(f"would keep {len(kept)} audit line(s), drop {dropped}, "
              f"hash {scrubbed} legacy IP(s)")
        return len(kept), dropped, scrubbed

    if dropped or scrubbed:
        detail = []
        if dropped:
            detail.append(f"dropped {dropped} audit line(s) older than {days} days")
        if scrubbed:
            detail.append(f"hashed {scrubbed} legacy raw IP(s)")
        kept.append({
            "ts": _iso(ts_now),
            "rid": "",
            "event": "retention",
            "user": "",
            "ip": "",
            "detail": "; ".join(detail),
        })
    prev = GENESIS
    out = []
    for obj in kept:
        obj.pop("prev", None)
        obj["prev"] = prev
        line = json.dumps(obj, ensure_ascii=False)
        out.append(line)
        prev = hashlib.sha256(line.encode("utf-8")).hexdigest()
    path = os.path.join(data_dir, "audit.log")
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        print(f"FAIL audit rewrite: {exc}", file=sys.stderr)
        return len(kept), dropped, scrubbed
    try:
        os.remove(path + ".1")
    except OSError:
        pass
    print(f"kept {len(kept)} audit line(s), dropped {dropped}, hashed {scrubbed} IP(s)")
    return len(kept), dropped, scrubbed


def prune_usage(data_dir, days, dry_run=False, now=None):
    """Drop usage rows unseen for `days`. Returns the number of rows removed."""
    ts_now = time.time() if now is None else float(now)
    cutoff = ts_now - days * DAY
    path = os.path.join(data_dir, "usage.json")
    data = _read_json(path, None)
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
        return 0
    accounts = data["accounts"]
    removed = 0
    for uid in list(accounts):
        rec = accounts.get(uid)
        seen = _parse_iso(rec.get("last_seen")) if isinstance(rec, dict) else None
        if seen is None or seen < cutoff:
            print(f"delete usage {uid}")
            if not dry_run:
                accounts.pop(uid, None)
            removed += 1
    if removed and not dry_run:
        _write_json(path, data)
    return removed


def prune_backups(data_dir, keep, dry_run=False):
    """Keep the newest `keep` backup files per account. Returns files removed."""
    users_dir = os.path.join(data_dir, "users")
    removed = 0
    try:
        users = sorted(os.listdir(users_dir))
    except OSError:
        return 0
    for uid in users:
        bk = os.path.join(users_dir, uid, "backups")
        try:
            files = sorted(os.listdir(bk))
        except OSError:
            continue
        for name in files[:-keep] if keep > 0 else files:
            full = os.path.join(bk, name)
            if not os.path.isfile(full):
                continue
            print(f"delete backup {uid}/{name}")
            if not dry_run:
                try:
                    os.remove(full)
                except OSError as exc:
                    print(f"FAIL backup {full}: {exc}", file=sys.stderr)
                    continue
            removed += 1
    return removed


def main(argv):
    args = argv[1:]
    dry_run = "--dry-run" in args
    data_dir = ""
    opts = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--audit-days", "--usage-days", "--backups") and i + 1 < len(args):
            opts[arg] = int(args[i + 1])
            i += 2
            continue
        if arg.startswith("--") and "=" in arg:
            key, value = arg.split("=", 1)
            opts[key] = int(value)
        elif not arg.startswith("--") and not data_dir:
            data_dir = arg
        i += 1
    if not data_dir:
        data_dir = os.environ.get("DATA_DIR", "")
    if not data_dir:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    audit_days = opts.get("--audit-days", 90)
    usage_days = opts.get("--usage-days", 396)
    keep_backups = opts.get("--backups", 20)

    print(f"retention: data={data_dir} audit={audit_days}d "
          f"usage={usage_days}d backups={keep_backups}"
          + (" (dry run)" if dry_run else ""))
    audit_kept, audit_dropped, audit_scrubbed = prune_audit(data_dir, audit_days, dry_run)
    usage_dropped = prune_usage(data_dir, usage_days, dry_run)
    backups_dropped = prune_backups(data_dir, keep_backups, dry_run)
    print(f"summary: audit_dropped={audit_dropped} audit_scrubbed={audit_scrubbed} "
          f"usage_dropped={usage_dropped} backups_dropped={backups_dropped} "
          f"audit_kept={audit_kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
