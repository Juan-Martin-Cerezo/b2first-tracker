"""Unified Practice view: By part (default) + Library tab, no separate Resources view.

Practice is the single entry point. It holds two tabs:
  - "By part" (default): #partsList exercises by exam part.
  - "Library": every local material, online source and Reference item.
Legacy showView('resources') / showView('exercises') / showView('libros') and
goToPartFilter() all land on Practice -> Library.
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

    # 1. Practice defaults to the "By part" tab and has no legacy Resources DOM.
    pg.evaluate("showView('practice')")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.querySelector('.view.active').id") == "v-practice", "Practice is not active"
    assert pg.evaluate("!!document.querySelector('#v-practice #partsList')"), "#partsList is not in Practice"
    assert pg.evaluate("!document.getElementById('practiceTabParts').hidden"), "By part tab is not visible by default"
    assert pg.evaluate("document.getElementById('practiceTabLibrary').hidden"), "Library tab should start hidden"
    assert pg.eval_on_selector_all("#v-practice #partsList .step", "els => els.length") > 0, (
        "Practice has no exercise rows"
    )
    for removed in ("v-resources", "v-exercises", "v-libros", "practiceGrid", "practiceResources", "practiceBooks"):
        assert not pg.evaluate(f"!!document.getElementById('{removed}')"), (
            f"Legacy #{removed} still exists in DOM"
        )
    out["practice"] = {"steps": pg.eval_on_selector_all("#v-practice #partsList .step", "els => els.length")}

    # 2. Clicking the Library tab reveals the unified library controls and list.
    pg.click("#practiceTabLibraryBtn")
    pg.wait_for_timeout(300)
    assert pg.evaluate("!document.getElementById('practiceTabLibrary').hidden"), "Library tab did not open"
    assert pg.evaluate("document.getElementById('practiceTabParts').hidden"), "By part panel did not hide"
    for node in (
        "exercisesLibraryCard", "exLibSearch", "exLibPaperFilter", "exLibPartFilter",
        "exLibFreeOnly", "exLibSort", "exLibCount", "exLibList",
    ):
        assert pg.evaluate(f"!!document.querySelector('#v-practice #{node}')"), (
            f"#{node} is not inside Practice Library"
        )
    out["library_rows"] = pg.eval_on_selector_all("#exLibList a.exlib-row", "els => els.length")
    assert out["library_rows"] > 0, "Library rendered 0 rows"

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
    tabs_en = pg.eval_on_selector_all("#practiceTabs .practice-tab", "els => els.map(e => e.textContent.trim())")
    assert label_en == "Practice", f"Practice nav label is {label_en!r}"
    assert tabs_en == ["By part", "Library"], f"EN Practice tabs mismatch: {tabs_en}"

    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(350)
    label_es = pg.eval_on_selector(
        "nav button[data-view='practice'] .nav-label", "el => el.textContent.trim()"
    )
    tabs_es = pg.eval_on_selector_all("#practiceTabs .practice-tab", "els => els.map(e => e.textContent.trim())")
    assert label_es == "Práctica", f"Practice nav label is {label_es!r} in Spanish"
    assert tabs_es == ["Por parte", "Biblioteca"], f"ES Practice tabs mismatch: {tabs_es}"
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(250)
    out["nav"] = {"en": label_en, "es": label_es, "tabs_en": tabs_en, "tabs_es": tabs_es}

    # 4. Legacy showView('resources') / showView('exercises') / showView('libros') redirect to Practice -> Library.
    for legacy in ("resources", "exercises", "libros"):
        pg.evaluate("showView('hoy')")
        pg.evaluate(f"showView('{legacy}')")
        pg.wait_for_timeout(200)
        assert pg.evaluate("document.querySelector('.view.active').id") == "v-practice", (
            f"showView('{legacy}') did not redirect to #v-practice"
        )
        assert pg.evaluate("!document.getElementById('practiceTabLibrary').hidden"), (
            f"showView('{legacy}') did not open Library tab"
        )

    # 5. goToPartFilter lands in Practice -> Library filtered to the paper and part.
    pg.evaluate("showView('hoy')")
    pg.evaluate("goToPartFilter(3, 'ue')")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.querySelector('.view.active').id") == "v-practice", (
        "goToPartFilter did not land on Practice"
    )
    assert pg.evaluate("!document.getElementById('practiceTabLibrary').hidden"), (
        "goToPartFilter did not open Library tab"
    )
    assert pg.evaluate("EXLIB_STATE.paper === 'rue' && EXLIB_STATE.part === '3'"), (
        f"goToPartFilter did not filter library: {pg.evaluate('EXLIB_STATE')}"
    )
    skills = pg.eval_on_selector_all("#exLibList a.exlib-row", "els => [...new Set(els.map(e => e.dataset.skill))]")
    assert skills == ["rue"], f"Library did not filter to rue: {skills}"
    out["go_to_part"] = {"skills": skills, "state": pg.evaluate("EXLIB_STATE")}

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
