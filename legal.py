#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tiny Markdown renderer for the legal pages (stdlib only, no template engine).

Supported: ATX headings, paragraphs, unordered/ordered lists, fenced code,
tables, blockquotes, inline code, bold, italic and [links](url).

Security: every piece of source text is HTML-escaped *before* any generated tag
is inserted, so a `<` in a document can never become markup. Link targets are
restricted to http(s), mailto and site-relative paths.
"""
import html
import os
import re

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+\.\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _safe_url(raw):
    """Return an escaped URL for href, or '#' for anything not http(s)/mailto/relative."""
    url = html.unescape(raw).strip()
    low = url.lower()
    if low.startswith(("http://", "https://", "mailto:", "/")):
        return html.escape(url, quote=True)
    return "#"


def _inline(text):
    """Escape text and apply inline formatting (never introduces raw source markup)."""
    out = html.escape(text, quote=False)
    out = _CODE.sub(lambda m: "<code>" + m.group(1) + "</code>", out)
    out = _BOLD.sub(lambda m: "<b>" + m.group(1) + "</b>", out)
    out = _ITALIC.sub(lambda m: "<i>" + m.group(1) + "</i>", out)
    out = _LINK.sub(
        lambda m: '<a href="' + _safe_url(m.group(2)) + '">' + m.group(1) + "</a>",
        out,
    )
    return out


def _split_row(line):
    """Cells of a table row, dropping the optional leading/trailing pipe."""
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [cell.strip() for cell in raw.split("|")]


def render_markdown(text):
    """Return the HTML body for one Markdown document."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            i += 1
            block = []
            while i < n and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1  # closing fence
            out.append("<pre><code>" + html.escape("\n".join(block), quote=False)
                       + "</code></pre>")
            continue

        if not stripped:
            i += 1
            continue

        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        # Table: header row followed by a separator row.
        if (stripped.startswith("|") and i + 1 < n
                and _TABLE_SEP.match(lines[i + 1]) and "-" in lines[i + 1]):
            head = _split_row(stripped)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            out.append("<table><thead><tr>"
                       + "".join(f"<th>{_inline(c)}</th>" for c in head)
                       + "</tr></thead><tbody>")
            for row in rows:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row)
                           + "</tr>")
            out.append("</tbody></table>")
            continue

        if _BULLET.match(line):
            items = []
            while i < n and _BULLET.match(lines[i]):
                items.append(_BULLET.match(lines[i]).group(1))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items)
                       + "</ul>")
            continue

        if _ORDERED.match(line):
            items = []
            while i < n and _ORDERED.match(lines[i]):
                items.append(_ORDERED.match(lines[i]).group(1))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(x)}</li>" for x in items)
                       + "</ol>")
            continue

        if stripped.startswith(">"):
            parts = []
            while i < n and lines[i].strip().startswith(">"):
                parts.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>" + _inline(" ".join(parts)) + "</blockquote>")
            continue

        # Paragraph: consecutive non-blank lines that are not another block.
        parts = []
        while i < n:
            cur = lines[i]
            s = cur.strip()
            if not s:
                break
            if (s.startswith("```") or _HEADING.match(s) or _BULLET.match(cur)
                    or _ORDERED.match(cur) or s.startswith("|")
                    or s.startswith(">")):
                break
            parts.append(s)
            i += 1
        out.append("<p>" + _inline(" ".join(parts)) + "</p>")

    return "\n".join(out)


_STYLE = """
:root, :root[data-theme="light"]{
  color-scheme:light;
  --bg: oklch(0.99 0.002 250); --surface: oklch(0.975 0.003 250);
  --line: oklch(0.90 0.006 250); --txt: oklch(0.22 0.01 250);
  --txt-2: oklch(0.46 0.01 250); --acc: oklch(0.52 0.16 255);
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --bg: oklch(0.19 0.006 255); --surface: oklch(0.23 0.008 255);
  --line: oklch(0.33 0.01 255); --txt: oklch(0.94 0.004 255);
  --txt-2: oklch(0.72 0.008 255); --acc: oklch(0.72 0.13 255);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){--bg: oklch(0.19 0.006 255); --surface: oklch(0.23 0.008 255);
    --line: oklch(0.33 0.01 255); --txt: oklch(0.94 0.004 255);
    --txt-2: oklch(0.72 0.008 255); --acc: oklch(0.72 0.13 255);}
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font:15px/1.65 system-ui,-apple-system,sans-serif;padding:24px 16px 56px}
.wrap{max-width:780px;margin:0 auto}
a{color:var(--acc)}
h1{font-size:24px;font-weight:800;letter-spacing:-.2px;margin:0 0 12px}
h2{font-size:17px;font-weight:700;margin:28px 0 8px}
h3{font-size:15px;font-weight:700;margin:20px 0 6px}
p,li{font-size:14px;color:var(--txt);margin:7px 0}
ul,ol{padding-left:22px}
code{font:13px/1.4 ui-monospace,monospace;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:1px 6px}
pre{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto;margin:10px 0}
pre code{border:0;padding:0;background:none}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:var(--surface);font-weight:700}
blockquote{border-left:3px solid var(--line);margin:12px 0;padding:2px 0 2px 14px;color:var(--txt-2)}
.legal-nav{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px}
.legal-nav a{text-decoration:none;font-size:13px;font-weight:600;border:1px solid var(--line);border-radius:10px;padding:7px 14px}
footer{margin-top:32px;padding-top:14px;border-top:1px solid var(--line);color:var(--txt-2);font-size:12px}
"""

_SHELL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — B2 First Tracker</title>
<meta name="theme-color" content="#fbfcfd">
<script>
(function(){{try{{
  if(localStorage.getItem('b2first_theme')==='dark')document.documentElement.setAttribute('data-theme','dark');
}}catch(e){{}}}})();
</script>
<style>{style}</style></head>
<body><div class="wrap">
<div class="legal-nav"><a href="/">← Back to the Tracker</a>
<a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/security">Security</a></div>
{body}
<footer>B2 First Tracker · self-hosted in Argentina · no advertising, no tracking ·
<a href="/.well-known/security.txt">security.txt</a></footer>
</div></body></html>"""


def read_doc(name):
    """Return the Markdown source of docs/<name>.md (empty string if missing)."""
    path = os.path.join(DOCS_DIR, name + ".md")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def legal_page(name, title):
    """Render docs/<name>.md inside the shared legal-page shell."""
    body = render_markdown(read_doc(name))
    return _SHELL.format(title=html.escape(title), style=_STYLE, body=body)
