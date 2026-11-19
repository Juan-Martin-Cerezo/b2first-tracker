#!/usr/bin/env bash
# tools/backup_push_gdrive.sh -- copy the newest encrypted archives off-host.
#
# Runs after tools/backup_offsite.sh (systemd ExecStartPost). It is deliberately
# soft: if the rclone remote or the rclone binary is missing it prints why and
# exits 0, so a broken off-site destination never fails the local backup.
#
# Remote layout: <REMOTE>:<PATH>/b2first-<ts>.tar.enc (+ .sha256)
# Retention on the remote follows the local window (B2_BACKUP_KEEP_DAYS, 14 d).
set -u

DEST="${B2_BACKUP_DEST:-/mnt/vps_data/backups}"
REMOTE="${B2_GDRIVE_REMOTE:-gdrive}"
RPATH="${B2_GDRIVE_PATH:-b2first-backups}"
KEEP="${B2_BACKUP_KEEP_DAYS:-14}"

log() { echo "gdrive: $*"; }

if ! command -v rclone >/dev/null 2>&1; then
  log "rclone not installed; skipping the off-host copy"
  exit 0
fi
if ! rclone listremotes 2>/dev/null | grep -qx "${REMOTE}:"; then
  log "remote '${REMOTE}:' not configured; skipping (see docs/internal/isms/06-BACKUP-RESTORE.md)"
  exit 0
fi

if [ ! -d "$DEST" ]; then
  log "no local backup directory at $DEST; nothing to push"
  exit 0
fi

NEWEST="$(find "$DEST" -maxdepth 1 -name 'b2first-*.tar.enc' -type f -printf '%T@ %p\n' 2>/dev/null \
          | sort -n | tail -1 | cut -d' ' -f2-)"
if [ -z "${NEWEST:-}" ]; then
  log "no archive found in $DEST; nothing to push"
  exit 0
fi

if ! rclone copy "$NEWEST" "${REMOTE}:${RPATH}/" --no-traverse 2>&1 | sed 's/^/gdrive: /'; then
  log "copy failed for $(basename "$NEWEST")"
  exit 1
fi
if [ -f "$NEWEST.sha256" ]; then
  rclone copy "$NEWEST.sha256" "${REMOTE}:${RPATH}/" --no-traverse 2>&1 | sed 's/^/gdrive: /' || true
fi

# Remote retention: same window as the local one.
rclone delete "${REMOTE}:${RPATH}/" --include 'b2first-*.tar.enc*' --min-age "${KEEP}d" 2>&1 | sed 's/^/gdrive: /' || true

COUNT="$(rclone lsf "${REMOTE}:${RPATH}/" --include 'b2first-*.tar.enc' 2>/dev/null | wc -l | tr -d ' ')"
log "pushed $(basename "$NEWEST"); remote now holds ${COUNT} archive(s), retention ${KEEP}d"
log "PASS: off-host copy done"
exit 0
