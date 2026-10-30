#!/usr/bin/env python3
"""Report which PRACTICE_SOURCES URLs resolve.

Stdlib only. Reads index.html, extracts the PRACTICE_SOURCES array and sends a
HEAD request per URL with a browser-like User-Agent and a 5 s timeout. This is
a manual report, NOT a gate: the Playwright suite never touches the internet.

Usage:
    python3 tools/check_sources.py
"""
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "index.html"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 5


def sources():
    text = HTML.read_text(encoding="utf-8")
    block = re.search(r"PRACTICE_SOURCES\s*=\s*\[(.*?)\];", text, re.S)
    if not block:
        raise SystemExit("PRACTICE_SOURCES array not found in index.html")
    return re.findall(r'n:"([^"]+)"\s*,\s*url:"([^"]+)"', block.group(1))


def check(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, "HTTP error"
    except Exception as e:  # timeout, DNS, TLS, connection reset
        return None, type(e).__name__


def main():
    rows = sources()
    reachable = []
    blocked = []
    failed = []
    for name, url in rows:
        status, note = check(url)
        if status is not None and 200 <= status < 400:
            reachable.append((name, status))
            print(f"OK    {status}  {name}")
        elif status in (403, 405):
            blocked.append((name, status))
            print(f"HEAD  {status}  {name}  (reachable in a browser; HEAD rejected)")
        else:
            failed.append((name, status, note))
            print(f"FAIL  {status or note}  {name}  {url}")

    print()
    print(
        f"{len(reachable)}/{len(rows)} reachable to HEAD; "
        f"{len(blocked)} rejected HEAD; {len(failed)} failed"
    )
    if blocked:
        print("HEAD-rejected: " + ", ".join(f"{n} ({s})" for n, s in blocked))
    if failed:
        print(
            "Failed: "
            + ", ".join(f"{n} ({s or note})" for n, s, note in failed)
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
