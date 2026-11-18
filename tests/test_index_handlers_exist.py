"""Phase 115: the document actually served at /app is complete and wired.

Complements test_inline_handlers.py: that one reads index.html from disk, this
one reads the bytes the server hands a browser. It first refuses a partial
document (no `</html>`, unbalanced scripts), then checks that the document has
no inline `on*` handler attribute left and that every `data-action` it serves
resolves to an entry of the delegated ACTIONS table in the page.

Run with:  uv run --with playwright python test_index_handlers_exist.py
"""
import re
import urllib.request

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server()

HANDLER = re.compile(r'\bon[a-z]+\s*=\s*"')
ACTION = re.compile(r'\bdata-(?:action|change|input|keydown)="([^"]*)"')


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


def main():
    html = served_html()
    assert_complete(html)

    inline = HANDLER.findall(html)
    assert not inline, (
        "served /app still carries inline on* handler attributes: "
        + ", ".join(sorted(set(inline)))
    )

    served_actions = sorted(set(ACTION.findall(html)))
    assert served_actions, "served /app has no data-* action attributes"

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

        unresolved = pg.evaluate(
            """(names) => names.filter(n =>
                   !ACTIONS.click[n] && !ACTIONS.change[n] &&
                   !ACTIONS.input[n] && !ACTIONS.keydown[n])""",
            served_actions,
        )
        browser.close()

    assert not unresolved, (
        "data-* attributes with no delegated action: " + ", ".join(unresolved)
    )

    print(f"served document OK: 0 inline handlers, {len(served_actions)} actions wired")


if __name__ == "__main__":
    main()
