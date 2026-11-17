#!/usr/bin/env bash
# Load-test runner for b2first-tracker.
#
# Starts the real server.py on a free port over a throwaway data directory
# (never the production service on 8088 unless --prod is given), seeds N
# accounts through the API, runs tools/loadtest.py on a concurrency ladder and
# samples the server's CPU, RSS, threads and file descriptors from /proc.
#
# The data dir lives under /var/tmp (ext4) by default: /tmp is tmpfs here, and
# measuring JSON writes on a RAM disk would understate the disk cost.
#
# Usage:
#   bash tools/loadtest_run.sh [--users 400] [--steps "10 25 50 100 200"] \
#       [--duration 30] [--scenario mixed] [--out DIR] [--keep]
#
# Every step starts from the same seeded snapshot, so the ladder is not
# contaminated by tokens, backups or rate-limit state left by the previous one.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PYTHON="${PYTHON:-python3}"
LOADTEST="$HERE/loadtest.py"

HOST="127.0.0.1"
URL=""
PORT=""
USERS=400
DURATION=30
STEPS="10 25 50 100 200"
SCENARIO="mixed"
PROD=0
KEEP=0
OUT=""
PASSWORD="${B2_LOADTEST_PASSWORD:-loadtest-pass-9}"
PREFIX="load"
CREDS=""
SERVER_PID=""
SAMPLER_PID=""
TMPROOT=""
DATA=""
SEED_DIR=""
RESULTS=""
DATA_ROOT="${B2_LOADTEST_ROOT:-/var/tmp}"

die() { echo "error: $*" >&2; exit 1; }

usage() {
  sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --url)        URL="${2:-}"; shift 2 ;;
    --users)      USERS="${2:-}"; shift 2 ;;
    --duration)   DURATION="${2:-}"; shift 2 ;;
    --steps)      STEPS="${2//,/ }"; shift 2 ;;
    --concurrency) STEPS="${2:-}"; shift 2 ;;
    --scenario)   SCENARIO="${2:-}"; shift 2 ;;
    --out)        OUT="${2:-}"; shift 2 ;;
    --creds)      CREDS="${2:-}"; shift 2 ;;
    --password)   PASSWORD="${2:-}"; shift 2 ;;
    --prefix)     PREFIX="${2:-}"; shift 2 ;;
    --prod)       PROD=1; shift ;;
    --keep)       KEEP=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *)            die "unknown argument: $1 (see --help)" ;;
  esac
done

case "$SCENARIO" in
  read|api|write|login|mixed) ;;
  *) die "unknown scenario: $SCENARIO" ;;
esac

if [ "$PROD" = 1 ]; then
  URL="${URL:-http://127.0.0.1:8088}"
  [ -n "$CREDS" ] || die "--prod needs --creds FILE: never seed the live service"
  USERS=0
else
  [ -z "$URL" ] || [[ "$URL" != *:8088* ]] || \
    die "refusing to load-test the production port 8088 without --prod"
fi

TMPROOT="$(mktemp -d "$DATA_ROOT/b2load-XXXXXX")"
DATA="$TMPROOT/data"
SEED_DIR="$TMPROOT/seed"
RESULTS="$TMPROOT/results"
LOG="$TMPROOT/server.log"
RUNLOG="$TMPROOT/run.log"
mkdir -p "$DATA" "$RESULTS"
: > "$RUNLOG"
[ -n "$OUT" ] && mkdir -p "$OUT"

free_port() {
  "$PYTHON" - <<'PY'
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
}

stop_sampler() {
  if [ -n "${SAMPLER_PID:-}" ] && kill -0 "$SAMPLER_PID" 2>/dev/null; then
    kill "$SAMPLER_PID" 2>/dev/null || true
    wait "$SAMPLER_PID" 2>/dev/null || true
  fi
  SAMPLER_PID=""
}

stop_server() {
  if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.2
    done
    kill -9 "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  SERVER_PID=""
}

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  stop_sampler
  stop_server
  if [ "$KEEP" = 1 ]; then
    echo "artifacts kept in $TMPROOT"
  else
    rm -rf "$TMPROOT"
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

wait_health() {
  "$PYTHON" - "$URL/api/health" "$SERVER_PID" <<'PY'
import http.client, os, sys, time
from urllib.parse import urlsplit
url, pid = sys.argv[1], int(sys.argv[2])
parts = urlsplit(url)
deadline = time.time() + 25
while time.time() < deadline:
    try:
        os.kill(pid, 0)
    except OSError:
        sys.exit(2)
    try:
        conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=1)
        conn.request("GET", parts.path)
        resp = conn.getresponse()
        resp.read()
        conn.close()
        if resp.status in (200, 503):
            sys.exit(0)
    except OSError:
        pass
    time.sleep(0.1)
sys.exit(1)
PY
}

