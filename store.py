#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON storage seam for users, progress and backups.

This module isolates all data-filesystem access from the HTTP logic.
It knows nothing about tokens and does not depend on http.server.
"""
import json
import os
import re
import shutil
import sys
import threading
import time
from contextlib import contextmanager

__all__ = [
    "get_user",
    "create_user",
    "list_users",
    "remove_user",
    "get_progress",
    "put_progress",
    "backup",
    "speaking_read",
    "speaking_add",
    "speaking_file",
    "StoreBusy",
    "PROGRESS_SCHEMA",
]

_DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_DIR = _DEFAULT_DATA_DIR
BK_KEEP = 20
PROGRESS_SCHEMA = 2
_LOCK_TIMEOUT = 5.0

_SAFE_UID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


class StoreBusy(Exception):
    """A write lock could not be acquired within _LOCK_TIMEOUT seconds."""


def _safe_uid(raw):
    """Validate a user id before it is ever used to build a path.

    Accepts only [A-Za-z0-9._-]{1,64}; rejects '..', '/' , '\\' and leading
    dots. Returns the id unchanged or raises ValueError (never touches disk).
    """
    if not isinstance(raw, str) or not _SAFE_UID_RE.fullmatch(raw):
        raise ValueError("invalid user id")
    if raw.startswith(".") or ".." in raw:
        raise ValueError("invalid user id")
    return raw


_STORE_LOCK = threading.Lock()
_PROG_LOCKS = {}
_PROG_LOCKS_GUARD = threading.Lock()


def _prog_lock(uid: str) -> threading.Lock:
    """Per-user Lock for progress read-modify-write (guarded dict of locks)."""
    with _PROG_LOCKS_GUARD:
        lock = _PROG_LOCKS.get(uid)
        if lock is None:
            lock = threading.Lock()
            _PROG_LOCKS[uid] = lock
        return lock


@contextmanager
def _locked(lock):
    """Take `lock` or raise StoreBusy after _LOCK_TIMEOUT seconds."""
    if not lock.acquire(timeout=_LOCK_TIMEOUT):
        raise StoreBusy("busy")
    try:
        yield
    finally:
        lock.release()


def _data_dir() -> str:
    """Return the active data directory (respects server.DATA_DIR in tests)."""
    if DATA_DIR != _DEFAULT_DATA_DIR:
        return DATA_DIR
    srv = sys.modules.get("server")
    if srv is not None and getattr(srv, "DATA_DIR", None):
        return srv.DATA_DIR
    return DATA_DIR


def _users_file() -> str:
    return os.path.join(_data_dir(), "users.json")


def _user_dir(uid: str) -> str:
    return os.path.join(_data_dir(), "users", _safe_uid(uid))


def _prog_file(uid: str) -> str:
    return os.path.join(_user_dir(uid), "progress.json")


def speaking_file(uid: str) -> str:
    """Path to a user's speaking-minute ledger (data/users/<uid>/speaking.json)."""
    return os.path.join(_user_dir(uid), "speaking.json")


def _bk_dir(uid: str) -> str:
    return os.path.join(_user_dir(uid), "backups")


def _ensure_private_dir(path: str) -> None:
    """Create a directory (if needed) and force 0700 permissions on it.

    os.makedirs applies mode only when creating and it is masked by the umask,
    so the explicit chmod keeps the directory private even if it pre-exists.
    """
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def _ensure_user_dirs(uid: str) -> None:
    """Create data/users/<uid>/ (0700) and its backups/ folder (0700)."""
    _ensure_private_dir(_user_dir(uid))
    _ensure_private_dir(_bk_dir(uid))


def _read_json(path: str, default):
    """Read a JSON file or return default if it is missing or corrupt."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path: str, data) -> None:
    """Write a JSON file atomically (tmp + rename), readable only by the owner (0600)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def list_users() -> dict:
    """Return {uid: record} read from data/users.json."""
    data = _read_json(_users_file(), {})
    return data if isinstance(data, dict) else {}


def get_user(uid: str) -> dict | None:
    """Return the record of user uid, or None if it does not exist."""
    return list_users().get(uid)


def create_user(uid: str, record: dict) -> None:
    """Persist or update the record of user uid and ensure its backups folder."""
    _safe_uid(uid)
    with _locked(_STORE_LOCK):
        users = list_users()
        users[uid] = record
        _write_json(_users_file(), users)
        _ensure_user_dirs(uid)


def remove_user(uid: str) -> None:
    """Delete the record of user uid and its whole data directory."""
    _safe_uid(uid)
    with _locked(_STORE_LOCK):
        users = list_users()
        users.pop(uid, None)
        _write_json(_users_file(), users)
        shutil.rmtree(_user_dir(uid), ignore_errors=True)


