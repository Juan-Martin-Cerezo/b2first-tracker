"""Phase 82: Practice keeps only the exercises; Resources is its own tab.

Practice used to hold the source grid, the resource cards and the books. They
now live in the Resources view, in one place each, and every link that used to
land on Practice for sources lands on Resources instead.
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

    # 1. Practice is only the exercises by part.
    pg.evaluate("showView('practice')")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.querySelector('.view.active').id") == "v-practice", "Practice is not active"
    assert pg.evaluate("!!document.querySelector('#v-practice #partsList')"), "#partsList is not in Practice"
    assert pg.eval_on_selector_all("#v-practice #partsList .step", "els => els.length") > 0, (
        "Practice has no exercise rows"
    )
    for moved in ("practiceGrid", "practiceResources", "practiceBooks"):
        assert not pg.evaluate(f"!!document.querySelector('#v-practice #{moved}')"), (
            f"#{moved} still lives inside Practice"
        )
    for moved in ("practiceFilter", "practiceFreeOnly"):
        assert not pg.evaluate(f"!!document.querySelector('#v-practice #{moved}')"), (
            f"#{moved} still lives inside Practice"
        )
    out["practice"] = {"steps": pg.eval_on_selector_all("#v-practice #partsList .step", "els => els.length")}

    # 2. Resources holds the three blocks plus the source grid, with the same ids.
    pg.evaluate("showView('resources')")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.querySelector('.view.active').id") == "v-resources", "Resources is not active"
    for node in (
        "practiceGrid", "practiceResources", "practiceBooks", "onlineList",
        "matList", "matFilter", "practiceFilter", "practiceFreeOnly",
    ):
        assert pg.evaluate(f"!!document.querySelector('#v-resources #{node}')"), (
            f"#{node} is not inside Resources"
        )

    # 3. Online practice, sample cards, downloads: in that order.
    tops = pg.evaluate(
        """() => ['onlineList', 'resourcesList', 'matList']
              .map(id => document.getElementById(id).getBoundingClientRect().top)"""
    )
    assert tops[0] < tops[1] < tops[2], f"Resources blocks out of order: {tops}"
    out["resources_order"] = tops
    pg.locator("#v-resources").screenshot(path=os.path.join(OUT, "resources_view.png"))

    # 4. The new nav entry exists in both languages and opens the view.
    assert pg.evaluate("!!document.querySelector(\"nav button[data-view='resources']\")"), (
        "Resources is not in the main navigation"
    )
    label_en = pg.eval_on_selector(
        "nav button[data-view='resources'] .nav-label", "el => el.textContent.trim()"
    )
    assert label_en == "Resources", f"Resources nav label is {label_en!r}"
    pg.evaluate("showView('hoy')")
    pg.evaluate("showView('resources')")
    pg.wait_for_timeout(200)
    assert pg.evaluate("document.querySelector('.view.active').id") == "v-resources", (
        "showView('resources') does not open Resources"
    )
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    label_es = pg.eval_on_selector(
        "nav button[data-view='resources'] .nav-label", "el => el.textContent.trim()"
    )
    assert label_es == "Recursos", f"Resources nav label is {label_es!r} in Spanish"
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(300)
    out["nav"] = {"en": label_en, "es": label_es}

    # 5. goToPartFilter ends in Resources, filtered to the paper.
    pg.evaluate("showView('hoy')")
    pg.evaluate("goToPartFilter(3, 'ue')")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.querySelector('.view.active').id") == "v-resources", (
        "goToPartFilter did not land on Resources"
    )
    assert pg.evaluate("!!RES_FILTER && RES_FILTER.type === 'ue' && RES_FILTER.part === 3"), (
        "goToPartFilter did not set the paper filter"
    )
    papers = pg.eval_on_selector_all(
        "#resourcesList .res-paper", "els => els.map(e => e.dataset.resType)"
    )
    assert papers == ["ue"], f"Resources did not filter to the row's paper: {papers}"
    out["go_to_part"] = {"papers": papers, "filter": pg.evaluate("RES_FILTER")}

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
