"""Phase 115: the document actually served at /app is complete and wired.

Complements test_inline_handlers.py: that one reads index.html from disk, this
one reads the bytes the server hands a browser. It first refuses a partial
document (no `</html>`, unbalanced scripts), then checks that every inline
handler in the served markup calls a function that exists on `window`.

Run with:  uv run --with playwright python test_index_handlers_exist.py
"""
import re
import urllib.request

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server()

KEYWORDS = set(
    "if for while function return typeof new delete void in of instanceof else "
    "do switch case var let const try catch finally throw yield await async "
    "true false null undefined this".split()
)
BUILTINS = set(
    "alert confirm prompt parseInt parseFloat isNaN String Number Boolean Array "
    "Object JSON Math Date RegExp Error encodeURIComponent decodeURIComponent "
    "setTimeout clearTimeout setInterval clearInterval console localStorage "
    "sessionStorage fetch Promise Set Map".split()
)
SCOPE = set("event this document window arguments navigator location history".split())

IDENT = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")
STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")
HANDLER = re.compile(r'\bon([a-z]+)\s*=\s*"([^"]*)"')

DOM_JS = """() => {
    const out = [];
    for (const el of document.querySelectorAll('*')) {
        for (const a of el.attributes) {
            if (!/^on[a-z]+$/.test(a.name)) continue;
            out.push({attr: a.name, code: a.value});
        }
    }
    return out;
}"""


def served_html():
    with urllib.request.urlopen(URL + "/app") as r:
        return r.read().decode("utf-8")


def assert_complete(html):
    """Fail before evaluating anything when the server handed us a partial doc."""
    assert "</html>" in html, "served /app is missing </html> (partial document)"
    opens = len(re.findall(r"<script\b", html, re.I))
    closes = len(re.findall(r"</script\s*>", html, re.I))
    assert opens == closes, f"served /app has {opens} <script> vs {closes} </script>"
    assert "onLPartChange" in html, "served /app lost the onLPartChange handler"


def called_globals(code):
    stripped = STRING.sub(" ", code)
    return {
        m.group(1) for m in IDENT.finditer(stripped)
        if m.group(1) not in KEYWORDS
        and m.group(1) not in BUILTINS
        and m.group(1) not in SCOPE
    }


def main():
    html = served_html()
    assert_complete(html)

    source_handlers = [
        {"attr": "on" + m.group(1), "code": m.group(2)}
        for m in HANDLER.finditer(html)
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(URL + "/app", wait_until="networkidle")
        login_owner(pg, URL + "/")
        pg.wait_for_timeout(300)
        pg.evaluate("""() => {
            for (const view of ['hoy','plan','prog','practice','exam','err','ia','diag']) {
                try { showView(view); } catch (e) {}
            }
            try { showView('hoy'); } catch (e) {}
        }""")
        pg.wait_for_timeout(250)

        dom_handlers = pg.evaluate(DOM_JS)
        handlers = source_handlers + dom_handlers
        names = sorted({n for h in handlers for n in called_globals(h["code"])})
        kinds = pg.evaluate(
            "(names) => Object.fromEntries(names.map(n => [n, typeof window[n]]))",
            names,
        )
        browser.close()

    orphans = sorted(n for n, kind in kinds.items() if kind != "function")
    assert not orphans, "inline handlers reference missing globals: " + ", ".join(orphans)

    print(f"served handlers OK: {len(handlers)} handlers, {len(names)} globals")


if __name__ == "__main__":
    main()
