#!/usr/bin/env python3
"""Group client and server errors so a new one can be spotted in seconds.

Reads the same files the app already writes:
  data/events/YYYY-MM-DD.jsonl   client events, `js_error` / `fetch_error`
  data/errors/YYYY-MM-DD.jsonl   unhandled server exceptions (traceback)

Usage:
  tools/errors.py                 last 7 days, grouped, most frequent first
  tools/errors.py --days 1        today only
  tools/errors.py --since 10:30   only what happened today at or after 10:30
  tools/errors.py --new           only groups first seen in the last 24 h
  tools/errors.py --json          machine-readable (used by the alert cron)
  tools/errors.py --summary       top 5 groups: count, endpoint, first seen

--json prints an array of group objects, one per error group:
  side      "client" or "server"
  hash      stack_hash / tb_hash, or a message prefix when there is no hash
  kind      the client event name ("js_error" / "fetch_error") or "server 500"
  count     events in the group inside the window (--since applied)
  first     earliest timestamp seen, as written to the JSONL file
  last      latest timestamp seen
  days      number of distinct days the group appeared on
  sample    one message, or the last line of the traceback
  paths     up to three endpoints (client) or "METHOD /path" (server)

--since reads a clock time, not a date: only today's events at or after
HH:MM are counted, which is the useful window right after a deploy. HH:MM is
the machine's local clock (the same one --days uses); the files stamp UTC, so
the cutoff is converted before comparing.

Exit code is 1 when --new finds anything, so a cron can alert on it.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("B2_DATA_DIR") or os.path.join(ROOT, "data")
SUMMARY_TOP = 5

# Statuses that mean "the client asked for something it cannot have", not "the app broke":
# auth/plan/method/size/rate limits are expected and would drown the real failures.
EXPECTED_STATUS = {400, 401, 402, 403, 404, 405, 409, 413, 429, 451, 503}
EXPECTED_ENDPOINTS = ("/api/speaking/token",)


def iter_jsonl(path):
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def day_files(name, days):
    d = os.path.join(DATA, name)
    today = date.today()
    for i in range(days):
        yield os.path.join(d, (today - timedelta(days=i)).isoformat() + ".jsonl")


def parse_hhmm(value):
    """`--since` takes a clock time (HH:MM, 24 h); return it normalised."""
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except ValueError:
        raise argparse.ArgumentTypeError(
            "expected HH:MM on the 24-hour clock, got %r" % value)


def since_cutoff(hhmm):
    """UTC timestamp string for today at `hhmm` local, matching the file stamps."""
    local = datetime.combine(date.today(), datetime.strptime(hhmm, "%H:%M").time())
    return local.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def collect(days, cutoff=None):
    groups = defaultdict(lambda: {"count": 0, "first": None, "last": None,
                                  "days": set(), "kind": "", "sample": "",
                                  "paths": set()})
    for path in day_files("events", days):
        for ev in iter_jsonl(path):
            if cutoff is not None and (ev.get("ts") or "") < cutoff:
                continue
            if ev.get("n") not in ("js_error", "fetch_error"):
                continue
            props = ev.get("p") or {}
            if props.get("status") in EXPECTED_STATUS:
                continue
            endpoint = str(props.get("endpoint") or "")
            if any(endpoint.startswith(e) for e in EXPECTED_ENDPOINTS):
                continue
            key = props.get("stack_hash") or (props.get("message_trunc") or "")[:40] or "unknown"
            g = groups[("client", key)]
            g["kind"] = ev.get("n")
            g["count"] += 1
            g["sample"] = props.get("message_trunc") or g["sample"]
            if props.get("endpoint"):
                g["paths"].add(str(props["endpoint"])[:80])
            mark(g, ev.get("ts"))
    for path in day_files("errors", days):
        for ev in iter_jsonl(path):
            if cutoff is not None and (ev.get("ts") or "") < cutoff:
                continue
            key = ev.get("tb_hash") or "unknown"
            g = groups[("server", key)]
            g["kind"] = "server 500"
            g["count"] += 1
            lines = [l for l in (ev.get("tb") or "").strip().splitlines() if l.strip()]
            g["sample"] = lines[-1][:160] if lines else g["sample"]
            if ev.get("path"):
                g["paths"].add("%s %s" % (ev.get("method", ""), ev["path"]))
            mark(g, ev.get("ts"))
    out = []
    for (side, key), g in groups.items():
        out.append({
            "side": side, "hash": key, "kind": g["kind"], "count": g["count"],
            "first": g["first"], "last": g["last"], "days": len(g["days"]),
            "sample": g["sample"], "paths": sorted(g["paths"])[:3],
        })
    out.sort(key=lambda r: (-r["count"], r["first"] or ""))
    return out


def mark(g, ts):
    if not ts:
        return
    g["days"].add(ts[:10])
    if g["first"] is None or ts < g["first"]:
        g["first"] = ts
    if g["last"] is None or ts > g["last"]:
        g["last"] = ts


def print_summary(rows, top=SUMMARY_TOP):
    print("%-6s %-44s %s" % ("COUNT", "ENDPOINT", "FIRST SEEN"))
    for r in rows[:top]:
        endpoint = r["paths"][0] if r["paths"] else "-"
        print("%-6d %-44s %s" % (r["count"], endpoint[:44], r["first"] or "?"))


def main():
    ap = argparse.ArgumentParser(description="Group client and server errors")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--since", metavar="HH:MM", type=parse_hhmm, default=None,
                    help="only events at or after this local clock time today "
                         "(e.g. --since 10:30)")
    ap.add_argument("--new", action="store_true", help="only first seen in the last 24 h")
    ap.add_argument("--json", action="store_true",
                    help="print every group as a JSON array: side, hash, kind, count, "
                         "first, last, days, sample, paths")
    ap.add_argument("--summary", action="store_true",
                    help="top 5 groups by count, with endpoint and first seen")
    args = ap.parse_args()

    cutoff = since_cutoff(args.since) if args.since else None
    rows = collect(max(args.days, 1), cutoff)
    if args.new:
        new_cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
        rows = [r for r in rows if (r["first"] or "") >= new_cutoff]
    empty = ("No errors since %s today." % args.since if args.since
             else "No errors in the last %d day(s)." % args.days)

    if args.json:
        json.dump(rows, sys.stdout, indent=1)
        sys.stdout.write("\n")
    elif args.summary:
        if not rows:
            print(empty)
        else:
            print_summary(rows)
    elif not rows:
        print(empty)
    else:
        print("%-6s %-7s %-8s %-20s %-19s %s" % ("SIDE", "COUNT", "DAYS", "FIRST SEEN", "HASH", "SAMPLE"))
        for r in rows:
            print("%-6s %-7d %-8d %-20s %-19s %s" % (
                r["side"], r["count"], r["days"], r["first"] or "?", r["hash"][:16],
                (r["sample"] or "")[:70]))
            for p in r["paths"]:
                print("           at %s" % p)

    if args.new and rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
