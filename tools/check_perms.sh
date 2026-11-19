#!/usr/bin/env bash
# tools/check_perms.sh -- exercise the at-rest permissions claim for data/.
#
# Every directory under the data directory must be 0700 and every file 0600.
# This is the verifiable part of A.8.24 (cryptography at rest): permissions and
# encrypted backups, not home-made crypto on the JSON documents.
#
# Exit codes: 0 = all modes are private (or data/ does not exist), 1 = drift.
#
# Usage: bash tools/check_perms.sh
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${B2_DATA_DIR:-$REPO/data}"

if [ ! -d "$DATA" ]; then
  echo "check_perms: $DATA does not exist; nothing to check"
  exit 0
fi

bad=0
while IFS= read -r path; do
  mode="$(stat -c '%a' "$path" 2>/dev/null)"
  [ "$mode" = "700" ] && continue
  echo "BAD DIR  $mode  $path (expected 700)"
  bad=$((bad + 1))
done < <(find "$DATA" -type d 2>/dev/null)

while IFS= read -r path; do
  mode="$(stat -c '%a' "$path" 2>/dev/null)"
  [ "$mode" = "600" ] && continue
  echo "BAD FILE $mode  $path (expected 600)"
  bad=$((bad + 1))
done < <(find "$DATA" -type f 2>/dev/null)

if [ "$bad" -ne 0 ]; then
  echo "FAIL: $bad path(s) under $DATA are not 0700/0600" >&2
  exit 1
fi

dirs="$(find "$DATA" -type d 2>/dev/null | wc -l | tr -d ' ')"
files="$(find "$DATA" -type f 2>/dev/null | wc -l | tr -d ' ')"
echo "OK: $dirs directories at 0700 and $files files at 0600 under $DATA"
exit 0
