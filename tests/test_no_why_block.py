"""Phase 101: the "Why this?" disclosure is gone from the Week plan.

Neither the <details id="wpWhy"> nor its body exists, the phrase is not painted
anywhere, and the plan_why key is missing from both dictionaries.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(300)

    # 1. Neither node exists.
    dom = pg.evaluate(
        """() => ({
            box: !!document.getElementById('wpWhy'),
            body: !!document.getElementById('wpWhyBody'),
            summaries: [...document.querySelectorAll('#weeklyPlanCard summary')]
                .map(el => el.textContent.trim()),
            text: document.getElementById('v-plan').innerText,
        })"""
    )
    assert not dom["box"], "#wpWhy still exists"
    assert not dom["body"], "#wpWhyBody still exists"
    assert not any("why this" in s.lower() for s in dom["summaries"]), (
        f"a Why this? summary is still in the card: {dom['summaries']}"
    )
    assert "why this" not in dom["text"].lower(), (
        f"the Why this? copy is still painted: {dom['text']!r}"
    )
    OUT["1_dom_removed"] = {"summaries": dom["summaries"]}

    # 2. The key is gone from both dictionaries.
    keys = pg.evaluate(
        """() => ['plan_why','plan_why_queue']
            .filter(k => (k in I18N.en) || (k in I18N.es))"""
    )
    assert keys == [], f"removed i18n keys still in a dictionary: {keys}"
    OUT["2_keys_removed"] = keys

    # 3. The Week plan keeps its real content.
    card = pg.evaluate(
        """() => ({
            title: document.querySelector('#weeklyPlanCard h2').textContent.trim(),
            regen: !!document.getElementById('wpRegenBtn'),
            rotation: !!document.getElementById('wpRotationMode'),
            items: !!document.getElementById('wpItemsPerSession'),
            rows: !!document.getElementById('wpRows'),
        })"""
    )
    assert card == {
        "title": "Week plan", "regen": True, "rotation": True,
        "items": True, "rows": True,
    }, f"the Week plan lost content: {card}"
    OUT["3_card_content"] = card

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
