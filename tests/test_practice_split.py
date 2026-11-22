"""Unified Practice view: By part only, single Start opens session with Contents.

Practice is the single entry point showing exercises by exam part (#partsList),
with no separate Resources view and no Practice Library tab. Each part has one
Start button that opens the session workspace (Session + Contents tabs).
Legacy showView('resources') / showView('exercises') / showView('libros')
redirect to Practice, and goToPartFilter() opens the unit's session on Contents.
"""
import json
import os

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 1000})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    # 1. Practice shows By part directly and has no legacy Resources or Library tab DOM.
    pg.evaluate("showView('practice')")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.querySelector('.view.active').id") == "v-practice", "Practice is not active"
    assert pg.evaluate("!!document.querySelector('#v-practice #partsList')"), "#partsList is not in Practice"
    assert pg.eval_on_selector_all("#v-practice #partsList .step", "els => els.length") > 0, (
        "Practice has no exercise rows"
    )
    for removed in (
        "v-resources", "v-exercises", "v-libros",
        "practiceGrid", "practiceResources", "practiceBooks",
        "practiceTabs", "practiceTabLibrary", "practiceTabLibraryBtn",
    ):
        assert not pg.evaluate(f"!!document.getElementById('{removed}')"), (
            f"Legacy #{removed} still exists in DOM"
        )
    out["practice"] = {"steps": pg.eval_on_selector_all("#v-practice #partsList .step", "els => els.length")}

    # 2. Clicking Start opens the session workspace on Contents, with Session and Contents tabs.
    pg.click("#partsList .step button[data-action='startPart'][data-i='1']")
    pg.wait_for_timeout(300)
    assert pg.evaluate("!document.getElementById('sessionWorkspace').hidden"), "Session workspace did not open"
    assert pg.evaluate("!document.getElementById('sessionTabContents').hidden"), "Contents tab should start open"
    assert pg.evaluate("document.getElementById('sessionTabSession').hidden"), "Session tab should start hidden"
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("!document.getElementById('sessionTabSession').hidden"), "Session tab did not open"
    pg.click("#sessionTabContentsBtn")
    pg.wait_for_timeout(250)
    assert pg.evaluate("!document.getElementById('sessionTabContents').hidden"), "Contents tab did not open"
    for node in (
        "exercisesLibraryCard", "exLibSearch", "exLibPaperFilter", "exLibPartFilter",
        "exLibFreeOnly", "exLibSort", "exLibCount", "exLibList",
    ):
        assert pg.evaluate(f"!!document.querySelector('#sessionTabContents #{node}')"), (
            f"#{node} is not inside Session Contents"
        )
    out["contents_rows"] = pg.eval_on_selector_all("#exLibList a.exlib-row", "els => els.length")
    assert out["contents_rows"] > 0, "Contents rendered 0 rows"

    # 3. Nav has Practice only (no Resources or Exercises entries), translated in EN/ES.
    assert not pg.evaluate("!!document.querySelector(\"nav button[data-view='resources']\")"), (
        "Resources is still in the main navigation"
    )
    assert not pg.evaluate("!!document.querySelector(\"nav button[data-view='exercises']\")"), (
        "Exercises is still in the main navigation"
    )
    label_en = pg.eval_on_selector(
        "nav button[data-view='practice'] .nav-label", "el => el.textContent.trim()"
    )
    tabs_en = pg.eval_on_selector_all("#sessionTabs .practice-tab", "els => els.map(e => e.textContent.trim())")
    assert label_en == "Practice", f"Practice nav label is {label_en!r}"
    assert tabs_en == ["Session", "Contents"], f"EN Session tabs mismatch: {tabs_en}"

    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(350)
    label_es = pg.eval_on_selector(
        "nav button[data-view='practice'] .nav-label", "el => el.textContent.trim()"
    )
    tabs_es = pg.eval_on_selector_all("#sessionTabs .practice-tab", "els => els.map(e => e.textContent.trim())")
    assert label_es == "Práctica", f"Practice nav label is {label_es!r} in Spanish"
    assert tabs_es == ["Sesión", "Contenidos"], f"ES Session tabs mismatch: {tabs_es}"
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(250)
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)
    out["nav"] = {"en": label_en, "es": label_es, "tabs_en": tabs_en, "tabs_es": tabs_es}

    # 4. Legacy showView('resources') / showView('exercises') / showView('libros') redirect to Practice.
    for legacy in ("resources", "exercises", "libros"):
        pg.evaluate("showView('hoy')")
        pg.evaluate(f"showView('{legacy}')")
        pg.wait_for_timeout(200)
        assert pg.evaluate("document.querySelector('.view.active').id") == "v-practice", (
            f"showView('{legacy}') did not redirect to #v-practice"
        )

    # 5. goToPartFilter opens the unit session on Contents filtered to the paper and part.
    pg.evaluate("showView('hoy')")
    pg.evaluate("goToPartFilter(3, 'ue')")
    pg.wait_for_timeout(300)
    assert pg.evaluate("!document.getElementById('sessionWorkspace').hidden"), (
        "goToPartFilter did not open session workspace"
    )
    assert pg.evaluate("!document.getElementById('sessionTabContents').hidden"), (
        "goToPartFilter did not open Contents tab"
    )
    assert pg.evaluate("EXLIB_STATE.paper === 'rue' && EXLIB_STATE.part === '3'"), (
        f"goToPartFilter did not filter contents: {pg.evaluate('EXLIB_STATE')}"
    )
    skills = pg.eval_on_selector_all("#exLibList a.exlib-row", "els => [...new Set(els.map(e => e.dataset.skill))]")
    assert skills == ["rue"], f"Contents did not filter to rue: {skills}"
    out["go_to_part"] = {"skills": skills, "state": pg.evaluate("EXLIB_STATE")}

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
