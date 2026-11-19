# 06 — Backup and Restore

## 1. Objectives (declared, not yet measured in production)

| Objective | Target | Current evidence |
| --- | --- | --- |
| **RPO** (maximum acceptable data loss) | 24 hours for progress; 0 for an accidental overwrite of the current document while the host is alive | Per-save copies keep the previous version, 20 per account (`store.py:293-304`, `434-438`). An encrypted archive job now exists (`tools/backup_offsite.sh`), but no timer schedules it in this repository, so the live RPO is still **operator-dependent** (R08). |
| **RTO** (time to restore service) | 1 hour on the existing host | The data round-trip completes in seconds at drill volume (below). A bare-metal or new-host rebuild, including OS, service unit, secrets and edge, is **untested** and `unverified` (R06). |
| **Restore verification** | Every restore is proven by login and a progress comparison before the service is exposed | `tools/restore_drill.sh` implements this round-trip and exits 0 only when it succeeds. |

Backups protect against: logical corruption, an accidental overwrite, a bad migration, and
host/disk loss (if the off-host copy exists). They do **not** protect against a compromised
root user who also deletes the backups, nor against a supplier-side loss.

## 2. What is backed up

| Layer | Contents | Location | Retention | Evidence |
| --- | --- | --- | --- | --- |
| Per-save | Previous `progress.json` before every write; pre-migration copies | `data/users/<id>/backups/` | 20 newest per account | `store.py:293-304`, `417-439`; `BK_KEEP=20` (`store.py:45`); `tools/retention.py:192-218` |
| Encrypted host archive (shipped) | Whole `data/` as `b2first-<UTC>.tar.enc` + `.sha256` | `B2_BACKUP_DEST`, default `/mnt/vps_data/backups` (local path) | No automatic pruning; operator keeps the newest N | `tools/backup_offsite.sh`, `tools/backup_verify.sh`; run 2026-11-18 in §4 |
| Off-host copy | Not automated | **`unverified`** | **`unverified`** | Intentionally left to the provider: the shipped destination is a local path; rclone/ssh is an operation pending the backup provider |

The shipped archive is encrypted with AES-256-CBC, PBKDF2 (200,000 iterations) and a
random salt, keyed from `B2_BACKUP_PASSPHRASE`. The passphrase is read from the
environment (`-pass env:`), never from argv, a file in the repository, or the audit
log.

## 2.1 Backup and verification commands

```bash
# 1) write one encrypted archive + SHA-256 checksum
B2_BACKUP_PASSPHRASE='<secret>' bash tools/backup_offsite.sh

# optional: different source/destination
B2_DATA_DIR=/srv/b2first/data \
B2_BACKUP_DEST=/mnt/vps_data/backups \
B2_BACKUP_PASSPHRASE='<secret>' bash tools/backup_offsite.sh

# 2) verify the newest archive: checksum, decryption, tar -tf, data/ present
B2_BACKUP_PASSPHRASE='<secret>' bash tools/backup_verify.sh

# 3) prove file modes at rest (independent of the backup)
bash tools/check_perms.sh
```

`backup_offsite.sh` exits 2, before writing anything, when `B2_BACKUP_PASSPHRASE`
is missing. `backup_verify.sh` never extracts over `data/`: it decrypts into a
throwaway directory and only lists the archive.

## 2.2 What is still missing on the host

- No systemd unit/timer ships with the repository, so daily execution depends on the
  operator. R08 remains a documented gap until the timer is installed and its output
  stored in §5.
- The default destination is local (`/mnt/vps_data/backups`). Copying it to another
  machine (rclone/S3/ssh) is pending the backup provider; until then the archive
  protects against logical corruption and disk failure of the data directory, not
  against loss of the whole host.
- Retention is manual: the script never deletes old archives.

The earlier prose-only job (`b2f-data-YYYYmmdd-HHMMSS.tgz`, 14 kept, self-verifying)
is **superseded** by the shipped scripts and is no longer claimed.

## 3. Restore procedure (host-level)

Work on a copy. Never delete the current `data/`.

