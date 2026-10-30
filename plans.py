#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plans, per-plan usage meter and activation codes (phase 31).

Three plans exist:

* ``free`` — the default for every account: 3 LLM calls a day, 1 speaking mock
  (5 minutes) a week.
* ``byo``  — request-scoped: the user brought their own provider key (phase 30).
  Nothing is stored here; ``server._plan_for`` derives it from the headers.
* ``pro``  — unlocked by a signed, single-use activation code issued by the
  owner with ``tools/issue_license.py`` (phase 33 adds Stripe subscriptions).

Design rules:

* ``data/plans.json`` is the source of truth for a stored plan; expiry is
  evaluated on read (``until <= now`` demotes to ``free``), so no cron job is
  needed and a lapsed account never sees a stale limit.
* ``data/usage.json`` is the meter: counters per account, per UTC day / ISO week
  / month. Windows reset by comparing their key on read; accounts untouched for
  more than ``USAGE_KEEP_DAYS`` are pruned on write (rotation).
* ``data/licenses.json`` is keyed by ``sha256(code)``: plaintext codes never
  touch the disk and an audit of the file cannot reveal a redeemable code.
* This module knows nothing about HTTP and never formats a response body.
  Every path is resolved per call through ``store.data_dir()`` so tests can swap
  ``DATA_DIR`` after import.
"""
import base64
import calendar
import hashlib
import hmac
import os
import re
import secrets
import threading
import time

import store

__all__ = [
    "PLANS",
    "LIMITS",
    "plan_record",
    "effective_plan",
    "set_plan",
    "forget_user",
    "usage_snapshot",
    "writing_used",
    "writing_consume",
    "speaking_used",
    "speaking_add_mock",
    "speaking_add_seconds",
    "reset_at",
    "issue_code",
    "verify_code",
    "normalize_code",
    "code_hash",
    "record_issue",
    "license_row",
    "mark_redeemed",
    "list_issues",
    "LICENSE_PREFIX",
]

USAGE_KEEP_DAYS = 60
MAX_DAYS = 400
LICENSE_PREFIX = "FT"
CODE_BODY_CHARS = 12
_DAY = 24 * 3600

PLANS = ("free", "byo", "pro")

# The cost ceiling per plan lives here and nowhere else. Measured inputs:
# ~US$0.25 per speaking mock, ~US$0.01 per writing correction / report.
# free ~= $0.10/month, pro = 60*$0.01 + 6*$0.25 = $2.10/month against $5.
LIMITS = {
    "free": {
        "writing": {"limit": 3, "window": "day"},
        "speaking": {"mocks": 1, "minutes": 5, "window": "week"},
        "pronunciation": "preview",
    },
    "byo": {
        "writing": None,
        "speaking": None,
        "pronunciation": "preview",
    },
    "pro": {
        "writing": {"limit": 60, "window": "month"},
        "speaking": {"mocks": 6, "minutes": 90, "window": "month"},
        "pronunciation": "full",
    },
}

_LOCK = threading.RLock()  # re-entrant: set_plan -> mark_redeemed can nest
_LABEL_RE = re.compile(r"^(\d{1,4})([MD])$")


# ---------------------------------------------------------------------------
# Time helpers: everything is UTC, ISO-8601 with a trailing Z. The format is
# fixed-width, so comparing two of these strings is the same as comparing times.
# ---------------------------------------------------------------------------
def iso(ts):
    """Format an epoch timestamp as 2026-10-30T12:00:00Z."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _now(now=None):
    return time.time() if now is None else float(now)


