#!/usr/bin/env bash
# tools/backup_offsite.sh -- encrypted archive of the data directory.
#
# What it does:
#   1. archives the whole data directory (default <repo>/data, override with
#      B2_DATA_DIR) with tar;
#   2. encrypts it with AES-256-CBC, PBKDF2 (200,000 iterations) and a random
#      salt, keyed from B2_BACKUP_PASSPHRASE (the passphrase is read from the
#      environment, never from argv or a file in the repository);
#   3. writes b2first-<UTC timestamp>.tar.enc plus its .sha256 checksum into
#      B2_BACKUP_DEST (default /mnt/vps_data/backups).
#
# Exit codes:
#   0 = archive and checksum written
#   2 = B2_BACKUP_PASSPHRASE is not set (clear error, nothing written)
#   1 = any other failure (tar, openssl, checksum)
#
# The default destination is a LOCAL path on this host. Copying it to another
# machine (rclone/ssh) is an operation pending the backup provider; it is
# documented in docs/internal/isms/06-BACKUP-RESTORE.md and is not performed
# here. The script says so on every run.
#
# Usage: B2_BACKUP_PASSPHRASE=... bash tools/backup_offsite.sh
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${B2_DATA_DIR:-$REPO/data}"
DEST="${B2_BACKUP_DEST:-/mnt/vps_data/backups}"
PASSPHRASE="${B2_BACKUP_PASSPHRASE:-}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

if [ -z "$PASSPHRASE" ]; then
  echo "FAIL: B2_BACKUP_PASSPHRASE is not set." >&2
  echo "      Export the passphrase in the environment, e.g." >&2
  echo "      B2_BACKUP_PASSPHRASE='...' bash tools/backup_offsite.sh" >&2
  exit 2
fi

if [ ! -d "$DATA" ]; then
  echo "NOTE: no data directory at $DATA; creating an empty 0700 one."
  mkdir -p "$DATA" 2>/dev/null || fail "cannot create $DATA"
  chmod 700 "$DATA" || fail "cannot chmod 700 $DATA"
fi

mkdir -p "$DEST" 2>/dev/null || fail "cannot create destination $DEST"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="b2first-$STAMP.tar.enc"
OUT="$DEST/$NAME"
PARENT="$(dirname "$DATA")"
BASE="$(basename "$DATA")"

tar -C "$PARENT" -cf - "$BASE" \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
      -pass env:B2_BACKUP_PASSPHRASE -out "$OUT" \
  || fail "tar/openssl pipeline failed"

[ -s "$OUT" ] || fail "encrypted archive is empty: $OUT"

( cd "$DEST" && sha256sum "$NAME" > "$NAME.sha256" ) \
  || fail "could not write checksum"

SIZE="$(wc -c < "$OUT" | tr -d ' ')"
SUM="$(cut -d' ' -f1 "$OUT.sha256")"
echo "backup    $OUT ($SIZE bytes)"
echo "checksum  sha256 $SUM"
echo "source    $DATA"
echo "encryption AES-256-CBC, PBKDF2 200000 iterations, salted"
echo "NOTE: $DEST is a local path. An off-host copy (rclone/ssh) is pending"
echo "      the provider; see docs/internal/isms/06-BACKUP-RESTORE.md."
# Retention: keep two weeks of encrypted archives (override with
# B2_BACKUP_KEEP_DAYS). Deleting only our own pattern, never anything else.
KEEP="${B2_BACKUP_KEEP_DAYS:-14}"
REMOVED="$(find "$DEST" -maxdepth 1 -name 'b2first-*.tar.enc*' -type f -mtime "+$KEEP" -print -delete | wc -l | tr -d ' ')"
echo "retention kept ${KEEP}d, pruned ${REMOVED} old file(s)"
echo "PASS: encrypted backup written"
exit 0
