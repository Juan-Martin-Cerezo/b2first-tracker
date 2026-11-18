#!/usr/bin/env bash
# tools/restore_drill.sh -- prove that a data backup restores into a working account.
#
# What it does, end to end, in a throwaway directory:
#   1. builds a synthetic data directory (users.json + users/<id>/progress.json)
#      with a known marker, using the shipped server/store code;
#   2. archives it with tar (the same shape the host backup job uses);
#   3. restores it into a *different* B2_DATA_DIR and reapplies 0700/0600;
#   4. boots server.py against the restored directory on a free loopback port;
#   5. logs in with the restored credentials;
#   6. downloads the restored progress and compares the marker.
#
# Exit codes:
#   0 = the full round-trip worked (archive -> restore -> login -> same progress)
#   1 = any step failed (the failing step prints the reason)
#
# It never touches the repository's real data/ and never needs the network.
# Dependencies: bash, python3, tar. Usage: bash tools/restore_drill.sh
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/b2f-restore-drill.XXXXXX")"
SRC="$WORK/source/data"
RESTORED="$WORK/restored/data"
ARCHIVE="$WORK/b2f-data-drill.tar.gz"
LOG="$WORK/server.log"
SERVER_PID=""

DRILL_USER="drill-user"
DRILL_PASS="drill-pass-9"
DRILL_MARKER="restore-drill-$(date -u +%Y%m%dT%H%M%SZ)-$$"

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  echo "work directory kept for inspection: $WORK" >&2
  # Do not delete on failure: disable the cleanup trap.
  trap - EXIT
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  exit 1
}

step() { printf '%-11s %s\n' "$1" "$2"; }

mkdir -p "$SRC" "$RESTORED" || fail "cannot create the work directories"

# ---------------------------------------------------------------------------
# 1. Build the source data set with the application's own code.
# ---------------------------------------------------------------------------
export REPO DRILL_MARKER
UID_DRILL="$(B2_DATA_DIR="$SRC" python3 - <<'PY'
import os
import sys

sys.path.insert(0, os.environ["REPO"])
import server as S  # noqa: E402
import store  # noqa: E402

uid, err = S.register_user("drill-user", "drill-pass-9")
if err or not uid:
    print("REGISTER_FAILED:" + str(err), file=sys.stderr)
    raise SystemExit(2)

marker = os.environ["DRILL_MARKER"]
store.put_progress(uid, {
    "schema_version": 2,
    "log": [{"type": "drill", "marker": marker}],
    "errs": [],
    "settings": {"drill": marker},
    "profile": None,
    "onboarded": True,
})
print(uid)
PY
)" || fail "could not build the source data set"

[ -n "$UID_DRILL" ] || fail "source user id is empty"
step "source" "user=$UID_DRILL data=$SRC"

# ---------------------------------------------------------------------------
# 2. Archive (the backup).
# ---------------------------------------------------------------------------
tar czf "$ARCHIVE" -C "$SRC" . || fail "tar could not create the archive"
step "backup" "$(basename "$ARCHIVE") ($(wc -c < "$ARCHIVE") bytes)"

# Prove the archive really contains the two pieces the drill restores.
tar tzf "$ARCHIVE" | grep -q './users.json' || fail "archive has no users.json"
tar tzf "$ARCHIVE" | grep -q "./users/$UID_DRILL/progress.json" \
  || fail "archive has no users/$UID_DRILL/progress.json"

# ---------------------------------------------------------------------------
# 3. Restore into a fresh data directory and reapply the private modes.
# ---------------------------------------------------------------------------
tar xzf "$ARCHIVE" -C "$RESTORED" || fail "tar could not extract the archive"
find "$RESTORED" -type d -exec chmod 700 {} + || fail "chmod 700 failed"
find "$RESTORED" -type f -name '*.json' -exec chmod 600 {} + || fail "chmod 600 failed"
step "restore" "extracted into $RESTORED"

# ---------------------------------------------------------------------------
# 4. Boot an isolated server against the restored data.
# ---------------------------------------------------------------------------
PORT="$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)" || fail "could not allocate a free port"

B2_DATA_DIR="$RESTORED" PORT="$PORT" B2_HOST=127.0.0.1 B2_DEMO=0 B2_REGISTER=closed \
  python3 "$REPO/server.py" >"$LOG" 2>&1 &
SERVER_PID=$!

python3 - "$PORT" <<'PY' || fail "restored server did not become healthy (see $LOG)"
import sys
import time
import urllib.error
import urllib.request

url = "http://127.0.0.1:%s/api/health" % sys.argv[1]
for _ in range(60):
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status == 200:
                sys.exit(0)
    except (urllib.error.URLError, OSError):
        time.sleep(0.25)
sys.exit(1)
PY
step "server" "isolated instance on 127.0.0.1:$PORT (data=$RESTORED)"

# ---------------------------------------------------------------------------
# 5 + 6. Login with the restored account and compare the restored progress.
# ---------------------------------------------------------------------------
python3 - "$PORT" "$UID_DRILL" "$DRILL_MARKER" <<'PY' || fail "login or progress comparison failed"
import json
import sys
import urllib.error
import urllib.request

port, uid, marker = sys.argv[1], sys.argv[2], sys.argv[3]
base = "http://127.0.0.1:%s" % port


def call(path, payload=None, token=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


status, body = call("/api/login", {"name": "drill-user", "password": "drill-pass-9"})
if status != 200:
    raise SystemExit("login failed: HTTP %s %s" % (status, body[:200]))
token = json.loads(body).get("token") or ""
if not token:
    raise SystemExit("login returned no token")

status, body = call("/api/progress?download=1&user=" + uid, token=token)
if status != 200:
    raise SystemExit("progress download failed: HTTP %s %s" % (status, body[:200]))
doc = json.loads(body)
if doc.get("log", [{}])[0].get("marker") != marker:
    raise SystemExit("restored log marker mismatch")
if (doc.get("settings") or {}).get("drill") != marker:
    raise SystemExit("restored settings marker mismatch")

print("login ok: user=%s" % uid)
print("progress ok: log[0].marker and settings.drill == %s" % marker)
PY

step "result" "round-trip complete: archive -> restore -> login -> identical progress"
echo "PASS: restore drill succeeded"
exit 0