def day_key(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def month_key(ts):
    return time.strftime("%Y-%m", time.gmtime(ts))


def week_key(ts):
    """Monday-based week index, e.g. W02995 (1970-01-01 was a Thursday)."""
    return "W%05d" % ((int(ts) // _DAY + 3) // 7)


def reset_at(window, now=None):
    """ISO timestamp at which the window rolls over (day/week/month)."""
    ts = _now(now)
    tm = time.gmtime(ts)
    if window == "day":
        return iso((int(ts) // _DAY) * _DAY + _DAY)
    if window == "month":
        year, month = tm.tm_year, tm.tm_mon
        month += 1
        if month > 12:
            year, month = year + 1, 1
        return "%04d-%02d-01T00:00:00Z" % (year, month)
    # week: next Monday 00:00:00Z (tm_wday: Monday=0 .. Sunday=6)
    days = (7 - tm.tm_wday) % 7
    if days == 0:
        days = 7
    midnight = (int(ts) // _DAY) * _DAY
    return iso(midnight + days * _DAY)


def _parse_iso(value):
    """Epoch seconds for a 2026-10-30T12:00:00Z string (None if malformed)."""
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Small private JSON helpers (0600, atomic), resolved per call.
# ---------------------------------------------------------------------------
def _data_dir():
    """Active data directory.

    server.py sets its own DATA_DIR from the environment at import; a tool that
    only imports plans (tools/issue_license.py) never loads server, so the
    variable has to be read here too — the same convention as
    tools/verify_audit.py. An explicit store.DATA_DIR (tests) always wins.
    """
    current = store.data_dir()
    env = (os.environ.get("DATA_DIR") or "").strip()
    if env and current == store._DEFAULT_DATA_DIR:
        return env
    return current


def _plans_path():
    return os.path.join(_data_dir(), "plans.json")


def _usage_path():
    return os.path.join(_data_dir(), "usage.json")


def _licenses_path():
    return os.path.join(_data_dir(), "licenses.json")


def _read(path, default):
    data = store.read_json_private(path, default)
    return data if isinstance(data, dict) else default


# ---------------------------------------------------------------------------
# Plan records: {uid: {plan, since, until, source, code_hash}}
# ---------------------------------------------------------------------------
def _plans():
    return _read(_plans_path(), {})


def plan_record(uid):
    """Raw stored row for uid, or None."""
    row = _plans().get(uid)
    return row if isinstance(row, dict) else None


def _is_active(rec, ts):
    until = rec.get("until")
    if not isinstance(until, str) or not until:
        return False
    return until > iso(ts)


def effective_plan(uid, byo=False, now=None):
    """The one place that answers 'what may this account do right now'.

    Precedence: an active stored ``pro`` (or subscription) wins over a BYO key,
    which wins over ``free``. Expiry is evaluated on read; the stored row is
    left untouched (the mirror in the UI shows the real ``until``).
    """
    ts = _now(now)
    rec = plan_record(uid) if uid else None
    if rec and rec.get("plan") in ("pro",) and _is_active(rec, ts):
        plan = "pro"
        return {
            "plan": plan,
            "since": rec.get("since"),
            "until": rec.get("until"),
            "source": rec.get("source") or "code",
            "limits": LIMITS[plan],
        }
    if byo:
        return {
            "plan": "byo",
            "since": None,
            "until": None,
            "source": "byo",
            "limits": LIMITS["byo"],
        }
    return {
        "plan": "free",
        "since": rec.get("since") if rec else None,
        "until": rec.get("until") if rec else None,
        "source": "default",
        "limits": LIMITS["free"],
    }


def set_plan(uid, plan, days, source="code", code_hash="", now=None):
    """Store an active plan for uid and return the row.

    Codes stack: a redemption extends from ``max(now, current until)`` so a
    second code never shortens a subscription that is still running.
    """
    if plan not in ("pro",):
        raise ValueError("only paid plans can be stored")
    ts = _now(now)
    with _LOCK:
        rows = _plans()
        current = rows.get(uid) if isinstance(rows.get(uid), dict) else {}
        base = ts
        until = current.get("until")
        if isinstance(until, str) and until > iso(ts):
            parsed = _parse_iso(until)
            if parsed is not None:
                base = parsed
        since = current.get("since") if current.get("plan") == plan else iso(ts)
        rec = {
            "plan": plan,
            "since": since or iso(ts),
            "until": iso(base + max(0, int(days)) * _DAY),
            "source": source,
            "code_hash": code_hash or "",
        }
        rows[uid] = rec
        store.write_json_private(_plans_path(), rows)
        return rec


def forget_user(uid):
    """Drop the plan and usage rows and detach redeemed licenses (GDPR hook)."""
    with _LOCK:
        rows = _plans()
        if rows.pop(uid, None) is not None:
            store.write_json_private(_plans_path(), rows)
        usage = _usage()
        accounts = usage.get("accounts")
        if isinstance(accounts, dict) and accounts.pop(uid, None) is not None:
            store.write_json_private(_usage_path(), usage)
        lic = _read(_licenses_path(), {})
        touched = False
        for row in lic.values():
            if isinstance(row, dict) and row.get("user_id") == uid:
                row["user_id"] = None
                row["redeemed_at"] = None
                touched = True
        if touched:
            store.write_json_private(_licenses_path(), lic)


# ---------------------------------------------------------------------------
# Usage meter: {uid: {writing: {..}, speaking: {..}, last_seen: iso}}
# ---------------------------------------------------------------------------
def _usage():
    data = _read(_usage_path(), {})
    if not isinstance(data.get("accounts"), dict):
        data = {"version": 1, "accounts": {}}
    return data


def _account(accounts, uid):
    rec = accounts.get(uid)
    if not isinstance(rec, dict):
        rec = {}
        accounts[uid] = rec
    if not isinstance(rec.get("writing"), dict):
        rec["writing"] = {}
    if not isinstance(rec.get("speaking"), dict):
        rec["speaking"] = {}
    return rec


def _prune(accounts, ts):
    """Rotation: forget accounts that have not been seen for USAGE_KEEP_DAYS."""
    cutoff = ts - USAGE_KEEP_DAYS * _DAY
    for uid in list(accounts):
        rec = accounts.get(uid)
        seen = rec.get("last_seen") if isinstance(rec, dict) else None
        if not isinstance(seen, str):
            accounts.pop(uid, None)
            continue
        stamp = _parse_iso(seen)
        if stamp is None:
            accounts.pop(uid, None)
            continue
        if stamp < cutoff:
            accounts.pop(uid, None)


def _writing_count(rec, window, ts):
    w = rec.get("writing") or {}
    if window == "day":
        return int(w.get("day_count") or 0) if w.get("day") == day_key(ts) else 0
    if window == "month":
        return int(w.get("month_count") or 0) if w.get("month") == month_key(ts) else 0
    return 0


def writing_used(uid, window, now=None):
    """How many LLM calls this account made in the current plan window."""
    ts = _now(now)
    rec = _usage()["accounts"].get(uid)
    if not isinstance(rec, dict):
        return 0
    return _writing_count(rec, window, ts)


def writing_consume(uid, now=None):
    """Count one LLM call (writing correction or speaking report)."""
    ts = _now(now)
    with _LOCK:
        data = _usage()
        accounts = data["accounts"]
        _prune(accounts, ts)
        rec = _account(accounts, uid)
        w = rec["writing"]
        if w.get("day") != day_key(ts):
            w["day"], w["day_count"] = day_key(ts), 0
        if w.get("month") != month_key(ts):
            w["month"], w["month_count"] = month_key(ts), 0
        w["day_count"] = int(w.get("day_count") or 0) + 1
        w["month_count"] = int(w.get("month_count") or 0) + 1
        rec["last_seen"] = iso(ts)
        store.write_json_private(_usage_path(), data)


def _speaking_counts(rec, window, ts):
    s = rec.get("speaking") or {}
    if window == "week":
        if s.get("week") != week_key(ts):
            return 0, 0.0
        return int(s.get("week_mocks") or 0), float(s.get("week_seconds") or 0.0)
    if window == "month":
        if s.get("month") != month_key(ts):
            return 0, 0.0
        return int(s.get("month_mocks") or 0), float(s.get("month_seconds") or 0.0)
    return 0, 0.0


def speaking_used(uid, window, now=None):
    """{mocks, seconds} used in the current week/month window."""
    ts = _now(now)
    rec = _usage()["accounts"].get(uid)
    if not isinstance(rec, dict):
        return {"mocks": 0, "seconds": 0.0}
    mocks, seconds = _speaking_counts(rec, window, ts)
    return {"mocks": mocks, "seconds": round(seconds, 3)}


def _speaking_bump(uid, ts, mocks=0, seconds=0.0):
    with _LOCK:
        data = _usage()
        accounts = data["accounts"]
        _prune(accounts, ts)
        rec = _account(accounts, uid)
        s = rec["speaking"]
        if s.get("week") != week_key(ts):
            s["week"], s["week_mocks"], s["week_seconds"] = week_key(ts), 0, 0.0
        if s.get("month") != month_key(ts):
            s["month"], s["month_mocks"], s["month_seconds"] = month_key(ts), 0, 0.0
        s["week_mocks"] = int(s.get("week_mocks") or 0) + int(mocks)
        s["week_seconds"] = round(float(s.get("week_seconds") or 0.0) + float(seconds), 3)
        s["month_mocks"] = int(s.get("month_mocks") or 0) + int(mocks)
        s["month_seconds"] = round(float(s.get("month_seconds") or 0.0) + float(seconds), 3)
        rec["last_seen"] = iso(ts)
        store.write_json_private(_usage_path(), data)


def speaking_add_mock(uid, now=None):
    """Count one minted speaking mock (only after a successful mint)."""
    _speaking_bump(uid, _now(now), mocks=1)


def speaking_add_seconds(uid, seconds, now=None):
    """Accumulate spoken seconds reported by the browser."""
    try:
        value = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return
    _speaking_bump(uid, _now(now), seconds=value)


def usage_snapshot(uid, plan_limits, now=None):
    """Everything GET /api/plan needs about the meter for this plan."""
    ts = _now(now)
    limits = plan_limits or LIMITS["free"]
    writing = limits.get("writing") or {}
    speaking = limits.get("speaking") or {}
    w_window = writing.get("window") or "day"
    s_window = speaking.get("window") or "week"
    rec = _usage()["accounts"].get(uid)
    rec = rec if isinstance(rec, dict) else {}
    mocks, seconds = _speaking_counts(rec, s_window, ts)
    return {
        "writing": _writing_count(rec, w_window, ts),
        "writing_window": w_window,
        "speaking_mocks": mocks,
        "speaking_seconds": round(seconds, 3),
        "speaking_window": s_window,
        "reset_at": reset_at(w_window, ts),
        "speaking_reset_at": reset_at(s_window, ts),
    }


# ---------------------------------------------------------------------------
# Activation codes: FT-<PLAN>-<LABEL>-XXXX-XXXX-XXXX
#
# The readable prefix carries the plan and the duration; the 12-char body is
# base32(nonce[3] + mac[4]) where mac = HMAC-SHA256(secret, "FT|plan|days|nonce")
# truncated to 4 bytes. Tampering with plan or duration breaks the MAC, so the
# prefix needs no separate signature. 32 bits + 5 attempts/hour/account makes
# guessing hopeless; 24 bits of nonce keeps codes unique in practice.
# ---------------------------------------------------------------------------
def normalize_code(raw):
    """Uppercase and drop everything that is not a letter or a digit."""
    if not isinstance(raw, str):
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", raw).upper()


def code_hash(code):
    """sha256 of the normalised code: the only form ever written to disk."""
    return hashlib.sha256(normalize_code(code).encode("ascii")).hexdigest()


def label_for_days(days):
    days = int(days)
    if days > 0 and days % 30 == 0:
        return "%dM" % (days // 30)
    return "%dD" % days


def days_from_label(label):
    m = _LABEL_RE.match(label or "")
    if not m:
        return None
    value = int(m.group(1))
    days = value * 30 if m.group(2) == "M" else value
    if days < 0 or days > MAX_DAYS:
        return None
    return days


def _b32(raw):
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _b32_decode(text):
    padded = text + "=" * ((8 - len(text) % 8) % 8)
    try:
        return base64.b32decode(padded.encode("ascii"), casefold=False)
    except (ValueError, UnicodeEncodeError):
        return None


def _mac(secret, plan, days, nonce):
    msg = ("%s|%s|%d|%s" % (LICENSE_PREFIX, plan, int(days), nonce.hex())).encode("ascii")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()[:4]


def _licenses():
    return _read(_licenses_path(), {})


def issue_code(plan, days, secret):
    """Build a fresh code. Raises ValueError for an invalid plan/duration."""
    if plan not in ("pro",):
        raise ValueError("only 'pro' codes can be issued")
    days = int(days)
    if days < 0 or days > MAX_DAYS:
        raise ValueError("days out of range")
    if not isinstance(secret, str) or len(secret) < 32:
        raise ValueError("license secret must be at least 32 bytes")
    label = label_for_days(days)
    taken = _licenses()
    for _attempt in range(64):
        nonce = secrets.token_bytes(3)
        body = _b32(nonce + _mac(secret, plan, days, nonce))
        if len(body) != CODE_BODY_CHARS:
            continue
        code = "%s-%s-%s-%s-%s-%s" % (
            LICENSE_PREFIX, plan.upper(), label,
            body[0:4], body[4:8], body[8:12],
        )
        if code_hash(code) not in taken:
            return code
    raise RuntimeError("could not generate a unique code")


def verify_code(code, secret):
    """Return {plan, days, label, nonce_hex} for a valid code, else None.

    Never reveals *why* a code failed: every failure is a plain None so the
    HTTP layer can answer with one identical body.
    """
    if not isinstance(secret, str) or len(secret) < 32:
        return None
    compact = normalize_code(code)
    if len(compact) <= CODE_BODY_CHARS + len(LICENSE_PREFIX):
        return None
    if not compact.startswith(LICENSE_PREFIX):
        return None
    body = compact[-CODE_BODY_CHARS:]
    middle = compact[len(LICENSE_PREFIX):-CODE_BODY_CHARS]
    plan = None
    for candidate in ("PRO",):
        if middle.startswith(candidate):
            plan = candidate.lower()
            label = middle[len(candidate):]
            break
    if not plan:
        return None
    days = days_from_label(label)
    if days is None or label_for_days(days) != label:
        return None
    raw = _b32_decode(body)
    if not raw or len(raw) != 7:
        return None
    # The last base32 character carries padding bits that b32decode ignores, so
    # re-encoding must reproduce the body exactly: otherwise a one-character
    # change would be accepted (same bytes, different text).
    if _b32(raw) != body:
        return None
    nonce, mac = raw[:3], raw[3:]
    if not hmac.compare_digest(mac, _mac(secret, plan, days, nonce)):
        return None
    return {"plan": plan, "days": days, "label": label, "nonce_hex": nonce.hex()}


def record_issue(code, plan, days, now=None):
    """Tool-side ledger row: lets --list show what was issued and to whom."""
    ts = _now(now)
    key = code_hash(code)
    with _LOCK:
        rows = _licenses()
        rows[key] = {
            "plan": plan,
            "days": int(days),
            "label": label_for_days(days),
            "issued_at": iso(ts),
            "user_id": None,
            "redeemed_at": None,
            "until": None,
        }
        store.write_json_private(_licenses_path(), rows)
    return key


def license_row(code):
    return _licenses().get(code_hash(code))


def mark_redeemed(code, uid, until, now=None):
    """Mark a code as used. Returns the stored row (created if it was unknown)."""
    ts = _now(now)
    key = code_hash(code)
    with _LOCK:
        rows = _licenses()
        row = rows.get(key) if isinstance(rows.get(key), dict) else {}
        row.setdefault("plan", "pro")
        row.setdefault("issued_at", iso(ts))
        row["user_id"] = uid
        row["redeemed_at"] = iso(ts)
        row["until"] = until
        rows[key] = row
        store.write_json_private(_licenses_path(), rows)
        return row


def list_issues():
    """Issued codes, newest first: hash prefix only, never the plaintext."""
    rows = _licenses()
    out = []
    for key, row in rows.items():
        if not isinstance(row, dict):
            continue
        out.append({
            "hash": key,
            "plan": row.get("plan"),
            "label": row.get("label") or label_for_days(row.get("days") or 0),
            "issued_at": row.get("issued_at"),
            "user_id": row.get("user_id"),
            "redeemed_at": row.get("redeemed_at"),
            "until": row.get("until"),
        })
    out.sort(key=lambda r: (r.get("issued_at") or "", r["hash"]), reverse=True)
    return out
