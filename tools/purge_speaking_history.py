#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backup and purge legacy Speaking history without touching accounts or other progress.

Actions:
1. Create `data/.backup-speaking-<timestamp>.tar.gz` (mode 0600) containing all
   user `progress.json` files, legacy `data/speaking*` entries (excluding
   `speaking_v3`), and any legacy `data/users/*/speaking/` transcript folders.
2. Remove ONLY `speaking` and `spxCustom` keys from each
   `data/users/*/progress.json` (preserving all accounts and non-speaking data).
3. Delete legacy `data/speaking*` files/directories (NEVER `data/speaking_v3`)
   and any legacy `data/users/*/speaking/` transcript directories.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tarfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_PROGRESS_KEYS = ("speaking", "spxCustom")


def _default_data_dir():
    return (
        os.environ.get("B2_DATA_DIR")
        or os.environ.get("DATA_DIR")
        or os.path.join(REPO_ROOT, "data")
    )


def _atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def purge_speaking_history(data_dir=None, dry_run=False):
    """Run the backup + purge against `data_dir` and return a summary dict."""
    root = os.path.abspath(data_dir or _default_data_dir())
    if not os.path.isdir(root):
        return {
            "data_dir": root,
            "backup_path": None,
            "users_scanned": 0,
            "users_touched": 0,
            "touched_users": [],
            "removed_paths": [],
        }

    progress_files = sorted(glob.glob(os.path.join(root, "users", "*", "progress.json")))
    legacy_top = []
    for entry in sorted(os.listdir(root)):
        if entry == "speaking_v3":
            continue
        if entry.startswith("speaking"):
            legacy_top.append(os.path.join(root, entry))

    legacy_user_dirs = sorted(glob.glob(os.path.join(root, "users", "*", "speaking")))
    legacy_user_dirs = [p for p in legacy_user_dirs if os.path.isdir(p)]

    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    backup_path = os.path.join(root, f".backup-speaking-{stamp}.tar.gz")
    if os.path.exists(backup_path):
        backup_path = os.path.join(root, f".backup-speaking-{stamp}-{int(time.time() * 1000) % 1000:03d}.tar.gz")

    if not dry_run:
        with tarfile.open(backup_path, "w:gz") as tar:
            for pf in progress_files:
                tar.add(pf, arcname=os.path.relpath(pf, root))
            for lp in legacy_top:
                tar.add(lp, arcname=os.path.relpath(lp, root))
            for ud in legacy_user_dirs:
                tar.add(ud, arcname=os.path.relpath(ud, root))
        os.chmod(backup_path, 0o600)

    users_scanned = 0
    touched_users = []
    for pf in progress_files:
        users_scanned += 1
        uid = os.path.basename(os.path.dirname(pf))
        try:
            with open(pf, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        changed = False
        for key in LEGACY_PROGRESS_KEYS:
            if key in doc:
                doc.pop(key, None)
                changed = True
        if changed:
            touched_users.append(uid)
            if not dry_run:
                _atomic_write_json(pf, doc)

    removed_paths = []
    for target in legacy_top + legacy_user_dirs:
        rel = os.path.relpath(target, root)
        removed_paths.append(rel)
        if not dry_run:
            if os.path.isdir(target) and not os.path.islink(target):
                shutil.rmtree(target)
            elif os.path.exists(target) or os.path.islink(target):
                os.remove(target)

    return {
        "data_dir": root,
        "backup_path": None if dry_run else backup_path,
        "users_scanned": users_scanned,
        "users_touched": len(touched_users),
        "touched_users": touched_users,
        "removed_paths": removed_paths,
        "dry_run": dry_run,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Backup and purge legacy Speaking history from data/."
    )
    parser.add_argument("--data-dir", default=None, help="Path to data directory (default: data/)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without writing or deleting")
    args = parser.parse_args(argv)
    summary = purge_speaking_history(data_dir=args.data_dir, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
