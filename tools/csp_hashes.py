#!/usr/bin/env python3
"""CSP hash generator for the single-file UI.

Extracts the body of every inline ``<script>`` (a tag with ``src`` is skipped)
from an HTML document and prints the resulting ``sha256-`` hashes as a ready
``script-src`` directive.

The UI no longer uses inline ``on*`` event-handler attributes: every control
carries a ``data-action``/``data-change``/``data-input``/``data-keydown``
attribute that a single delegated listener in ``index.html`` resolves. Without
handler attributes there is nothing for ``'unsafe-hashes'`` to allow, so the
directive only lists the ``<script>`` hashes.

Usage:
    python3 tools/csp_hashes.py index.html
    python3 tools/csp_hashes.py --file landing.html
"""
import argparse
import base64
import hashlib
import os
import sys
from html.parser import HTMLParser

DEFAULT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")


def _hash(text):
    """Return the CSP ``sha256-<base64>`` hash of ``text``."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


class _Collector(HTMLParser):
    """Collect the body of every inline ``<script>``."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_script = False
        self._buffer = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
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


def script_hashes(html):
    """Sorted, de-duplicated hashes of every inline script body."""
    collector = _Collector()
    collector.feed(html)
    collector.close()
    return sorted({_hash(body) for body in collector.scripts})


def script_src(html):
    """The complete ``script-src`` directive value for ``html``."""
    parts = ["'self'"]
    parts.extend("'%s'" % value for value in script_hashes(html))
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
