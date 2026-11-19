#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Service levels and the per-account usage meter.

Every account gets the same service level. The limits exist to keep provider
spend and abuse bounded, not to sell an upgrade: there is no plan to buy, no
activation code and no per-plan gating in the product.

Design rules:

* ``effective_plan`` is the one place that answers "what may this account do
  right now". It returns the owner row, the bring-your-own-key row or the
  default service row.
* ``data/usage.json`` is the meter: counters per account, per UTC day / ISO week
  / month. Windows reset by comparing their key on read; accounts untouched for
  more than ``USAGE_KEEP_DAYS`` are pruned on write (rotation).
* This module knows nothing about HTTP and never formats a response body.
  Every path is resolved per call through ``store.data_dir()`` so tests can swap
  ``DATA_DIR`` after import.
"""
import calendar
import os
import threading
import time

import store

__all__ = [
    "LIMITS",
    "effective_plan",
    "forget_user",
    "usage_snapshot",
    "usage_row",
    "writing_used",
    "writing_consume",
    "speaking_used",
    "speaking_add_mock",
    "speaking_add_seconds",
    "reset_at",
]

USAGE_KEEP_DAYS = 396   # 13 months on write (the retention tool enforces the same)
DAY_WRITING_LIMIT = 5
DAY_SPEAKING_MOCKS = 1
DAY_SPEAKING_MINUTES = 15
_DAY = 24 * 3600

# The account(s) that run the product are not capped per day (the global
# monthly Gemini Live guard in server.py still applies to everyone).
# B2_OWNER_UIDS overrides the default (comma separated user ids).
OWNER_UID_DEFAULT = "owner"

# One service level for every account, sized for the budget (DeepSeek USD 2.18
# prepaid one-time, Gemini USD 10/month; writing USD 0.0011-0.0022, Live minute
# USD 0.0088, 14-min mock USD 0.123) and enforced per UTC day; the instance-wide
# AI ceiling lives in server.py.
LIMITS = {
    "service": {
        "writing": {"limit": DAY_WRITING_LIMIT, "window": "day"},
        "speaking": {"mocks": DAY_SPEAKING_MOCKS,
                     "minutes": DAY_SPEAKING_MINUTES, "window": "day"},
        "pronunciation": "full",
    },
    "byo": {
        # The user's own provider key pays, so this server does not meter it.
        "writing": None,
        "speaking": None,
        "pronunciation": "full",
    },
    "owner": {
        # The owner is not metered per day; the instance-wide knobs still
        # exist for every other account.
        "writing": {"limit": 1_000_000, "window": "day"},
        "speaking": {"mocks": 1_000_000, "minutes": 1_000_000, "window": "day"},
        "pronunciation": "full",
    },
}

_LOCK = threading.RLock()


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
    only imports plans never loads server, so the variable has to be read here
    too — the same convention as tools/verify_audit.py. An explicit
    store.DATA_DIR (tests) always wins.
    """
    current = store.data_dir()
    env = (os.environ.get("DATA_DIR") or "").strip()
    if env and current == store._DEFAULT_DATA_DIR:
        return env
    return current


def _usage_path():
    return os.path.join(_data_dir(), "usage.json")


def _read(path, default):
    data = store.read_json_private(path, default)
    return data if isinstance(data, dict) else default


# ---------------------------------------------------------------------------
# Service level: owner, bring-your-own-key or the single default service row.
# ---------------------------------------------------------------------------
def owner_uids():
    """User ids treated as the owner (no caps). B2_OWNER_UIDS overrides."""
    raw = (os.environ.get("B2_OWNER_UIDS") or "").strip()
    if not raw:
        return {OWNER_UID_DEFAULT}
    return {x.strip() for x in raw.split(",") if x.strip()}


def is_owner(uid):
    return bool(uid) and uid in owner_uids()


def effective_plan(uid, byo=False, now=None):
    """The one place that answers 'what may this account do right now'."""
    if uid and is_owner(uid):
        return {"plan": "owner", "since": None, "until": None,
                "source": "owner", "limits": LIMITS["owner"]}
    if byo:
        return {"plan": "byo", "since": None, "until": None,
                "source": "byo", "limits": LIMITS["byo"]}
    return {"plan": "service", "since": None, "until": None,
            "source": "service", "limits": LIMITS["service"]}


def forget_user(uid):
    """Drop the usage row for an account (GDPR hook)."""
    with _LOCK:
        usage = _usage()
        accounts = usage.get("accounts")
        if isinstance(accounts, dict) and accounts.pop(uid, None) is not None:
            store.write_json_private(_usage_path(), usage)


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
    """How many LLM calls this account made in the current window."""
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
    if window == "day":
        if s.get("day") != day_key(ts):
            return 0, 0.0
        return int(s.get("day_mocks") or 0), float(s.get("day_seconds") or 0.0)
    return 0, 0.0


def speaking_used(uid, window, now=None):
    """{mocks, seconds} used in the current day/week/month window."""
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
        if s.get("day") != day_key(ts):
            s["day"], s["day_mocks"], s["day_seconds"] = day_key(ts), 0, 0.0
        if s.get("week") != week_key(ts):
            s["week"], s["week_mocks"], s["week_seconds"] = week_key(ts), 0, 0.0
        if s.get("month") != month_key(ts):
            s["month"], s["month_mocks"], s["month_seconds"] = month_key(ts), 0, 0.0
        s["day_mocks"] = int(s.get("day_mocks") or 0) + int(mocks)
        s["day_seconds"] = round(float(s.get("day_seconds") or 0.0) + float(seconds), 3)
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


def usage_row(uid):
    """Raw metering row for one account ({} when it has never used anything)."""
    rec = _usage()["accounts"].get(uid)
    return dict(rec) if isinstance(rec, dict) else {}


def usage_snapshot(uid, plan_limits, now=None):
    """Everything GET /api/plan needs about the meter for this service level."""
    ts = _now(now)
    limits = plan_limits or LIMITS["service"]
    writing = limits.get("writing") or {}
    speaking = limits.get("speaking") or {}
    w_window = writing.get("window") or "day"
    s_window = speaking.get("window") or "day"
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