start_server() {
  [ -n "$PORT" ] || PORT="$(free_port)"
  URL="http://$HOST:$PORT"
  : > "$LOG"
  env PORT="$PORT" B2_HOST="$HOST" B2_DATA_DIR="$DATA" \
      B2_REGISTER=open B2_DEMO=0 B2_OWNER_PASSWORD="$PASSWORD" \
      B2_RATE_IP_AUTH=0 B2_RATE_IP_ANON=0 B2_RATE_USER_API=0 \
      "$PYTHON" "$ROOT/server.py" >> "$LOG" 2>&1 &
  SERVER_PID=$!
  if ! wait_health; then
    tail -n 40 "$LOG" >&2 || true
    die "server did not become healthy on $URL"
  fi
}

sample_loop() {
  local pid="$1" out="$2" rest ut st now rss thr fds temp
  : > "$out"
  while kill -0 "$pid" 2>/dev/null; do
    rest="$(sed 's/.*) //' "/proc/$pid/stat" 2>/dev/null)" || break
    [ -n "$rest" ] || break
    now="$(date +%s.%N)"
    read -r ut st <<< "$(printf '%s\n' "$rest" | awk '{print $12, $13}')" || true
    rss="$(awk '/^VmRSS:/{print $2}' "/proc/$pid/status" 2>/dev/null || true)"
    thr="$(awk '/^Threads:/{print $2}' "/proc/$pid/status" 2>/dev/null || true)"
    fds="$(ls "/proc/$pid/fd" 2>/dev/null | wc -l || true)"
    temp="$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)"
    printf '%s %s %s %s %s %s %s\n' "$now" "${ut:-0}" "${st:-0}" \
      "${rss:-0}" "${thr:-0}" "${fds:-0}" "${temp:-0}" >> "$out"
    sleep 1
  done
}

start_sampler() {
  sample_loop "$SERVER_PID" "$1" &
  SAMPLER_PID=$!
}

