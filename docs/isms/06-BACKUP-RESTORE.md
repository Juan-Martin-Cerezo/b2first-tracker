# 06 — Backup and Restore

## 1. Objectives (declared, not yet measured in production)

| Objective | Target | Current evidence |
| --- | --- | --- |
| **RPO** (maximum acceptable data loss) | 24 hours for progress; 0 for an accidental overwrite of the current document while the host is alive | Per-save copies keep the previous version, 20 per account (`store.py:293-304`, `434-438`). A daily host archive is described in `SECURITY.md §4`, 14 kept, but **no backup unit, timer or script exists in the repository** — the live RPO is `unverified` (R08). |
| **RTO** (time to restore service) | 1 hour on the existing host | The data round-trip completes in seconds at drill volume (below). A bare-metal or new-host rebuild, including OS, service unit, secrets and edge, is **untested** and `unverified` (R06). |
| **Restore verification** | Every restore is proven by login and a progress comparison before the service is exposed | `tools/restore_drill.sh` implements this round-trip and exits 0 only when it succeeds. |

Backups protect against: logical corruption, an accidental overwrite, a bad migration, and
host/disk loss (if the off-host copy exists). They do **not** protect against a compromised
root user who also deletes the backups, nor against a supplier-side loss.

## 2. What is backed up

| Layer | Contents | Location | Retention | Evidence |
| --- | --- | --- | --- | --- |
| Per-save | Previous `progress.json` before every write; pre-migration copies | `data/users/<id>/backups/` | 20 newest per account | `store.py:293-304`, `417-439`; `BK_KEEP=20` (`store.py:45`); `tools/retention.py:192-218` |
| Host archive (claimed) | Whole `data/` as `b2f-data-YYYYmmdd-HHMMSS.tgz` | A backup directory outside the repository; exact path **unverified** | 14 newest | `SECURITY.md §4` — prose only; no script in `tools/` |
| Off-host copy | Not documented | **`unverified`** | **`unverified`** | No evidence in the repository |

The host archive is claimed to verify itself on every run: `tar -tzf`, a test extraction,
and `json.load` on every restored `.json`; it is supposed to print `B2F BACKUP FAIL: ...`
and keep 14 archives (`SECURITY.md §4`). None of that job is present in this repository, so
it is **not** claimed as an implemented control.

## 3. Restore procedure (host-level)

Work on a copy. Never delete the current `data/`.

```bash
# 0) stop writes
sudo systemctl stop b2first.service

# 1) preserve the damaged data — do not delete it
cd /path/to/b2first-tracker
mv data "data.broken-$(date -u +%Y%m%d-%H%M%S)"

# 2) extract the chosen archive (it contains data/ at its root)
tar xzf /path/to/backup/b2f-data-YYYYmmdd-HHMMSS.tgz -C /path/to/b2first-tracker

# 3) restore private modes
find data -type d -exec chmod 700 {} +
find data -type f -name '*.json' -exec chmod 600 {} +

# 4) verify the audit chain before exposing the service
python3 tools/verify_audit.py data

# 5) prove the data before starting the real unit
bash tools/restore_drill.sh

# 6) start and check
sudo systemctl start b2first.service
curl -s http://127.0.0.1:8088/api/health
# → {"ok": true, ...}

# 7) log in with a known account and compare a visible progress value
```

If step 4 reports a broken chain, keep the archive and the extracted copy and open an
incident (`04-INCIDENT-RESPONSE.md`); do not "fix" the chain by hand.

## 4. Restore drill — executed 2026-11-18

`tools/restore_drill.sh` is a self-contained, network-free proof of the data contract. It:

1. creates a synthetic `data/` with `users.json` and `users/<id>/progress.json` using the
   real `server.register_user` / `store.put_progress` code, with a unique marker;
2. archives it with `tar czf` and asserts the archive contains both `users.json` and the
   progress file;
3. restores it into a **different** `B2_DATA_DIR` and reapplies `0700`/`0600`;
4. boots `server.py` against the restored directory on a free loopback port;
5. logs in with the restored password;
6. downloads the restored progress and compares `log[0].marker` and `settings.drill`.

It exits 0 only if every step succeeds. It does not touch the repository's `data/` and does
not need the network.

Actual output (verbatim):

```
source      user=drill-user data=/tmp/b2f-restore-drill.BFUpwp/source/data
backup      b2f-data-drill.tar.gz (504 bytes)
restore     extracted into /tmp/b2f-restore-drill.BFUpwp/restored/data
server      isolated instance on 127.0.0.1:60121 (data=/tmp/b2f-restore-drill.BFUpwp/restored/data)
login ok: user=drill-user
progress ok: log[0].marker and settings.drill == restore-drill-20261118T000421Z-557668
result      round-trip complete: archive -> restore -> login -> identical progress
PASS: restore drill succeeded
```

What this proves:

- The archive/restore shape works for `users.json` and a user's `progress.json`.
- Credentials survive the restore (login succeeded against the restored `users.json`).
- The restored progress is byte-equivalent in the compared fields.
- The server boots against a restored directory and answers `/api/health`.

What it does **not** prove:

- That a production host backup job exists, runs daily, or is copied off-host (R08).
- That the real archive is readable, encrypted, or retained for 14 days.
- That the per-save backup rotation or `tools/retention.py` behaves on production data.
- That a new host can be rebuilt within the RTO, including the edge, secrets and systemd.

## 5. Drill log

| Date (UTC) | Script | Result | Marker | Notes |
| --- | --- | --- | --- | --- |
| 2026-11-18T00:04:21Z | `tools/restore_drill.sh` | PASS (exit 0) | `restore-drill-20261118T000421Z-557668` | Synthetic data; 504-byte archive; isolated server on port 60121 |

Schedule: run quarterly and after any change to `store.py`, the progress schema, or the
account/credential format. Record every run in the table above.

## 6. Gaps

- No backup unit/timer/script in the repository; the daily job is prose only (R08).
- No documented off-host destination, encryption at rest, or key custody for the archive.
- No measured RPO/RTO from a real host failure.
- No automated alert when a backup fails; the job is not run by any shipped scheduler (R15).
- Deleted accounts persist in host backups for the stated 14 days with no purge tool (R05).
- `tools/restore_drill.sh` tests the data contract with synthetic data, not the latest
  production archive. A production archive should also be restored into a scratch directory
  and checked with `tools/verify_audit.py` before it is needed.
