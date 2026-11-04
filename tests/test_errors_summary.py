"""Backlog 11: `tools/errors.py --summary` prints the top 5 groups by count.

Builds its own `data/events` + `data/errors` JSONL fixtures inside a temporary
directory and points the tool at them with B2_DATA_DIR (the same variable
server.py honours), so the real data/ is never read. Run:

    cd tests && python3 test_errors_summary.py
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tools", "errors.py")
TODAY = date.today().isoformat()

tmp = tempfile.mkdtemp(prefix="b2errors-")
DATA = os.path.join(tmp, "data")
os.makedirs(os.path.join(DATA, "events"))
os.makedirs(os.path.join(DATA, "errors"))

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else "FAIL " + str(detail or name)
    if not cond:
        failed.append(name)


def ts(hour, minute, second=0):
    return "%sT%02d:%02d:%02d" % (TODAY, hour, minute, second)


def client_event(endpoint, when, message, status=500):
    return {"n": "fetch_error", "ts": when,
            "p": {"endpoint": endpoint, "status": status, "message_trunc": message}}


def server_event(tb_hash, when, method, path):
    return {"ts": when, "tb_hash": tb_hash, "method": method, "path": path,
            "tb": "Traceback (most recent call last):\n  File \"server.py\"\n"
                  "ValueError: boom"}


events = [
    client_event("/api/broken/a", ts(10, 0), "a error"),
    client_event("/api/broken/a", ts(11, 0), "a error"),
    client_event("/api/broken/a", ts(12, 0), "a error"),
    client_event("/api/broken/b", ts(9, 0), "b error"),
    client_event("/api/broken/b", ts(9, 10), "b error"),
    client_event("/api/broken/c", ts(8, 0), "c error"),
    client_event("/api/broken/d", ts(8, 30), "d error"),
    client_event("/api/broken/e", ts(9, 30), "e error"),
    client_event("/api/broken/f", ts(10, 30), "f error"),
    client_event("/api/broken/g", ts(11, 30), "g error"),
    # Filtered out before grouping: expected status and expected endpoint.
    client_event("/api/broken/expected", ts(7, 0), "expected error", status=404),
    client_event("/api/speaking/token", ts(7, 30), "token error", status=500),
]
errors = [
    server_event("srv-1", ts(12, 1), "POST", "/api/boom"),
    server_event("srv-1", ts(12, 2), "POST", "/api/boom"),
    server_event("srv-1", ts(12, 3), "POST", "/api/boom"),
    server_event("srv-1", ts(12, 4), "POST", "/api/boom"),
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


def summary_rows(stdout):
    rows = []
    for line in stdout.splitlines():
        if line[:1].isdigit():
            count, rest = line.split(None, 1)
            endpoint, first = rest.rsplit(None, 1)
            rows.append({"count": int(count), "endpoint": endpoint.strip(),
                         "first": first})
    return rows


# --- 1. --summary is exactly the top 5, most frequent first ---------------
res = run("--summary")
check("summary_exit", res.returncode == 0, res.stderr)
lines = [l for l in res.stdout.splitlines() if l.strip()]
check("summary_has_header",
      bool(lines) and "COUNT" in lines[0] and "ENDPOINT" in lines[0]
      and "FIRST SEEN" in lines[0], lines[:1])

rows = summary_rows(res.stdout)
check("summary_rows_top5", len(rows) == 5, [r["endpoint"] for r in rows])
check("summary_counts",
      [r["count"] for r in rows] == [4, 3, 2, 1, 1],
      [r["count"] for r in rows])
check("summary_endpoints",
      [r["endpoint"] for r in rows] == [
          "POST /api/boom", "/api/broken/a", "/api/broken/b",
          "/api/broken/c", "/api/broken/d"],
      [r["endpoint"] for r in rows])

# --- 2. Each row carries its real first sighting (earliest ts) ------------
check("summary_first_seen",
      [r["first"] for r in rows] == [
          ts(12, 1), ts(10, 0), ts(9, 0), ts(8, 0), ts(8, 30)],
      [r["first"] for r in rows])

# --- 3. Groups beyond the top 5 and filtered noise stay out --------------
for hidden in ("/api/broken/e", "/api/broken/f", "/api/broken/g",
               "/api/broken/expected", "/api/speaking/token"):
    check("summary_hides_" + hidden.rsplit("/", 1)[-1],
          hidden not in res.stdout, hidden)

# --- 4. The full table still shows every group, so --summary truncates ----
full = run()
check("full_exit", full.returncode == 0, full.stderr)
full_rows = [l for l in full.stdout.splitlines()
             if l.startswith("client") or l.startswith("server")]
check("full_all_groups", len(full_rows) == 8, len(full_rows))
check("full_has_hidden_group", "/api/broken/f" in full.stdout)
check("full_still_filters", "/api/broken/expected" not in full.stdout
      and "/api/speaking/token" not in full.stdout)

# --- 5. --json keeps working and is untouched by --summary ---------------
res = run("--json")
try:
    doc = json.loads(res.stdout)
except ValueError as exc:
    doc = None
    check("json_parses", False, str(exc))
check("json_exit", res.returncode == 0, res.stderr)
check("json_all_groups", isinstance(doc, list) and len(doc) == 8,
      len(doc) if isinstance(doc, list) else type(doc).__name__)

print(json.dumps(out, indent=1))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print("ALL OK")
