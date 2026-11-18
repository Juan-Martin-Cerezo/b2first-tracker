#!/usr/bin/env python3
"""CSP hash generator for the single-file UI.

Extracts from an HTML document:

  * the body of every inline ``<script>`` (a tag with ``src`` is skipped), and
  * the value of every inline ``on*`` event-handler attribute,

and prints the resulting ``sha256-`` hashes grouped by CSP directive, ready to
paste into a ``Content-Security-Policy`` header.

Inline event handlers can only be allowed by hash with ``'unsafe-hashes'`` in
``script-src`` (CSP Level 3), which is why the generated directive carries it.
The long-term fix is to replace the handlers with delegated listeners and drop
``'unsafe-hashes'``; see the note next to the CSP in ``server.py``.

Usage:
    python3 tools/csp_hashes.py index.html
    python3 tools/csp_hashes.py --file landing.html
"""
import argparse
import base64
import hashlib
import os
import re
import sys
from html.parser import HTMLParser

_HANDLER_IN_SCRIPT = re.compile(r"\bon[a-z]+\s*=\s*\"([^\"]*)\"", re.IGNORECASE)

DEFAULT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")


def _hash(text):
    """Return the CSP ``sha256-<base64>`` hash of ``text``."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


class _Collector(HTMLParser):
    """Collect inline script bodies and inline event-handler values."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_script = False
        self._buffer = []
        self.scripts = []
        self.handlers = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name.startswith("on") and value is not None:
                self.handlers.append(value)
        if tag == "script":
            has_src = any(name == "src" for name, _value in attrs)
            self._in_script = not has_src
            self._buffer = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script:
            self.scripts.append("".join(self._buffer))
            self._in_script = False
            self._buffer = []

    def handle_data(self, data):
        if self._in_script:
            self._buffer.append(data)


def extract(html):
    """Return ``{"scripts": [...], "handlers": [...]}`` for ``html``.

    Handlers are collected twice: as real attributes (the static markup) and as
    ``on*="…"`` fragments inside inline script bodies, where the UI builds rows
    with ``innerHTML``. Those fragments use static code plus ``data-*`` values,
    so the same hash covers every row the script renders later.
    """
    collector = _Collector()
    collector.feed(html)
    collector.close()
    handlers = list(collector.handlers)
    for body in collector.scripts:
        handlers.extend(_HANDLER_IN_SCRIPT.findall(body))
    return {"scripts": collector.scripts, "handlers": handlers}


def script_hashes(html):
    """Sorted, de-duplicated hashes of every inline script body."""
    return sorted({_hash(body) for body in extract(html)["scripts"]})


def handler_hashes(html):
    """Sorted, de-duplicated hashes of every inline event-handler value."""
    return sorted({_hash(value) for value in extract(html)["handlers"]})


def script_src(html):
    """The complete ``script-src`` directive value for ``html``."""
    hashes = sorted(set(script_hashes(html)) | set(handler_hashes(html)))
    parts = ["'self'"]
    parts.extend("'%s'" % value for value in hashes)
    parts.extend(("'unsafe-hashes'", "'strict-dynamic'"))
    return " ".join(parts)


def directives(html):
    """Header-ready directives produced from ``html``."""
    return ["script-src " + script_src(html)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", default=DEFAULT_FILE,
                        help="HTML document (default: index.html)")
    parser.add_argument("--file", dest="file_opt", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    path = args.file_opt or args.file
    with open(path, encoding="utf-8") as handle:
        html = handle.read()
    for directive in directives(html):
        print(directive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