def _needs_migration(data: dict) -> bool:
    """True for pre-schema progress (v1: no schema_version). Future versions are left alone."""
    sv = data.get("schema_version")
    if sv == PROGRESS_SCHEMA:
        return False
    if isinstance(sv, int) and sv > PROGRESS_SCHEMA:
        return False
    return True


def _migrate_progress(data: dict) -> dict:
    """Upgrade progress in place to PROGRESS_SCHEMA (1 -> 2), never dropping unknown fields."""
    data.setdefault("profile", None)
    data.setdefault("onboarded", False)
    settings = data.get("settings")
    if not isinstance(settings, dict):
        settings = {}
        data["settings"] = settings
    settings["__v"] = PROGRESS_SCHEMA
    data["schema_version"] = PROGRESS_SCHEMA
    return data


def get_progress(uid: str) -> dict | None:
    """Return the saved progress of the user, or None if it does not exist yet.

    Versioned migration: a progress without schema_version is upgraded to
    PROGRESS_SCHEMA and rewritten, keeping the original in
    backups/pre-migration-<ts>.json (idempotent: a second read is a no-op).
    """
    _safe_uid(uid)
    pf = _prog_file(uid)
    data = _read_json(pf, None)
    if not isinstance(data, dict) or not _needs_migration(data):
        return data if isinstance(data, dict) else None
    with _locked(_prog_lock(uid)):
        data = _read_json(pf, None)  # re-read under the lock
        if not isinstance(data, dict) or not _needs_migration(data):
            return data if isinstance(data, dict) else None
        _ensure_user_dirs(uid)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        try:
            shutil.copy2(pf, os.path.join(_bk_dir(uid), f"pre-migration-{stamp}.json"))
        except OSError:
            pass
        _write_json(pf, _migrate_progress(data))
        return data


def backup(uid: str, label: str | None = None) -> str:
    """Copy the current progress.json into backups/ and return the created path."""
    pf = _prog_file(uid)
    if not os.path.exists(pf):
        return ""
    _ensure_user_dirs(uid)
    bk_dir = _bk_dir(uid)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    dst = os.path.join(bk_dir, f"progress-{stamp}{suffix}.json")
    shutil.copy2(pf, dst)
    return dst


def _nonneg_float(value) -> float:
    """Coerce to a finite, non-negative float (0.0 for anything else)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")) or number < 0:
        return 0.0
    return number


def speaking_read(uid: str, day: str) -> dict:
    """Today's speaking ledger for one user, without creating the file.

    Returns {date, seconds, tokens_minted}. A ledger from another day reads as
    zero: minutes are a per-day budget and the reset happens on access.
    """
    _safe_uid(uid)
    rec = _read_json(speaking_file(uid), None)
    if not isinstance(rec, dict) or rec.get("date") != day:
        return {"date": day, "seconds": 0.0, "tokens_minted": 0}
    return {
        "date": day,
        "seconds": round(_nonneg_float(rec.get("seconds")), 3),
        "tokens_minted": int(_nonneg_float(rec.get("tokens_minted"))),
    }


def speaking_add(uid: str, day: str, seconds: float = 0.0, tokens: int = 0) -> dict:
    """Accumulate spoken seconds and minted tokens for today (atomic, 0600, locked).

    Uses the same per-user lock as progress.json, so two browsers reporting at
    once cannot lose a write. The ledger survives a restart.
    """
    _safe_uid(uid)
    with _locked(_prog_lock(uid)):
        _ensure_user_dirs(uid)
        rec = _read_json(speaking_file(uid), None)
        if not isinstance(rec, dict) or rec.get("date") != day:
            rec = {"date": day, "seconds": 0.0, "tokens_minted": 0}
        out = {
            "date": day,
            "seconds": round(_nonneg_float(rec.get("seconds")) + _nonneg_float(seconds), 3),
            "tokens_minted": (int(_nonneg_float(rec.get("tokens_minted")))
                              + int(_nonneg_float(tokens))),
        }
        _write_json(speaking_file(uid), out)
        return out


def put_progress(uid: str, data: dict) -> None:
    """Persist the user's progress atomically and rotate backups (BK_KEEP=20).

    The per-user lock covers backup + write so two concurrent PUTs cannot
    clobber each other's backup or tmp file.
    """
    _safe_uid(uid)
    with _locked(_prog_lock(uid)):
        _ensure_user_dirs(uid)
        bk_dir = _bk_dir(uid)
        pf = _prog_file(uid)
        if os.path.exists(pf):
            try:
                backup(uid)
            except OSError:
                pass
        _write_json(pf, data)
        try:
            bks = sorted(os.listdir(bk_dir))
            for old in bks[:-BK_KEEP]:
                os.remove(os.path.join(bk_dir, old))
        except OSError:
            pass
