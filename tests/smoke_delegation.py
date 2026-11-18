"""Smoke test: delegated actions fire and nothing throws."""
import json
import sys

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
ERRORS = []
CONSOLE = []

DISPATCH = """(sel) => {
  const el = document.querySelector(sel);
  if (!el) return 'MISSING';
  el.click();
  return 'ok';
}"""


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.expose_function("__err", lambda v: ERRORS.append(v))
        pg.add_init_script(
            "window.addEventListener('error',e=>window.__err(String(e.message)));")
        pg.on("console", lambda m: CONSOLE.append((m.type, m.text)))
        pg.goto(URL + "app", wait_until="networkidle")
        login_owner(pg, URL)
        pg.wait_for_timeout(400)

        results = {}

        def act(sel, label):
            results[label] = pg.evaluate(DISPATCH, sel)
            pg.wait_for_timeout(120)

        # Quick log: chips carry the argument in data-ql-type/kind/range.
        act("button[data-action='openQuickLog']", "openQuickLog")
        act("button[data-action='qlSetType'][data-ql-type='w']", "qlSetType(w)")
        act("button[data-action='qlSetKind'][data-ql-kind='Essay']", "qlSetKind")
        act("button[data-action='qlPickRange'][data-ql-range='6-10']", "qlPickRange")
        act("button[data-action='qlNext']", "qlNext")
        act("button[data-action='closeQuickLog']", "closeQuickLog")

        # Account sheet + settings + language.
        act("#userChip", "toggleAccountSheet")
        act("button[data-action='setThemeMode'][data-arg='dark']", "themeDark")
        act("button[data-action='setThemeMode'][data-arg='light']", "themeLight")
        act("button[data-action='setLang'][data-arg='es']", "setLangEs")
        act("button[data-action='setLang'][data-arg='en']", "setLangEn")
        act("button[data-action='accountSettings']", "accountSettings")
        act("button[data-action='closeSettingsModal']", "closeSettings")

        # Views, plan controls, practice filters.
        act("button[data-action='showView'][data-arg='plan']", "showView(plan)")
        act("button[data-action='advanceSession'][data-arg='1']", "advanceSession")
        act("button[data-action='setPracticeFilter'][data-skill='w']", "practiceFilter")
        act("button[data-action='showView'][data-arg='resources']", "showView(resources)")
        act("button[data-action='showView'][data-arg='exam']", "showView(exam)")
        act("button[data-action='showView'][data-arg='hoy']", "showView(hoy)")

        # Solo modal: two delegated actions on one element.
        act("button[data-action='openSoloModal']", "openSoloModal")
        results["solo_open"] = pg.evaluate(
            "document.getElementById('soloModal').style.display")
        act("#soloModal", "clickOverlayBackdrop")
        results["solo_closed"] = pg.evaluate(
            "document.getElementById('soloModal').style.display")

        # change + input delegation on a real select/textarea.
        pg.evaluate("showView('exam')")
        results["exPaper_change"] = pg.evaluate(
            """() => { const s=document.getElementById('exPaper');
                       s.value='w'; s.dispatchEvent(new Event('change',{bubbles:true}));
                       return document.getElementById('exGuide').innerText.length>=0; }""")

        results["final_view"] = pg.evaluate("currentActiveViewId()")
        results["jserrors"] = ERRORS
        results["console_errors"] = [t[:140] for k, t in CONSOLE if k == "error"][:10]
        b.close()

    print(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
