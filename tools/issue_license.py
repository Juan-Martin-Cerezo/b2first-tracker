#!/usr/bin/env python3
"""Owner tool: issue and list pro activation codes (phase 31).

Usage:
    python3 tools/issue_license.py pro 30           # 30 days  -> FT-PRO-1M-...
    python3 tools/issue_license.py pro 90           # 90 days  -> FT-PRO-3M-...
    python3 tools/issue_license.py pro 0 --expire-now   # instantly expired (tests)
    python3 tools/issue_license.py --list           # issued codes (hashes only)
    python3 tools/issue_license.py --gen-secret     # print a fresh B2_LICENSE_SECRET

The code is printed alone on stdout (pipe it), details go to stderr.

The signing secret comes from B2_LICENSE_SECRET (32+ bytes) and is never
printed, logged or written to the repo: keep it in a shell export or in the
systemd drop-in (`systemctl edit b2first`). Codes are single-use: the server
stores sha256(code) only, in data/licenses.json. Respects DATA_DIR.

Exit codes: 0 ok · 1 usage error · 2 configuration error.
"""
import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import plans  # noqa: E402  (same code/format/HMAC the server verifies)

SECRET_ENV = "B2_LICENSE_SECRET"
SECRET_MIN = 32


def _secret():
    value = (os.environ.get(SECRET_ENV) or "").strip()
    if len(value) < SECRET_MIN:
        print(f"{SECRET_ENV} must be set and at least {SECRET_MIN} bytes "
              f"(generate one with: python3 tools/issue_license.py --gen-secret)",
              file=sys.stderr)
        return ""
    return value


def cmd_issue(args):
    secret = _secret()
    if not secret:
        return 2
    if args.plan != "pro":
        print("only 'pro' codes can be issued (free and byo are automatic)",
              file=sys.stderr)
        return 1
    days = 0 if args.expire_now else args.days
    if days is None:
        print("days is required (e.g. 'pro 30')", file=sys.stderr)
        return 1
    if days < 0 or days > plans.MAX_DAYS:
        print(f"days must be between 0 and {plans.MAX_DAYS}", file=sys.stderr)
        return 1
    try:
        code = plans.issue_code(args.plan, days, secret)
    except (ValueError, RuntimeError) as exc:
        print(f"could not issue the code: {exc}", file=sys.stderr)
        return 2
    plans.record_issue(code, args.plan, days)
    print(f"plan={args.plan} days={days} label={plans.label_for_days(days)} "
          f"(single-use, redeem it in Settings -> Plan)", file=sys.stderr)
    print(code)
    return 0


def cmd_list(_args):
    rows = plans.list_issues()
    if not rows:
        print("no codes issued yet", file=sys.stderr)
        return 0
    print("%-12s  %-4s  %-4s  %-20s  %-18s  %s" %
          ("HASH", "PLAN", "TERM", "ISSUED", "REDEEMED BY", "UNTIL"))
    for row in rows:
        print("%-12s  %-4s  %-4s  %-20s  %-18s  %s" % (
            (row["hash"] or "")[:12],
            row.get("plan") or "?",
            row.get("label") or "?",
            row.get("issued_at") or "?",
            row.get("user_id") or "-",
            row.get("until") or "-",
        ))
    return 0


def cmd_gen_secret(_args):
    print(secrets.token_urlsafe(32))
    print(f"# export {SECRET_ENV}=<the secret above> — never commit it",
          file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Issue pro activation codes for b2first (owner tool).")
    ap.add_argument("plan", nargs="?", help="plan to unlock (only 'pro')")
    ap.add_argument("days", nargs="?", type=int, help="duration in days")
    ap.add_argument("--list", action="store_true", help="list issued codes")
    ap.add_argument("--gen-secret", action="store_true",
                    help="print a fresh B2_LICENSE_SECRET and exit")
    ap.add_argument("--expire-now", action="store_true",
                    help="issue a code that is already expired (tests)")
    args = ap.parse_args()
    if args.gen_secret:
        return cmd_gen_secret(args)
    if args.list:
        return cmd_list(args)
    if not args.plan:
        ap.print_usage(sys.stderr)
        return 1
    return cmd_issue(args)


if __name__ == "__main__":
    sys.exit(main())
