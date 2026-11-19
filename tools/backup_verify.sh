#!/usr/bin/env bash
# tools/backup_verify.sh -- prove the newest encrypted backup is readable.
#
# It never restores over data/. It:
#   1. picks the newest b2first-*.tar.enc in B2_BACKUP_DEST (default
#      /mnt/vps_data/backups), or the file passed as $1;
#   2. re-computes the SHA-256 checksum and compares it with the .sha256 file;
#   3. decrypts into a throwaway directory with B2_BACKUP_PASSPHRASE;
#   4. lists the archive with `tar -tf` and checks that it contains data/.
#
# Exit codes: 0 = verified, 1 = any check failed, 2 = passphrase missing.
#
# Usage:
#   B2_BACKUP_PASSPHRASE=... bash tools/backup_verify.sh [archive.tar.enc]
set -u

DEST="${B2_BACKUP_DEST:-/mnt/vps_data/backups}"
PASSPHRASE="${B2_BACKUP_PASSPHRASE:-}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

if [ -z "$PASSPHRASE" ]; then
  echo "FAIL: B2_BACKUP_PASSPHRASE is not set." >&2
  exit 2
fi

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ]; then
  ARCHIVE="$(ls -1t "$DEST"/b2first-*.tar.enc 2>/dev/null | head -n 1)"
fi
[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || fail "no .tar.enc archive found in $DEST"

CHECK="$ARCHIVE.sha256"
[ -f "$CHECK" ] || fail "checksum file missing: $CHECK"

( cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$CHECK")" ) \
  || fail "SHA-256 checksum mismatch"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/b2f-backup-verify.XXXXXX")" || fail "mktemp failed"
PLAIN="$WORK/archive.tar"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass env:B2_BACKUP_PASSPHRASE -in "$ARCHIVE" -out "$PLAIN" \
  || fail "decryption failed (wrong passphrase or corrupt archive)"

[ -s "$PLAIN" ] || fail "decrypted archive is empty"

LIST="$WORK/list.txt"
tar -tf "$PLAIN" > "$LIST" 2>"$WORK/tar.err" || fail "tar -tf failed: $(cat "$WORK/tar.err")"
[ -s "$LIST" ] || fail "archive contains no files"

if ! grep -qE '^data(/|$)' "$LIST"; then
  fail "archive does not contain a data/ root"
fi

FILES="$(grep -cvE '/$' "$LIST" || true)"
DIRS="$(grep -cE '/$' "$LIST" || true)"
echo "archive   $ARCHIVE"
echo "checksum  OK"
echo "contents  data/ present ($FILES files, $DIRS directories)"
echo "sample"
head -n 8 "$LIST" | sed 's/^/          /'
echo "PASS: newest backup decrypts, matches its checksum and lists its files"
exit 0