cpu_summary() {
  "$PYTHON" - "$1" "$2" "$3" "$4" <<'PY'
import json, os, sys
samples, out_path, conc, step_path = sys.argv[1:5]
hz = os.sysconf("SC_CLK_TCK")
rows = []
try:
    with open(samples, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != 7:
                continue
            try:
                ts, ut, st, rss, thr, fds, temp = (
                    float(parts[0]), int(parts[1]), int(parts[2]),
                    int(parts[3]), int(parts[4]), int(parts[5]),
                    int(parts[6]))
            except ValueError:
                continue
            if rss == 0 and thr == 0:
                continue
            rows.append((ts, ut + st, rss, thr, fds, temp))
except OSError:
    pass
interval = []
for prev, cur in zip(rows, rows[1:]):
    dt = cur[0] - prev[0]
    if dt > 0:
        interval.append((cur[1] - prev[1]) / hz / dt * 100.0)
if len(rows) >= 2:
    span = rows[-1][0] - rows[0][0]
    avg = (rows[-1][1] - rows[0][1]) / hz / span * 100.0 if span > 0 else 0.0
else:
    avg = 0.0
temps = [r[5] / 1000.0 for r in rows if r[5] > 0]
meta = {
    "concurrency": int(conc),
    "samples": len(rows),
    "cpu_avg_pct": round(avg, 1),
    "cpu_peak_pct": round(max(interval), 1) if interval else 0.0,
    "rss_peak_kb": max((r[2] for r in rows), default=0),
    "threads_peak": max((r[3] for r in rows), default=0),
    "fds_peak": max((r[4] for r in rows), default=0),
    "temp_peak_c": round(max(temps), 1) if temps else 0.0,
    "temp_avg_c": round(sum(temps) / len(temps), 1) if temps else 0.0,
}
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(meta, fh, indent=2)
    fh.write("\n")
try:
    with open(step_path, encoding="utf-8") as fh:
        step = json.load(fh)
except (OSError, ValueError):
    step = {}
overall = step.get("overall", {})
print("step %3s | %7.1f req/s | p50 %6.1f | p95 %6.1f | p99 %6.1f ms | "
      "err %5.2f%% | cpu avg %5.1f%% peak %5.1f%% | rss %4d MB | threads %4d"
      " | %.1f C"
      % (conc, overall.get("rps", 0.0), overall.get("p50_ms", 0.0),
         overall.get("p95_ms", 0.0), overall.get("p99_ms", 0.0),
         100.0 * overall.get("error_rate", 0.0), meta["cpu_avg_pct"],
         meta["cpu_peak_pct"], meta["rss_peak_kb"] // 1024,
         meta["threads_peak"], meta.get("temp_peak_c", 0.0)))
PY
}

seed_users() {
  echo ">>> seeding $USERS accounts on $URL"
  "$PYTHON" "$LOADTEST" --url "$URL" --seed "$USERS" \
      --password "$PASSWORD" --user-prefix "$PREFIX" \
      --seed-threads 8 --creds-out "$CREDS" | tee -a "$RUNLOG"
}

run_step() {
  local conc="$1"
  echo ">>> step concurrency=$conc scenario=$SCENARIO duration=${DURATION}s"
  start_sampler "$RESULTS/step-$conc.cpu.txt"
  "$PYTHON" "$LOADTEST" --url "$URL" --scenario "$SCENARIO" \
      --concurrency "$conc" --duration "$DURATION" \
      --creds "$CREDS" --users "$USERS" --password "$PASSWORD" \
      --xff-pool 4096 --json "$RESULTS/step-$conc.json" \
      >> "$RUNLOG" 2>&1 || echo "warning: loadtest exited non-zero"
  stop_sampler
  cpu_summary "$RESULTS/step-$conc.cpu.txt" \
      "$RESULTS/step-$conc.cpu.json" "$conc" "$RESULTS/step-$conc.json"
}

summarise() {
  "$PYTHON" - "$RESULTS" "$OUT" <<'PY'
import glob, json, os, re, shutil, sys
results, out_dir = sys.argv[1], sys.argv[2]
rows = []
for step_path in glob.glob(os.path.join(results, "step-*.json")):
    match = re.match(r"step-(\d+)\.json$", os.path.basename(step_path))
    if not match:
        continue
    conc = int(match.group(1))
    try:
        with open(step_path, encoding="utf-8") as fh:
            step = json.load(fh)
    except (OSError, ValueError):
        continue
    cpu_path = os.path.join(results, "step-%d.cpu.json" % conc)
    try:
        with open(cpu_path, encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        meta = {"cpu_avg_pct": 0.0, "cpu_peak_pct": 0.0, "rss_peak_kb": 0,
                "threads_peak": 0, "fds_peak": 0}
    rows.append({"concurrency": conc, "load": step, "server": meta})
rows.sort(key=lambda r: r["concurrency"])
if not rows:
    sys.exit(0)
print()
print("| conn | req/s | p50 ms | p95 ms | p99 ms | errs % | cpu avg % | "
      "cpu peak % | rss MB | threads | fds | temp C |")
print("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for row in rows:
    load = row["load"].get("overall", {})
    srv = row["server"]
    print("| %d | %.1f | %.1f | %.1f | %.1f | %.2f | %.1f | %.1f | %d | %d | %d | %.1f |"
          % (row["concurrency"], load.get("rps", 0.0), load.get("p50_ms", 0.0),
             load.get("p95_ms", 0.0), load.get("p99_ms", 0.0),
             100.0 * load.get("error_rate", 0.0), srv["cpu_avg_pct"],
             srv["cpu_peak_pct"], srv["rss_peak_kb"] // 1024,
             srv["threads_peak"], srv["fds_peak"],
             srv.get("temp_peak_c", 0.0)))
if out_dir:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)
        fh.write("\n")
    for path in glob.glob(os.path.join(results, "step-*")):
        shutil.copy2(path, out_dir)
    print("\nwritten to %s" % out_dir)
PY
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "runner: scenario=$SCENARIO users=$USERS duration=${DURATION}s steps=[$STEPS]"
echo "runner: python=$PYTHON root=$ROOT"
"$PYTHON" -m py_compile "$LOADTEST"

if [ "$PROD" = 1 ]; then
  echo "runner: PROD mode — no server start, no seeding, target=$URL"
  for conc in $STEPS; do
    echo ">>> step concurrency=$conc scenario=$SCENARIO duration=${DURATION}s"
    "$PYTHON" "$LOADTEST" --url "$URL" --scenario "$SCENARIO" \
        --concurrency "$conc" --duration "$DURATION" \
        --creds "$CREDS" --users "$USERS" --password "$PASSWORD" \
        --xff-pool 4096 --json "$RESULTS/step-$conc.json" \
        >> "$RUNLOG" 2>&1 || echo "warning: loadtest exited non-zero"
    "$PYTHON" - "$RESULTS/step-$conc.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        report = json.load(fh)
    overall = report["overall"]
    print("step %s | %.1f req/s | p50 %.1f | p95 %.1f | p99 %.1f ms | "
          "err %.2f%%" % (report["concurrency"], overall["rps"],
                          overall["p50_ms"], overall["p95_ms"],
                          overall["p99_ms"], 100.0 * overall["error_rate"]))
except (OSError, ValueError, KeyError):
    pass
PY
  done
  summarise
  exit 0
fi

CREDS="${CREDS:-$TMPROOT/creds.json}"
start_server
seed_users
stop_server
cp -a "$DATA" "$SEED_DIR"

for conc in $STEPS; do
  rm -rf "$DATA"
  cp -a "$SEED_DIR" "$DATA"
  start_server
  run_step "$conc"
  stop_server
done

summarise
echo "runner: ok"
