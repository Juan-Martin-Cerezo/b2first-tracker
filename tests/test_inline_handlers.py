"""Phase 114 guard: no inline handler may point at a missing global.

`index.html` wires its controls through `data-action` / `data-change` /
`data-input` / `data-keydown` attributes that one delegated listener resolves,
plus a few handlers assigned as DOM0 properties. If a name in the ACTIONS table
(or a DOM0 assignment) is renamed, removed or left block-scoped, the browser
only finds out when a real user clicks: `ReferenceError: X is not defined`.

This suite collects every action name — from the live DOM after the app has
rendered, and from the source (so markup that is generated later is covered
too) — then asks the page for `typeof window[name]` for each global the entry
calls. Anything that is not a function fails with its selector and its line.

Run with:  uv run --with playwright python test_inline_handlers.py
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO_ROOT, "index.html")
URL = isolated_server() + "/"

# Names that are not globals you must declare: language keywords, browser
# built-ins, and the names a handler gets from the element it is bound to.
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

ACTION_TABLE = re.compile(
    r"^(?:click|change|input|keydown):\{(.*?)^\}", re.S | re.M)
ACTION_ENTRY = re.compile(r"^'([^']+)':\s*(.+?),?$", re.M)


def called_globals(code):
    """Function names a handler calls that must exist on `window`."""
    stripped = STRING.sub(" ", code)
    out = set()
    for m in IDENT.finditer(stripped):
        name = m.group(1)
        if name in KEYWORDS or name in BUILTINS or name in SCOPE:
            continue
        out.add(name)
    return out


def source_table():
    """Every ACTIONS entry in the file: its name and body, with a 1-based line."""
    src = open(INDEX, encoding="utf-8").read()
    found = []
    for group in ACTION_TABLE.finditer(src):
        for m in ACTION_ENTRY.finditer(group.group(1)):
            found.append({
                "name": m.group(1),
                "code": m.group(2),
                "line": src.count("\n", 0, group.start(1)) + 1,
            })
    return found


def source_dom0_targets():
    """Named functions assigned through a DOM0 property, e.g. `b.onclick=f`."""
    src = open(INDEX, encoding="utf-8").read()
    found = []
    pattern = re.compile(
        r"\.on(?:click|change|input|submit|blur|focus|keydown|keyup|error|load|"
        r"ended|start|end|message|open|close)\s*=\s*([A-Za-z_$][\w$]*)\s*;"
    )
    for m in pattern.finditer(src):
        found.append({
            "name": m.group(1),
            "line": src.count("\n", 0, m.start()) + 1,
        })
    return found


DOM_JS = """() => {
    const out = [];
    for (const el of document.querySelectorAll(
            '[data-action],[data-change],[data-input],[data-keydown]')) {
        let sel = el.tagName.toLowerCase();
        if (el.id) sel += '#' + el.id;
        out.push({selector: sel, name: el.dataset.action || el.dataset.change
            || el.dataset.input || el.dataset.keydown});
    }
    return out;
}"""


def main():
    table = source_table()
    dom0 = source_dom0_targets()

    # Source-map of action name -> body, to know what each DOM action calls.
    bodies = {t["name"]: t["code"] for t in table}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(URL + "app", wait_until="networkidle")
        login_owner(pg, URL)
        pg.wait_for_timeout(300)

        pg.evaluate("""() => {
            for (const view of ['hoy','plan','prog','practice','exam','err','ia','diag']) {
                try { showView(view); } catch (e) {}
            }
            try { showOnboarding(); } catch (e) {}
            try { hideOnboarding(); } catch (e) {}
            try { showView('hoy'); } catch (e) {}
        }""")
        pg.wait_for_timeout(250)
        dom = pg.evaluate(DOM_JS)

        occurrences = {}  # name -> first place it appears

        def note(name, where):
            occurrences.setdefault(name, []).append(where)

        for entry in table:
            for name in called_globals(entry["code"]):
                note(name, {"selector": "(ACTIONS)", "name": entry["name"],
                            "line": entry["line"],
                            "code": entry["code"].strip()[:60]})
        for h in dom:
            body = bodies.get(h["name"], "")
            for name in called_globals(body):
                note(name, {"selector": h["selector"], "name": h["name"],
                            "line": None, "code": body.strip()[:60]})
        for d in dom0:
            note(d["name"], {"selector": "(dom0 assignment)", "name": "on*",
                             "line": d["line"], "code": d["name"]})

        names = sorted(occurrences)
        kinds = pg.evaluate(
            "(names) => Object.fromEntries(names.map(n => [n, typeof window[n]]))",
            names,
        )
        browser.close()

    orphans = sorted(n for n, kind in kinds.items() if kind != "function")
    if orphans:
        print("Orphan handler names (referenced but not a global function):")
        for name in orphans:
            for where in occurrences[name][:4]:
                print(
                    f"  {name}  [{where['name']}]  {where['selector']}"
                    f"  line {where['line']}: {where['code']}"
                )
        raise SystemExit(1)

    print(json.dumps({
        "actions_in_table": len(table),
        "actions_in_dom": len(dom),
        "dom0_assignments": len(dom0),
        "globals_checked": len(names),
        "orphans": 0,
    }, indent=1))


if __name__ == "__main__":
    main()
