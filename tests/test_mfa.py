"""MFA (TOTP) contract: enrolment, login challenge, one-time ticket, recovery.

Pure stdlib client against an isolated server on a throwaway data dir.

Covers:
- RFC 6238 vectors and the +/-1 step window;
- enrolment returns a base32 secret, an otpauth URI and 10 recovery codes;
- confirm activates the factor, invalid codes do not;
- /api/login answers {"mfa_required": true, "ticket": ...} and mints no token;
- /api/login/mfa with a valid code returns a session token;
- a ticket is single-use; a recovery code is burned on first use;
- disable requires the password plus a valid code;
- accounts without MFA log in exactly as before;
- no code is written to the audit trail.

Run: cd tests && uv run --with playwright --with httpx python test_mfa.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from helpers import isolated_server

URL = isolated_server({"B2_REGISTER": "open", "B2_LOGIN_IP_PER_10MIN": "10000"})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mfa  # noqa: E402
import server as S  # noqa: E402

PASS = "mfa-suite-pass-9"
OUT = {}
failed = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FALLO ") + name + ("" if cond else f" -- {detail}"))
    OUT[name] = bool(cond)
    if not cond:
        failed.append(name)


def api(path, payload=None, token=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        URL + path, data=data,
        headers={"Content-Type": "application/json", "X-Requested-With": "b2first"},
        method=method or ("POST" if data is not None else "GET"),
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, body


def reset_limits():
    with S._RATE_LOCK:
        S._RATE.clear()
    with S._LOGIN_FAIL_LOCK:
        S._LOGIN_FAIL.clear()


# --- 1. Pure TOTP: RFC vectors and the +/-1 step window ---------------------
# RFC 6238 SHA-1 test secret ("12345678901234567890" in base32).
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
check("rfc6238_vector_59s", mfa.totp(RFC_SECRET, at=59) == "287082",
      mfa.totp(RFC_SECRET, at=59))
check("rfc6238_vector_1111111109",
      mfa.totp(RFC_SECRET, at=1111111109) == "081804",
      mfa.totp(RFC_SECRET, at=1111111109))

now = int(time.time())
secret_only = mfa.generate_secret()
check("secret_is_base32_32_chars",
      len(secret_only) == 32 and secret_only.isupper()
      and all(ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for ch in secret_only),
      secret_only)
check("window_accepts_previous_step",
      mfa.verify(secret_only, mfa.totp(secret_only, at=now - 30), at=now))
check("window_accepts_next_step",
      mfa.verify(secret_only, mfa.totp(secret_only, at=now + 30), at=now))
check("window_rejects_two_steps_out",
      not mfa.verify(secret_only, mfa.totp(secret_only, at=now - 90), at=now))
check("malformed_code_rejected", not mfa.verify(secret_only, "12345", at=now))

# --- 2. Account without MFA: the login contract is unchanged ---------------
reset_limits()
st, plain = api("/api/register", {"name": "no-mfa-user", "password": PASS})
check("register_plain", st == 200 and plain.get("token"), (st, plain))
st, plain_login = api("/api/login", {"name": "no-mfa-user", "password": PASS})
check("plain_login_still_returns_token",
      st == 200 and "mfa_required" not in plain_login and plain_login.get("token"),
      (st, plain_login))

# --- 3. Enrolment -----------------------------------------------------------
reset_limits()
api("/api/register", {"name": "mfa-user", "password": PASS})
st, login = api("/api/login", {"name": "mfa-user", "password": PASS})
token = login["token"]

st, status = api("/api/mfa/status", token=token)
check("status_initially_disabled", st == 200 and status == {
    "enabled": False, "pending": False, "recovery_remaining": 0}, (st, status))

st, enroll = api("/api/mfa/enroll", {}, token=token)
codes = enroll.get("recovery_codes") if isinstance(enroll, dict) else []
check("enroll_ok", st == 200 and enroll.get("secret") and enroll.get("otpauth_uri"),
      (st, enroll))
check("enroll_ten_recovery_codes", isinstance(codes, list) and len(codes) == 10,
      len(codes or []))
check("enroll_uri_shape", enroll.get("otpauth_uri", "").startswith(
    "otpauth://totp/") and "secret=" in enroll.get("otpauth_uri", ""), enroll.get("otpauth_uri"))
check("enroll_secret_not_echoed_by_status",
      api("/api/mfa/status", token=token)[1].get("secret") is None)

st, bad = api("/api/mfa/confirm", {"code": "000000"}, token=token)
check("confirm_rejects_wrong_code", st == 400, (st, bad))
st, confirmed = api("/api/mfa/confirm",
                    {"code": mfa.totp(enroll["secret"])}, token=token)
check("confirm_activates", st == 200 and confirmed.get("ok") is True, (st, confirmed))
st, status = api("/api/mfa/status", token=token)
check("status_after_confirm",
      st == 200 and status.get("enabled") is True and status.get("pending") is False
      and status.get("recovery_remaining") == 10, (st, status))

# --- 4. Login challenge -----------------------------------------------------
reset_limits()
st, challenged = api("/api/login", {"name": "mfa-user", "password": PASS})
check("login_requires_mfa",
      st == 200 and challenged.get("mfa_required") is True
      and challenged.get("ticket") and "token" not in challenged, (st, challenged))
ticket = challenged["ticket"]

st, wrong = api("/api/login/mfa", {"ticket": ticket, "code": "000000"})
check("mfa_rejects_wrong_code", st == 401, (st, wrong))
st, ok = api("/api/login/mfa",
             {"ticket": ticket, "code": mfa.totp(enroll["secret"])})
check("mfa_valid_code_returns_token", st == 200 and ok.get("token"), (st, ok))

st, replay = api("/api/login/mfa",
                 {"ticket": ticket, "code": mfa.totp(enroll["secret"])})
check("ticket_is_single_use", st == 401, (st, replay))

# Expired ticket: mutate the record rather than waiting five minutes.
reset_limits()
st, challenged = api("/api/login", {"name": "mfa-user", "password": PASS})
expired = challenged["ticket"]
with S._MFA_TICKETS_LOCK:
    S._MFA_TICKETS[expired]["exp"] = time.time() - 1
st, dead = api("/api/login/mfa",
               {"ticket": expired, "code": mfa.totp(enroll["secret"])})
check("expired_ticket_rejected", st == 401, (st, dead))

# --- 5. Recovery codes are one-time ----------------------------------------
reset_limits()
st, challenged = api("/api/login", {"name": "mfa-user", "password": PASS})
ticket = challenged["ticket"]
st, rec_ok = api("/api/login/mfa", {"ticket": ticket, "code": codes[0]})
check("recovery_code_works", st == 200 and rec_ok.get("token"), (st, rec_ok))
st, status = api("/api/mfa/status", token=token)
check("recovery_code_consumed", status.get("recovery_remaining") == 9, status)

reset_limits()
st, challenged = api("/api/login", {"name": "mfa-user", "password": PASS})
st, rec_again = api("/api/login/mfa",
                    {"ticket": challenged["ticket"], "code": codes[0]})
check("recovery_code_not_reusable", st == 401, (st, rec_again))

# --- 6. Disable requires password + code -----------------------------------
reset_limits()
st, challenged = api("/api/login", {"name": "mfa-user", "password": PASS})
st, fresh = api("/api/login/mfa",
                {"ticket": challenged["ticket"], "code": mfa.totp(enroll["secret"])})
fresh_token = fresh["token"]

st, bad_pw = api("/api/mfa/disable",
                 {"password": "wrong-password", "code": mfa.totp(enroll["secret"])},
                 token=fresh_token)
check("disable_rejects_wrong_password", st == 401, (st, bad_pw))
st, bad_code = api("/api/mfa/disable",
                   {"password": PASS, "code": "000000"}, token=fresh_token)
check("disable_rejects_wrong_code", st == 400, (st, bad_code))
st, disabled = api("/api/mfa/disable",
                   {"password": PASS, "code": mfa.totp(enroll["secret"])},
                   token=fresh_token)
check("disable_with_password_and_code", st == 200 and disabled.get("ok") is True,
      (st, disabled))

reset_limits()
st, plain_again = api("/api/login", {"name": "mfa-user", "password": PASS})
check("login_without_mfa_after_disable",
      st == 200 and plain_again.get("token") and not plain_again.get("mfa_required"),
      (st, plain_again))

# --- 7. No code ever reaches the audit trail -------------------------------
audit_text = ""
audit_path = os.path.join(S.DATA_DIR, "audit.log")
try:
    with open(audit_path, encoding="utf-8") as fh:
        audit_text = fh.read()
except OSError:
    pass
events = [json.loads(line) for line in audit_text.splitlines() if line.strip()]
check("audit_has_mfa_events",
      any(e.get("event") == "login_mfa_ok" for e in events))
check("audit_contains_no_code_field",
      all("code" not in e and "secret" not in e for e in events),
      [e for e in events if "code" in e or "secret" in e][:2])

print(json.dumps({"checks": len(OUT), "failed": failed}, indent=1))
if failed:
    print(f"{len(failed)} FAILED: " + ", ".join(failed), file=sys.stderr)
    sys.exit(1)
print("mfa OK")
