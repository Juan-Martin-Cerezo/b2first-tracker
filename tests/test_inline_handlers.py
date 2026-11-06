"""Phase 114 guard: no inline handler may point at a missing global.

`index.html` wires many controls with inline attributes (`onclick=...`,
`onchange=...`) and a few dynamically generated ones (the onboarding wizard).
If one of those names is renamed, removed or left block-scoped, the browser
only finds out when a real user clicks: `ReferenceError: X is not defined`.

This suite collects every handler — from the live DOM after the app has
rendered, and from the source (so markup that is generated later is covered
too) — then asks the page for `typeof window[name]` for each function the
handler calls. Anything that is not a function fails with its selector and
its line in index.html.

Handlers assigned as DOM0 properties (`el.onclick = fn`) are checked too: the
named target must be a global function.

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
# built-ins, and the names an inline handler gets from its own scope chain
# (element, form, document, window).
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


def source_handlers():
    """Every `on<event>="..."` in the file, with its 1-based line."""
    src = open(INDEX, encoding="utf-8").read()
    found = []
    for m in re.finditer(r'\bon([a-z]+)\s*=\s*"([^"]*)"', src):
        found.append({
            "attr": "on" + m.group(1),
            "code": m.group(2),
            "line": src.count("\n", 0, m.start()) + 1,
        })
    for m in re.finditer(r"\bon([a-z]+)\s*=\s*'([^']*)'", src):
        found.append({
            "attr": "on" + m.group(1),
            "code": m.group(2),
            "line": src.count("\n", 0, m.start()) + 1,
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
    for (const el of document.querySelectorAll('*')) {
        for (const a of el.attributes) {
            if (!/^on[a-z]+$/.test(a.name)) continue;
            let sel = el.tagName.toLowerCase();
            if (el.id) sel += '#' + el.id;
            else {
                const cls = (typeof el.className === 'string' ? el.className : '')
                    .trim().split(/\\s+/).filter(Boolean).slice(0, 2);
                if (cls.length) sel += '.' + cls.join('.');
            }
            out.push({selector: sel, attr: a.name, code: a.value});
        }
    }
    return out;
}"""


def main():
    source = source_handlers()
    dom0 = source_dom0_targets()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(URL + "app", wait_until="networkidle")
        login_owner(pg, URL)
        pg.wait_for_timeout(300)

        # Render the markup that only exists after a render pass: onboarding
        # wizard, exam player, today/plan/practice screens, quick log.
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
        for h in dom:
            for name in called_globals(h["code"]):
                occurrences.setdefault(name, []).append(
                    {"selector": h["selector"], "attr": h["attr"],
                     "line": source_line(h, source), "code": h["code"].strip()[:60]}
                )
        for h in source:
            for name in called_globals(h["code"]):
                occurrences.setdefault(name, []).append(
                    {"selector": "(source)", "attr": h["attr"],
                     "line": h["line"], "code": h["code"].strip()[:60]}
                )
        for d in dom0:
            occurrences.setdefault(d["name"], []).append(
                {"selector": "(dom0 assignment)", "attr": "on*",
                 "line": d["line"], "code": d["name"]}
            )

        names = sorted(occurrences)
        kinds = pg.evaluate(
            "(names) => Object.fromEntries(names.map(n => [n, typeof window[n]]))",
            names,
        )
        browser.close()

    orphans = sorted(n for n, kind in kinds.items() if kind != "function")
    if orphans:
        print("Orphan inline handlers (referenced but not a global function):")
        for name in orphans:
            for where in occurrences[name][:4]:
                print(
                    f"  {name}  [{where['attr']}]  {where['selector']}"
                    f"  line {where['line']}: {where['code']}"
                )
        raise SystemExit(1)

    print(json.dumps({
        "handlers_dom": len(dom),
        "handlers_source": len(source),
        "dom0_assignments": len(dom0),
        "globals_checked": len(names),
        "orphans": 0,
    }, indent=1))


def source_line(dom_handler, source):
    """Line in index.html that holds this rendered handler, if it is literal."""
    code = dom_handler["code"]
    for h in source:
        if h["code"] == code and h["attr"] == dom_handler["attr"]:
            return h["line"]
    return None


if __name__ == "__main__":
    main()
