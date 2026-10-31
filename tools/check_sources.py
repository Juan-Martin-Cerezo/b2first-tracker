#!/usr/bin/env python3
"""Report which PRACTICE_SOURCES URLs resolve.

Stdlib only. Reads index.html, extracts the PRACTICE_SOURCES array and fetches
each URL with a GET request and a full set of browser headers, then checks that
the response is 2xx AND carries a <title> (so a soft 404 or an error page is not
mistaken for a working link).

Why GET and not HEAD: learnenglish.britishcouncil.org sits behind Akamai's bot
manager. A bare HEAD (or a GET with only a User-Agent) is rejected with 403
"Access Denied" or a dropped HTTP/2 stream from this Raspberry Pi, even though
the page loads fine in a browser. Sending the headers a real navigation sends
(User-Agent, Accept, Accept-Language, Sec-Fetch-*) gets a normal 200. The same
false negative also produced spurious TimeoutErrors because urllib reports the
reset stream as a timeout.

This is a manual report, NOT a gate: the Playwright suite never touches the internet.

Usage:
    python3 tools/check_sources.py
"""
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "index.html"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    # identity keeps the body readable without gzip/br handling from stdlib.
    "Accept-Encoding": "identity",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Connection": "close",
}
TIMEOUT = 20
MAX_BYTES = 512 * 1024
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def sources():
    text = HTML.read_text(encoding="utf-8")
    block = re.search(r"PRACTICE_SOURCES\s*=\s*\[(.*?)\];", text, re.S)
    if not block:
        raise SystemExit("PRACTICE_SOURCES array not found in index.html")
    return re.findall(r'n:"([^"]+)"\s*,\s*url:"([^"]+)"', block.group(1))


def _body(response):
    """Read at most MAX_BYTES of a response and decode it to text."""
    raw = response.read(MAX_BYTES)
    charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, "replace")


def check(url):
    """GET the URL. Returns (status, title, note); status None means network error."""
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = _body(r)
            m = TITLE_RE.search(body)
            title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            return r.status, title, "" if body else "empty body"
    except urllib.error.HTTPError as e:
        return e.code, "", f"HTTP error ({e.reason})"
    except Exception as e:  # timeout, DNS, TLS, connection reset
        return None, "", type(e).__name__


def host_blocked(url):
    """True when the *host* rejects us, not just this path.

    Akamai-fronted hosts (learnenglish.britishcouncil.org) answer 403 to unknown
    paths, so a 403 on one URL is ambiguous. Fetching the site root tells the two
    cases apart: root 2xx => the host serves us and this specific URL is bad;
    root also 403/429 => the host is blocking this IP/request outright.
    """
    parts = urllib.parse.urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}/"
    try:
        req = urllib.request.Request(root, headers=HEADERS, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return not (200 <= r.status < 300)
    except urllib.error.HTTPError as e:
        return e.code in (403, 429)
    except Exception:
        return True


def main():
    rows = sources()
    reachable = []
    blocked = []
    failed = []
    for name, url in rows:
        status, title, note = check(url)
        if status is not None and 200 <= status < 300 and title:
            reachable.append((name, status, title))
            print(f"OK    {status}  {name}  — {title}")
        elif status is not None and 200 <= status < 300:
            # 200 but no <title>: probably a JS shell or a soft error page.
            failed.append((name, status, "no <title> in body"))
            print(f"WARN  {status}  {name}  (200 but no <title> — check by hand)  {url}")
        elif status in (403, 429):
            if host_blocked(url):
                blocked.append((name, status))
                print(f"BLOCK {status}  {name}  (host blocks this IP/request; verify in a browser)  {url}")
            else:
                # Same host serves the root, so this specific path is rejected:
                # dead or renamed page, not a bot wall.
                failed.append((name, status, "403 on this path, host root OK"))
                print(f"FAIL  {status}  {name}  (host reachable but this path is rejected)  {url}")
        else:
            failed.append((name, status, note))
            print(f"FAIL  {status or note}  {name}  {url}")

    print()
    print(
        f"{len(reachable)}/{len(rows)} reachable (GET 2xx + <title>); "
        f"{len(blocked)} blocked by bot protection; {len(failed)} failed"
    )
    if blocked:
        print("Blocked: " + ", ".join(f"{n} ({s})" for n, s in blocked))
    if failed:
        print("Failed: " + ", ".join(f"{n} ({s or note})" for n, s, note in failed))
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
