#!/usr/bin/env python3
"""Owner tool: reset a user's password from the host (no HTTP reset endpoint).

Usage:
    python3 tools/reset_password.py <username> [--generate]
    python3 tools/reset_password.py <username> --password <new-password>
    python3 tools/reset_password.py --pending
    python3 tools/reset_password.py --clear-pending

Prints the new password to stdout (never the hash), hashes it exactly like
server.py (PBKDF2-HMAC-SHA256, 600k iterations, fresh salt) and invalidates
every session token of that user.

The login screen can file a manual reset request (user name + optional
contact); those requests are queued in data/pwreset.jsonl. `--pending` prints
them oldest first and `--clear-pending` empties the queue. Respects the
DATA_DIR environment variable.
"""
import argparse
import getpass
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S  # noqa: E402  (hashing + token helpers, identical to the HTTP path)
import store  # noqa: E402


def find_user(name):
    """Return (uid, record) matching `name` case-insensitively, or (None, None)."""
    for uid, rec in store.list_users().items():
        if rec.get("name", "").lower() == name.strip().lower():
            return uid, rec
    return None, None


def read_queue():
    """Return [(ts, name, contact)] oldest first, skipping malformed lines."""
    try:
        with open(store.pwreset_file(), "r", encoding="utf-8") as f:
            raw = f.read().split("\n")
    except OSError:
        return []
    rows = []
    for line in raw:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        rows.append((rec.get("ts", ""), rec.get("name", ""), rec.get("contact", "")))
    return rows


def cmd_pending():
    rows = read_queue()
    if not rows:
        print("no pending password-reset requests")
        return 0
    for ts, name, contact in rows:
        print("%s\t%s\t%s" % (ts, name, contact))
    return 0


def cmd_clear_pending():
    path = store.pwreset_file()
    rows = read_queue()
    if not os.path.exists(path):
        print("cleared 0 pending password-reset request(s)")
        return 0
    try:
        with open(path, "w", encoding="utf-8"):
            pass
        os.chmod(path, 0o600)
    except OSError as exc:
        print("could not clear %s: %s" % (path, exc), file=sys.stderr)
        return 1
    print("cleared %d pending password-reset request(s)" % len(rows))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Reset a user's password (owner tool).")
    ap.add_argument("username", nargs="?", help="account name to reset")
    ap.add_argument("--generate", action="store_true",
                    help="generate a random password and print it")
    ap.add_argument("--password", help="use this new password instead of generating one")
    ap.add_argument("--pending", action="store_true",
                    help="print the queued reset requests (ts, name, contact)")
    ap.add_argument("--clear-pending", action="store_true",
                    help="empty the queued reset requests")
    args = ap.parse_args()

    if args.pending and args.clear_pending:
        ap.error("choose one of --pending or --clear-pending")
    if args.pending:
        return cmd_pending()
    if args.clear_pending:
        return cmd_clear_pending()
    if not args.username:
        ap.error("username is required unless --pending or --clear-pending is used")

    uid, rec = find_user(args.username)
    if not rec:
        print(f"user not found: {args.username}", file=sys.stderr)
        return 1

    if args.password is not None:
        new_password = args.password
    elif args.generate:
        new_password = secrets.token_urlsafe(12)
    else:
        new_password = getpass.getpass("New password: ")
        if new_password != getpass.getpass("Repeat password: "):
            print("passwords do not match", file=sys.stderr)
            return 1
    if not isinstance(new_password, str) or len(new_password) < S.PASSWORD_MIN_LEN:
        print(f"password too short (min {S.PASSWORD_MIN_LEN})", file=sys.stderr)
        return 1

    salt = secrets.token_hex(8)
    updated = dict(rec)
    updated["salt"] = salt
    updated["hash"] = S.hash_password(salt, new_password)
    updated["algo"] = "pbkdf2"
    updated["iters"] = S.PBKDF2_ITERATIONS
    store.create_user(uid, updated)

    revoked = S.revoke_user_sessions(uid)

    print(f"password updated for {rec.get('name')} (uid={uid}); "
          f"{revoked} session(s) invalidated", file=sys.stderr)
    print("reminder: delete the pending request in data/pwreset.jsonl "
          "when you are done (or run --clear-pending)", file=sys.stderr)
    print(new_password)
    return 0


if __name__ == "__main__":
    sys.exit(main())
