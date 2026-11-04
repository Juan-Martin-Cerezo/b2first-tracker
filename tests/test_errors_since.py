"""Backlog 23: `tools/errors.py --since HH:MM` counts only recent events, and
`--json` is documented in `--help`.

Fixtures are written into a temporary directory handed to the tool with
B2_DATA_DIR, so the real data/ is never read. Event stamps are computed the
way the server writes them (UTC) from a local clock time, so the expectations
hold in any timezone. Run:

    cd tests && python3 test_errors_since.py
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tools", "errors.py")
TODAY = date.today().isoformat()

tmp = tempfile.mkdtemp(prefix="b2errors-since-")
DATA = os.path.join(tmp, "data")
os.makedirs(os.path.join(DATA, "events"))
os.makedirs(os.path.join(DATA, "errors"))

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else "FAIL " + str(detail or name)
    if not cond:
        failed.append(name)


def utc_stamp(hh, mm, second=0):
    """The UTC stamp server.py would write for a local clock time today."""
    local = datetime.combine(date.today(), time(hh, mm, second))
    return local.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def client_event(endpoint, hh, mm, message, status=500):
    return {"n": "fetch_error", "ts": utc_stamp(hh, mm),
            "p": {"endpoint": endpoint, "status": status, "message_trunc": message}}


def server_event(tb_hash, hh, mm, method, path):
    return {"ts": utc_stamp(hh, mm), "tb_hash": tb_hash, "method": method, "path": path,
            "tb": "Traceback (most recent call last):\n  File \"server.py\"\n"
                  "ValueError: boom"}


events = [
    client_event("/api/broken/early", 8, 0, "early broke"),
    client_event("/api/broken/early", 8, 10, "early broke"),
    client_event("/api/broken/early", 8, 20, "early broke"),
    client_event("/api/broken/mixed", 9, 0, "mixed broke"),
    client_event("/api/broken/mixed", 10, 15, "mixed broke"),
    client_event("/api/broken/mixed", 10, 45, "mixed broke"),
    client_event("/api/broken/late", 11, 0, "late broke"),
    client_event("/api/broken/late", 11, 30, "late broke"),
    # Exactly on the cutoff: it must be counted.
    client_event("/api/broken/edge", 10, 0, "edge broke"),
    client_event("/api/broken/expected", 11, 10, "expected broke", status=404),
]
errors = [
    server_event("srv-old", 9, 0, "POST", "/api/old"),
    server_event("srv-new", 10, 30, "POST", "/api/new"),
    server_event("srv-new", 10, 40, "POST", "/api/new"),
]

with open(os.path.join(DATA, "events", TODAY + ".jsonl"), "w", encoding="utf-8") as fh:
    for ev in events:
        fh.write(json.dumps(ev) + "\n")
with open(os.path.join(DATA, "errors", TODAY + ".jsonl"), "w", encoding="utf-8") as fh:
    for ev in errors:
        fh.write(json.dumps(ev) + "\n")

ENV = dict(os.environ, B2_DATA_DIR=DATA)


def run(*flags):
    return subprocess.run([sys.executable, TOOL, "--days", "1", *flags],
                          capture_output=True, text=True, env=ENV, cwd=REPO)


def table_rows(stdout):
    return [l for l in stdout.splitlines()
            if l.startswith("client") or l.startswith("server")]


def summary_rows(stdout):
    rows = []
    for line in stdout.splitlines():
        if line[:1].isdigit():
            count, rest = line.split(None, 1)
            endpoint, first = rest.rsplit(None, 1)
            rows.append({"count": int(count), "endpoint": endpoint.strip(),
                         "first": first})
    return rows


# --- 1. Without --since, everything today is grouped ----------------------
base = run()
check("base_exit", base.returncode == 0, base.stderr)
check("base_all_groups", len(table_rows(base.stdout)) == 6,
      len(table_rows(base.stdout)))
check("base_early_counted", "/api/broken/early" in base.stdout)

# --- 2. --since keeps only what happened at or after the clock time ------
res = run("--since", "10:00")
check("since_exit", res.returncode == 0, res.stderr)
rows = table_rows(res.stdout)
check("since_groups", len(rows) == 4, len(rows))
for gone in ("/api/broken/early", "/api/old", "/api/broken/expected"):
    check("since_drops_" + gone.rsplit("/", 1)[-1], gone not in res.stdout, gone)
check("since_keeps_edge", "/api/broken/edge" in res.stdout)
check("since_keeps_server", "/api/new" in res.stdout)

# --- 3. Counts and first sightings only see the events after the cutoff --
res = run("--since", "10:00", "--summary")
check("summary_exit", res.returncode == 0, res.stderr)
srows = summary_rows(res.stdout)
check("summary_rows", len(srows) == 4, srows)
check("summary_counts", [r["count"] for r in srows] == [2, 2, 2, 1],
      [r["count"] for r in srows])
check("summary_first_seen",
      {r["endpoint"]: r["first"] for r in srows} == {
          "/api/broken/mixed": utc_stamp(10, 15),
          "POST /api/new": utc_stamp(10, 30),
          "/api/broken/late": utc_stamp(11, 0),
          "/api/broken/edge": utc_stamp(10, 0),
      }, srows)

# --- 4. --json carries the same filtered rows ----------------------------
res = run("--since", "10:00", "--json")
check("json_exit", res.returncode == 0, res.stderr)
try:
    doc = json.loads(res.stdout)
except ValueError as exc:
    doc = None
    check("json_parses", False, str(exc))
check("json_rows", isinstance(doc, list) and len(doc) == 4,
      len(doc) if isinstance(doc, list) else type(doc).__name__)
by_hash = {r["hash"]: r for r in doc or []}
check("json_hashes", sorted(by_hash) == ["edge broke", "late broke",
                                         "mixed broke", "srv-new"],
      sorted(by_hash))
check("json_mixed_count", by_hash.get("mixed broke", {}).get("count") == 2,
      by_hash.get("mixed broke"))
check("json_mixed_first",
      by_hash.get("mixed broke", {}).get("first") == utc_stamp(10, 15),
      by_hash.get("mixed broke"))

# --- 5. A cutoff after every fixture leaves nothing ----------------------
res = run("--since", "23:59")
check("empty_exit", res.returncode == 0, res.stderr)
check("empty_message", "No errors since 23:59 today." in res.stdout, res.stdout)
res = run("--since", "23:59", "--json")
check("empty_json", json.loads(res.stdout) == [], res.stdout)

# --- 6. A malformed clock time is rejected, not ignored ------------------
for bad in ("10:75", "abc", "1000"):
    res = run("--since", bad)
    check("rejects_" + bad, res.returncode == 2, res.returncode)
    check("rejects_message_" + bad, "HH:MM" in res.stderr, res.stderr)

# --- 7. --json documents its output in --help ----------------------------
help_out = subprocess.run([sys.executable, TOOL, "--help"],
                          capture_output=True, text=True, env=ENV, cwd=REPO)
check("help_exit", help_out.returncode == 0, help_out.stderr)
flat = " ".join(help_out.stdout.split())
check("help_json_described", "--json" in flat and "JSON array" in flat, flat)
check("help_documents_fields",
      "side, hash, kind, count, first, last, days, sample, paths" in flat, flat)
check("help_since_documented", "--since HH:MM" in flat and "--since 10:30" in flat, flat)

print(json.dumps(out, indent=1))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print("ALL OK")
