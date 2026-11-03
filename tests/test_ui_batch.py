"""Phase 48 acceptance: the six surgical UI fixes.

Runs against the isolated server and the shared throwaway account. The
listening cards are checked with a seeded MAT index so the test does not
depend on the PDFs being present on the machine.
"""
import os

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

ALLOWED_RESOURCE_NAMES = {
    "Questions",
    "Audio",
    "Tapescript",
    "Answer key",
    "Lesson plan",
    "Lesson plan audio",
    "Teacher guide",
    "Tapescript and key",
    "Online practice",
}

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

    # 1. The FAB opens the same modal as "Log single part".
    pg.evaluate("showView('hoy')")
    pg.wait_for_timeout(200)
    modal_title = pg.eval_on_selector(
        "#soloModal [data-i18n='solo_title']", "el => el.textContent.trim()"
    )
    fab_title = pg.get_attribute("#qlFab", "title")
    pg.click("#qlFab")
    pg.wait_for_selector("#soloModal", state="visible")
    assert pg.is_visible("#soloModal"), "FAB did not open #soloModal"
    assert fab_title.lower() == modal_title.lower(), (
        f"FAB title {fab_title!r} does not match modal title {modal_title!r}"
    )
    pg.evaluate("closeSoloModal()")
    out["1_fab_opens_solo"] = {"title": fab_title, "modal": modal_title}

    # 2. No rotation matrix anywhere.
    body = pg.evaluate("document.body.innerText")
    for banned in ("Fortnightly", "AUTOMATED CYCLE", "WEEK A"):
        assert banned not in body, f"rotation text still rendered: {banned!r}"
    assert not pg.evaluate("!!document.getElementById('rotCardWkA')"), "rotCardWkA still in the DOM"
    out["2_rotation_gone"] = True

    # 3. Parts live inside Practice, in paper order.
    assert not pg.evaluate("!!document.getElementById('v-partes')"), "#v-partes still exists"
    assert not pg.evaluate("!!document.querySelector(\"nav button[data-view='partes']\")"), (
        "Parts nav entry still exists"
    )
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(300)
    assert pg.evaluate("!!document.querySelector('#v-practice #partsList')"), (
        "#partsList is not inside #v-practice"
    )
    folders = pg.eval_on_selector_all(
        "#partsList .folder", "els => els.map(e => e.textContent.trim())"
    )
    order = ["Reading & Use of English", "Listening", "Speaking", "Writing"]
    positions = [folders.index(name) for name in order]
    assert positions == sorted(positions), f"paper order wrong: {folders}"
    out["3_parts_in_practice"] = folders

    # 4. One listening card per test, resources grouped and labelled by name.
    pg.evaluate(
        """() => {
        const keys = ['lS1','lS2','lFS1','lFS2','auS1',
          'auS2p1','auS2p2','auS2p3','auS2p4',
          'auFS1p1','auFS1p2','auFS1p3','auFS1p4','auFS2',
          'tsS1','tsFS1','lkS1','lkFS1',
          'lpL1','lpL2','lpL3','lpL4','fL1','fL2','fL3','fL4',
          'fL1a','fL2a','fL3a','fL4a',
          'hbA1','hbA2p1','hbA2p2','hbA2p3','hbA2p4',
          'hbFSp1','hbFSp2','hbFSp3','hbFSp4','hbFS2','hb','hbFS','lGuide'];
        MAT = {};
        keys.forEach(k => { MAT[k] = '/files/test-' + k + '.pdf'; });
        renderParts(); renderResources();
    }"""
    )
    pg.wait_for_timeout(200)
    cards = pg.eval_on_selector_all(
        "#resourcesList .res-paper[data-res-type='lp'] .listen-test",
        """els => els.map(e => ({
            title: e.querySelector('.lt-head').textContent.trim(),
            links: [...e.querySelectorAll('a')].map(a => a.textContent.trim())
        }))""",
    )
    assert cards, "no listening test cards rendered"
    by_title = {c["title"]: c["links"] for c in cards}
    first = by_title.get("Listening test 1", [])
    for needed in ("Questions", "Audio", "Tapescript", "Answer key"):
        assert needed in first, f"Listening test 1 is missing {needed!r}: {first}"
    for card in cards:
        if "Questions" in card["links"]:
            assert "Audio" in card["links"], f"audio separated from questions: {card['title']}"
    labels = {label for card in cards for label in card["links"]}
    assert labels <= ALLOWED_RESOURCE_NAMES, f"opaque chip label leaked: {labels - ALLOWED_RESOURCE_NAMES}"
    for opaque in ("auS2p3", "hbA2p1", "tsS1", "lkS1", "FS1"):
        assert opaque not in {label for card in cards for label in card["links"]}, (
            f"internal code shown as a chip: {opaque}"
        )
    pg.locator("#practiceResources").screenshot(path=os.path.join(OUT, "practice_listening.png"))
    out["4_listening_cards"] = [c["title"] for c in cards]

    # 5. One Progress screen with the four charts inside it.
    assert not pg.evaluate("!!document.querySelector(\"nav button[data-view='graf']\")"), (
        "Charts nav entry still exists"
    )
    assert not pg.evaluate("!!document.getElementById('v-graf')"), "#v-graf still exists"
    pg.click("nav button[data-view='prog']")
    pg.wait_for_timeout(300)
    for chart_id in ("gEvol", "gPart", "gErr", "gCons"):
        assert pg.evaluate(f"!!document.querySelector('#v-prog #{chart_id}')"), (
            f"{chart_id} is not inside #v-prog"
        )
    out["5_one_progress"] = True

    # 6. The matrix is read-only; thresholds stay editable in PLAN.
    pg.wait_for_timeout(400)
    assert pg.eval_on_selector_all("#gates input[type=number]", "els => els.length") == 0, (
        "the matrix still has number inputs"
    )
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(300)
    pg.fill("#pE0w", "17")
    pg.click("button[onclick='savePlan()']")
    pg.wait_for_timeout(1600)
    assert pg.evaluate("D.settings.e0.w") == 17, "PLAN did not write D.settings.e0.w"
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(900)
    assert pg.evaluate("D.settings.e0.w") == 17, "PLAN threshold did not persist across reload"
    pg.click("nav button[data-view='prog']")
    pg.wait_for_timeout(300)
    pg.locator("#gates").screenshot(path=os.path.join(OUT, "progress_matrix.png"))
    out["6_matrix_read_only"] = pg.evaluate("D.settings.e0.w")

    # 7. Errors legend: every code explained, every log pill titled.
    pg.evaluate(
        """() => {
        D.errs = [
          {date: today(), code: 'L-GAP', desc: 'vocabulary', fix: 'review'},
          {date: today(), code: 'G-ERR', desc: 'grammar', fix: 'review'},
          {date: today(), code: 'T-MIS', desc: 'distractor', fix: 'review'},
          {date: today(), code: 'T-LIM', desc: 'time', fix: 'review'}
        ];
        save(); refreshAll();
    }"""
    )
    pg.evaluate("showView('err')")
    pg.wait_for_timeout(400)
    legend = pg.evaluate("document.getElementById('errLegend').innerText")
    rows = pg.eval_on_selector_all(
        "#errLegend tbody tr",
        "els => els.map(tr => [...tr.children].map(td => td.innerText.trim()))",
    )
    assert len(rows) == 4, f"legend does not list four codes: {rows}"
    for row in rows:
        assert row[0], f"legend row has no code: {row}"
        assert row[2], f"legend row has no explanation: {row}"
        assert row[3], f"legend row has no example: {row}"
    titles = pg.eval_on_selector_all(
        "#errList .pill", "els => els.map(e => e.getAttribute('title') || '')"
    )
    for code in ("L-GAP", "G-ERR", "T-MIS", "T-LIM"):
        assert code in legend, f"{code} missing from the legend"
        assert any(code in title for title in titles), f"{code} missing from a log pill title"
    pg.locator("#errLegend").screenshot(path=os.path.join(OUT, "errors_legend.png"))
    out["7_errors_legend"] = [row[0] for row in rows]

    # 8. No page errors for the whole run.
    assert page_errors == [], f"page errors: {page_errors}"
    out["8_errors"] = page_errors
    browser.close()

print(__import__("json").dumps(out, ensure_ascii=False, indent=1))