```bash
# 0) stop writes
sudo systemctl stop b2first.service

# 1) preserve the damaged data — do not delete it
cd /path/to/b2first-tracker
mv data "data.broken-$(date -u +%Y%m%d-%H%M%S)"

# 2) decrypt the chosen archive, then extract it (it contains data/ at its root)
B2_BACKUP_PASSPHRASE='<secret>' \
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in /path/to/backup/b2first-YYYYmmddTHHMMSSZ.tar.enc \
    -out /tmp/b2first-restore.tar
tar tf /tmp/b2first-restore.tar | head        # inspect before extracting
tar xf /tmp/b2first-restore.tar -C /path/to/b2first-tracker
rm -f /tmp/b2first-restore.tar

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

### 4.1 Encrypted backup round-trip (new, 2026-11-18)

Executed in this worktree with `B2_BACKUP_PASSPHRASE=test-pass`. The worktree has no
production data directory, so the archive contains an empty `data/`; the point of the
run is the encryption/checksum/decryption contract, not production volume.

```
$ B2_BACKUP_PASSPHRASE=test-pass bash tools/backup_offsite.sh
NOTE: no data directory at /home/juan/.cache/b2f/wt-isms2/data; creating an empty 0700 one.
backup    /mnt/vps_data/backups/b2first-20261118T210627Z.tar.enc (10272 bytes)
checksum  sha256 86c97c363a3f3ed1e8697c21866c2d7bd8519a7d92d547f292ded1546ecf4e03
source    /home/juan/.cache/b2f/wt-isms2/data
encryption AES-256-CBC, PBKDF2 200000 iterations, salted
NOTE: /mnt/vps_data/backups is a local path. An off-host copy (rclone/ssh) is pending
      the provider; see docs/internal/isms/06-BACKUP-RESTORE.md.
PASS: encrypted backup written

$ B2_BACKUP_PASSPHRASE=test-pass bash tools/backup_verify.sh
b2first-20261118T210627Z.tar.enc: OK
archive   /mnt/vps_data/backups/b2first-20261118T210627Z.tar.enc
checksum  OK
contents  data/ present (0 files, 1 directories)
sample
          data/
PASS: newest backup decrypts, matches its checksum and lists its files

$ bash tools/check_perms.sh
OK: 1 directories at 0700 and 0 files at 0600 under /home/juan/.cache/b2f/wt-isms2/data
```

What this proves: the passphrase gate, AES-256-CBC/PBKDF2 encryption, the SHA-256
sidecar, decryption with the same passphrase, `tar -tf` listing and the `data/`
root are all exercised. What it does **not** prove: an off-host copy, a scheduled
run, or a restore of real production data.

### 4.2 Restore drill (existing)

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
| 2026-11-18T21:06:27Z | `tools/backup_offsite.sh` + `tools/backup_verify.sh` | PASS (exit 0) | `sha256 86c97c36…` | Encrypted empty `data/`; 10,272-byte archive; checksum, decryption and `tar -tf` verified |

Schedule: run quarterly and after any change to `store.py`, the progress schema, or the
account/credential format. Record every run in the table above.

## 6. Gaps

- No backup unit/timer in the repository: `tools/backup_offsite.sh` exists, but daily
  execution is manual until the operator installs a timer (R08).
- The shipped destination is local; no off-host copy or key custody for the archive
  passphrase is documented yet.
- No measured RPO/RTO from a real host failure.
- No automated alert when a backup fails; the job is not run by any shipped scheduler (R15).
- Deleted accounts persist in host backups for the stated 14 days with no purge tool (R05).
- `tools/restore_drill.sh` tests the data contract with synthetic data, not the latest
  production archive. A production archive should also be restored into a scratch directory
  and checked with `tools/verify_audit.py` before it is needed.

## Drill log (executed)

**2026-11-19 10:50 UTC — first automated drill**

- `tools/backup_offsite.sh` → `b2first-20261119T105037Z.tar.enc` (2.2 MB),
  checksum `sha256 d2ec8d699db5637cb553624182962d1b16c72f5027571d83d707e104e74f97aa`,
  AES-256-CBC with PBKDF2 (200 000 iterations), salted.
- `tools/backup_verify.sh` → decrypts, checksum matches, file list read back:
  `users.json`, `usage.json`, `audit.log`, `plans.json`, `users/<id>/progress.json`.
- Result: **PASS**. The archive is usable; nothing was restored over the live data.

**Scheduling (systemd user units, running now)**

- `b2first-backup.timer` — daily at 04:30 with a 15-minute randomized delay,
  `Persistent=true` (runs after a reboot if the window was missed), 14-day retention
  (`B2_BACKUP_KEEP_DAYS`).
- `b2first-backup-verify.timer` — Sundays at 05:30, decrypts and validates the newest
  archive without touching `data/`.
- The passphrase lives in `~/.config/b2first/backup.env` (0600) and is never in the
  repository or in argv.

**Still open (honest gap):** the destination is a local path
(`/mnt/vps_data/backups`). The encrypted copy must be pushed off-host (rclone/ssh or a
provider bucket) before this control can be called complete; that needs credentials and
a destination the operator owns.
