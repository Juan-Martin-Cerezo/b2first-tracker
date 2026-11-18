#!/usr/bin/env python3
"""Password policy tests (fase E, ASVS 2.1.1 / 2.1.7).

Exercises the real policy in server.py: 12-character minimum at registration
and change, the embedded blocklist plus its deterministic derivatives, and the
unicode path (no composition rules, no truncation).

Standalone: ``python3 tests/test_password_policy.py``; exits non-zero on any
failure. It does not start a server or touch data/.
"""
import json
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="b2pwpolicy-")
os.environ["B2_DATA_DIR"] = _tmp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S  # noqa: E402
import store  # noqa: E402
import wordlist  # noqa: E402

S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")

failed = []
checks = {}


def check(name, cond, detail=""):
    checks[name] = {"ok": bool(cond), "detail": detail}
    if not cond:
        failed.append(name)


# --- Length boundary (ASVS 2.1.1: 12) --------------------------------------
check("P1_11_chars_rejected",
      S.password_problem("someone", "abcdefghij1") == "password too short (min 12)",
      str(S.password_problem("someone", "abcdefghij1")))
check("P2_12_chars_accepted",
      S.password_problem("someone", "Tr0ub4dor&3x") is None,
      str(S.password_problem("someone", "Tr0ub4dor&3x")))

# --- Blocklist --------------------------------------------------------------
check("P3_common_password_rejected",
      S.password_problem("someone", "password1234") == "password too common",
      str(S.password_problem("someone", "password1234")))
check("P4_app_derived_rejected",
      S.password_problem("someone", "b2first12345") == "password too common",
      str(S.password_problem("someone", "b2first12345")))
check("P5_cambridge_derived_rejected",
      S.password_problem("someone", "cambridge2025") == "password too common",
      str(S.password_problem("someone", "cambridge2025")))
check("P6_keyboard_walk_rejected",
      S.password_problem("someone", "qwerty123456") == "password too common",
      str(S.password_problem("someone", "qwerty123456")))
check("P7_repetition_rejected",
      S.password_problem("someone", "aaaaaaaaaaaa") == "password too common",
      str(S.password_problem("someone", "aaaaaaaaaaaa")))
check("P8_suffix_rule_rejected",
      S.password_problem("someone", "sunshine2025") == "password too common",
      str(S.password_problem("someone", "sunshine2025")))

# --- Username equality and unicode -----------------------------------------
check("P9_username_equality_rejected",
      S.password_problem("María-José-2024", "maría-josé-2024") == "password equals username",
      str(S.password_problem("María-José-2024", "maría-josé-2024")))
check("P10_unicode_accepted",
      S.password_problem("someone", "contraseña-segura-9") is None,
      str(S.password_problem("someone", "contraseña-segura-9")))

# --- registration path uses the same policy --------------------------------
_uid, _err = S.register_user("policy-short", "abcdefghij1")
_uid_long, _err_long = S.register_user("policy-long", "Tr0ub4dor&3x")
check("P11_register_rejects_11",
      _uid is None and _err == "password too short (min 12)", str(_err))
check("P12_register_accepts_12", _uid_long is not None and _err_long is None,
      str(_err_long))
check("P13_blocklist_size",
      len(wordlist.COMMON_PASSWORDS) >= 3000,
      str(len(wordlist.COMMON_PASSWORDS)))

print(json.dumps(checks, ensure_ascii=False, indent=1))
print("PASSWORD_POLICY_EXIT", 1 if failed else 0)
sys.exit(1 if failed else 0)
