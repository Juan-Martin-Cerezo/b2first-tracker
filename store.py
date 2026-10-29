#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON storage seam for users, progress and backups.

This module isolates all data-filesystem access from the HTTP logic.
It knows nothing about tokens and does not depend on http.server.
"""
import json
import os
import shutil
import sys
import time

__all__ = [
    "get_user",
    "create_user",
    "list_users",
    "get_progress",
    "put_progress",
    "backup",
]

_DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_DIR = _DEFAULT_DATA_DIR
BK_KEEP = 20


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


def _prog_file(uid: str) -> str:
    return os.path.join(_data_dir(), "users", uid, "progress.json")


def _bk_dir(uid: str) -> str:
    return os.path.join(_data_dir(), "users", uid, "backups")


def _read_json(path: str, default):
    """Read a JSON file or return default if it is missing or corrupt."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path: str, data) -> None:
    """Write a JSON file atomically (tmp + rename)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def list_users() -> dict:
    """Return {uid: record} read from data/users.json."""
    data = _read_json(_users_file(), {})
    return data if isinstance(data, dict) else {}


def get_user(uid: str) -> dict | None:
    """Return the record of user uid, or None if it does not exist."""
    return list_users().get(uid)


def create_user(uid: str, record: dict) -> None:
    """Persist or update the record of user uid and ensure its backups folder."""
    users = list_users()
    users[uid] = record
    _write_json(_users_file(), users)
    os.makedirs(_bk_dir(uid), exist_ok=True)


def get_progress(uid: str) -> dict | None:
    """Return the saved progress of the user, or None if it does not exist yet."""
    data = _read_json(_prog_file(uid), None)
    return data if isinstance(data, dict) else None


def backup(uid: str, label: str | None = None) -> str:
    """Copy the current progress.json into backups/ and return the created path."""
    pf = _prog_file(uid)
    if not os.path.exists(pf):
        return ""
    bk_dir = _bk_dir(uid)
    os.makedirs(bk_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    dst = os.path.join(bk_dir, f"progress-{stamp}{suffix}.json")
    shutil.copy2(pf, dst)
    return dst


def put_progress(uid: str, data: dict) -> None:
    """Persist the user's progress atomically and rotate backups (BK_KEEP=20)."""
    bk_dir = _bk_dir(uid)
    os.makedirs(bk_dir, exist_ok=True)
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
