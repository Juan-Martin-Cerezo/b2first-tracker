#!/usr/bin/env python3
"""Periodic access review report (ISO 27001 A.5.15/A.5.18).

Reads data/users.json and data/tokens.json read-only and prints one row per
account: a short hash of the id, creation date, last access, whether TOTP MFA
is enabled, active sessions and the internal plan. It also lists tokens that
expire within the next 7 days and accounts with no recorded access in 90 days.

Privacy rules baked in:
- user ids are printed as sha256(id)[:12], never in full;
- session tokens are never printed (only the database key hash would be, and
  even that is omitted);
- no password hash, salt, email hash or progress content is read.

Usage:
    python3 tools/access_review.py                 # markdown report
    python3 tools/access_review.py --json          # machine-readable snapshot
    python3 tools/access_review.py --json --diff previous.json
    B2_DATA_DIR=/path/to/data python3 tools/access_review.py

Exit codes: 0 = report produced, 1 = data could not be read.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("B2_DATA_DIR") or os.path.join(REPO, "data")
sys.path.insert(0, REPO)

INACTIVE_DAYS = 90
EXPIRING_DAYS = 7


def _iso(stamp):
    if not isinstance(stamp, (int, float)):
        return ""
    return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).strftime("%Y-%m-%d")


def _id_hash(uid):
    return hashlib.sha256(str(uid).encode("utf-8")).hexdigest()[:12]


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _tokens():
    data = _read_json(os.path.join(DATA, "tokens.json"), {})
    return data if isinstance(data, dict) else {}


def _plan(uid):
    try:
        import plans
        return plans.effective_plan(uid).get("plan", "service")
    except Exception:  # noqa: BLE001 - the review must still print
        return "unknown"


def build_report():
    try:
        import store
        users = store.list_users()
    except Exception as exc:  # noqa: BLE001
        print("FAIL: cannot read users: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(users, dict):
        users = {}
    tokens = _tokens()
    now = time.time()
    by_user = {}
    expiring = []
    for _key, rec in tokens.items():
        if not isinstance(rec, dict):
            continue
        uid = rec.get("user_id")
        if not uid:
            continue
        item = by_user.setdefault(uid, {"sessions": 0, "last_seen": 0.0})
        limit = rec.get("absolute_exp")
        if not isinstance(limit, (int, float)):
            limit = rec.get("issued", 0) + 90 * 86400
        if rec.get("exp", 0) >= now and now < limit:
            item["sessions"] += 1
            seen = rec.get("last_seen")
            if isinstance(seen, (int, float)):
                item["last_seen"] = max(item["last_seen"], seen)
        soon = min(x for x in (rec.get("exp"), limit) if isinstance(x, (int, float)))
        if now < soon <= now + EXPIRING_DAYS * 86400:
            expiring.append({"user": _id_hash(uid), "expires_on": _iso(soon)})

    rows = []
    inactive = []
    for uid, user in sorted(users.items()):
        if not isinstance(user, dict):
            continue
        seen = by_user.get(uid, {})
        last_seen = seen.get("last_seen") or 0
        inactive_days = None
        if last_seen:
            inactive_days = int((now - last_seen) // 86400)
        else:
            inactive_days = INACTIVE_DAYS  # never seen: at least the window
        row = {
            "id_hash": _id_hash(uid),
            "created": str(user.get("created", ""))[:10],
            "last_seen": _iso(last_seen),
            "mfa": bool(isinstance(user.get("mfa"), dict)
                        and user["mfa"].get("secret")),
            "sessions": int(seen.get("sessions", 0)),
            "plan": _plan(uid),
            "inactive_days": inactive_days,
        }
        rows.append(row)
        if inactive_days is not None and inactive_days >= INACTIVE_DAYS:
            inactive.append(row["id_hash"])

    expiring.sort(key=lambda r: (r["expires_on"], r["user"]))
    report = {
        "generated_on": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inactive_days_threshold": INACTIVE_DAYS,
        "accounts": rows,
        "inactive_accounts": inactive,
        "tokens_expiring_7d": expiring,
        "counts": {
            "accounts": len(rows),
            "mfa_enabled": sum(1 for r in rows if r["mfa"]),
            "inactive": len(inactive),
            "expiring_tokens": len(expiring),
        },
    }
    return report


def render_markdown(report):
    lines = [
        "# Access review",
        "",
        "Generated (UTC): %s" % report["generated_on"],
        "",
        "| Account (id hash) | Created | Last access | MFA | Sessions | Plan | Inactive (d) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["accounts"]:
        lines.append(
            "| `%s` | %s | %s | %s | %d | %s | %s |" % (
                row["id_hash"], row["created"] or "—", row["last_seen"] or "never",
                "yes" if row["mfa"] else "no", row["sessions"], row["plan"],
                row["inactive_days"] if row["inactive_days"] is not None else "—",
            )
        )
    counts = report["counts"]
    lines += [
        "",
        "- Accounts: %d; MFA enabled: %d; inactive >= %d days: %d."
        % (counts["accounts"], counts["mfa_enabled"],
           report["inactive_days_threshold"], counts["inactive"]),
        "- Tokens expiring within 7 days: %d." % counts["expiring_tokens"],
    ]
    if report["inactive_accounts"]:
        lines.append("- Inactive account hashes (disable, do not delete without notice): %s."
                     % ", ".join("`%s`" % h for h in report["inactive_accounts"]))
    if report["tokens_expiring_7d"]:
        lines.append("")
        lines.append("| Account (id hash) | Expires (UTC) |")
        lines.append("| --- | --- |")
        for item in report["tokens_expiring_7d"]:
            lines.append("| `%s` | %s |" % (item["user"], item["expires_on"]))
    return "\n".join(lines)


def diff_reports(old, new):
    old_accounts = {r["id_hash"]: r for r in old.get("accounts", [])}
    new_accounts = {r["id_hash"]: r for r in new.get("accounts", [])}
    added = sorted(set(new_accounts) - set(old_accounts))
    removed = sorted(set(old_accounts) - set(new_accounts))
    changed = []
    for key in sorted(set(old_accounts) & set(new_accounts)):
        before, after = old_accounts[key], new_accounts[key]
        fields = [f for f in ("mfa", "sessions", "plan")
                  if before.get(f) != after.get(f)]
        if fields:
            changed.append({"id_hash": key, "changed": fields,
                            "before": {f: before.get(f) for f in fields},
                            "after": {f: after.get(f) for f in fields}})
    return {"added": added, "removed": removed, "changed": changed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="JSON snapshot")
    parser.add_argument("--diff", metavar="OLD.json",
                        help="compare the current snapshot with a previous --json run")
    args = parser.parse_args(argv)

    report = build_report()
    if args.diff:
        old = _read_json(args.diff, None)
        if not isinstance(old, dict):
            print("FAIL: cannot read previous snapshot %s" % args.diff, file=sys.stderr)
            return 1
        report["diff_vs"] = os.path.basename(args.diff)
        report["diff"] = diff_reports(old, report)
    print(json.dumps(report, ensure_ascii=False, indent=1,
                     sort_keys=True) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
