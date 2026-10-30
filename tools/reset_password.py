#!/usr/bin/env python3
"""Owner tool: reset a user's password from the Pi (no HTTP endpoint by design).

Usage:
    python3 tools/reset_password.py <username> [--generate]
    python3 tools/reset_password.py <username> --password <new-password>

Prints the new password to stdout (never the hash), hashes it exactly like
server.py (PBKDF2-HMAC-SHA256, 600k iterations, fresh salt) and invalidates
every session token of that user. Respects the DATA_DIR environment variable.
"""
import argparse
import getpass
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


def main():
    ap = argparse.ArgumentParser(description="Reset a user's password (owner tool).")
    ap.add_argument("username")
    ap.add_argument("--generate", action="store_true",
                    help="generate a random password and print it")
    ap.add_argument("--password", help="use this new password instead of generating one")
    args = ap.parse_args()

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
    print(new_password)
    return 0


if __name__ == "__main__":
    sys.exit(main())
