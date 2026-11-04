"""Phase 49 acceptance: seven surgical fixes.

Runs against the isolated server and the shared throwaway account. The
listening cards are checked with a seeded MAT index, and the rubric check is
exercised against a mocked corrector response.
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

LISTEN_KEYS = [
    "lS1", "lS2", "lFS1", "lFS2", "auS1",
    "auS2p1", "auS2p2", "auS2p3", "auS2p4",
    "auFS1p1", "auFS1p2", "auFS1p3", "auFS1p4", "auFS2",
    "tsS1", "tsFS1", "lkS1", "lkFS1", "lkS2", "lkFS2",
    "lpL1", "lpL2", "lpL3", "lpL4", "fL1", "fL2", "fL3", "fL4",
    "fL1a", "fL2a", "fL3a", "fL4a",
    "hbA1", "hbA2p1", "hbA2p2", "hbA2p3", "hbA2p4",
    "hbFSp1", "hbFSp2", "hbFSp3", "hbFSp4", "hbFS2", "hb", "hbFS", "lGuide",
]

DRAFT = """Technology has changed the way people talk to each other, and some observers argue that it has made us less social. Furthermore, many teenagers prefer a message to a conversation. Nevertheless, the evidence is not one-sided.

Firstly, smartphones allow families to stay in touch across long distances, which is a genuine benefit. Moreover, group chats can organise a meeting in minutes and keep everyone informed.

Consequently, it would be unfair to blame every device for loneliness. If governments were to invest in public spaces, people would meet face to face far more often.

As a result, the problem is not the technology itself but the habits it encourages. A balanced approach, which protects real conversation, is widely believed to be the answer. Not only should schools teach digital balance, but they should also create places where students can simply talk."""

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

    # 1. A session skips the landing; no session stays on it.
    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_timeout(300)
    assert pg.url.rstrip("/").endswith("/app"), f"logged-in / did not land on /app: {pg.url}"
    out["1_logged_in"] = pg.url
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    anon = ctx.new_page()
    anon.goto(URL, wait_until="networkidle")
    anon.wait_for_timeout(200)
    assert anon.url.rstrip("/") == URL.rstrip("/"), f"logged-out / redirected: {anon.url}"
    assert "Someone finally marks your writing" in anon.inner_text("h1#hero-title"), "landing headline missing"
    out["1_logged_out"] = anon.url
    ctx.close()

    # Seed the material index so every card renders without the PDFs on disk.
    pg.evaluate(
        """(keys) => {
        MAT = {};
        keys.forEach(k => { MAT[k] = '/files/test-' + k + '.pdf'; });
        renderParts(); renderResources(); renderGuides();
    }""",
        LISTEN_KEYS,
    )
    pg.evaluate("showView('practice')")
    pg.wait_for_timeout(300)

    # 2. No opaque listening code anywhere; cards grouped in Practice and exam mode.
    chip_labels = pg.eval_on_selector_all("#resourcesList .chip", "els => els.map(e => e.textContent.trim())")
    assert chip_labels, "no resource chips rendered"
    assert not [c for c in chip_labels if "🎧" in c], f"an emoji audio chip leaked: {chip_labels}"
    assert not [c for c in chip_labels if re.search(r"-P[1-4]\b", c)], f"a part code leaked: {chip_labels}"
    body_text = pg.evaluate("document.body.innerText")
    assert not re.search(r"-P[1-4]\b", body_text), "a part code is visible in the page text"

    practice_cards = pg.eval_on_selector_all(
        "#resourcesList .listen-test",
        """els => els.map(e => ({
            title: e.querySelector('.lt-head').textContent.trim(),
            links: [...e.querySelectorAll('a')].map(a => a.textContent.trim())
        }))""",
    )
    titles = [c["title"] for c in practice_cards]
    for wanted in ("Listening test 1", "Listening test 2 · part 1", "Full test 1", "Full test 2", "Handbook exercises"):
        assert wanted in titles, f"listening card missing in Practice: {wanted} ({titles})"
    for card in practice_cards:
        if "Audio" in card["links"]:
            assert any(k in card["links"] for k in ("Tapescript", "Answer key", "Tapescript and key")), (
                f"audio without a tapescript/key in the same card: {card}"
            )

    pg.evaluate("showView('exam'); document.getElementById('exPaper').value='l'; renderEx()")
    pg.wait_for_timeout(300)
    exam_cards = pg.eval_on_selector_all("#exGuide .listen-test .lt-head", "els => els.map(e => e.textContent.trim())")
    assert "Listening test 1" in exam_cards, f"exam mode is not grouped: {exam_cards}"
    orphan_chips = pg.evaluate(
        "() => [...document.querySelectorAll('#exGuide .chip')].filter(a => !a.closest('.listen-test')).length"
    )
    assert orphan_chips == 0, "exam mode still paints a flat chip wall"
    gl_cards = pg.eval_on_selector_all("#gLChips .listen-test", "els => els.length")
    assert gl_cards >= 1, "the listening studio did not render grouped cards"
    out["2_grouped"] = {"practice": titles, "exam": exam_cards, "studio": gl_cards}
    pg.locator("#exGuide").screenshot(path=os.path.join(OUT, "exam_listening.png"))

    # 3. The personalized study-plan sentence is gone in both languages.
    pg.evaluate("showView('hoy'); setLang('en')")
    pg.wait_for_timeout(300)
    assert "Personalized study plan for" not in pg.evaluate("document.body.innerText")
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    assert "Plan de estudio personalizado" not in pg.evaluate("document.body.innerText")
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(300)
    out["3_study_plan"] = "gone"

    # 4. Part rows have no chips; Resources filters the resources section.
    pg.evaluate("showView('practice'); clearResourcesFilter(); showView('practice')")
    pg.wait_for_timeout(300)
    assert pg.eval_on_selector_all("#partsList .step .chip", "els => els.length") == 0, (
        "part rows still carry resource chips"
    )
    pg.locator("#v-practice").screenshot(path=os.path.join(OUT, "practice_sections.png"))
    first_row = pg.locator("#partsList .step").first
    row_buttons = first_row.locator("button")
    labels = [row_buttons.nth(i).inner_text().strip() for i in range(row_buttons.count())]
    assert "Resources" in labels, f"the row has no Resources button: {labels}"
    first_row.locator("button", has_text="Resources").click()
    pg.wait_for_timeout(400)
    papers = pg.eval_on_selector_all("#resourcesList .res-paper", "els => els.map(e => e.dataset.resType)")
    assert papers == ["ue"], f"Resources did not filter to the row's paper: {papers}"
    pg.evaluate("clearResourcesFilter()")
    out["4_rows_resources"] = {"row_buttons": labels, "filtered": papers}

    # 5. The Phase 3 AI check reuses the corrector endpoint shape.
    seen = {}

    def ai_route(route):
        seen["method"] = route.request.method
        seen["url"] = route.request.url
        seen["body"] = route.request.post_data_json
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "bands": {"content": 4, "communicative_achievement": 4, "organisation": 4, "language": 4},
            "total": 16, "feedback": {}, "weaknesses": {}, "quotes": {}, "rewrite": [],
        }))

    pg.route("**/api/ai/writing", ai_route)
    assert pg.evaluate("!!document.querySelector('#wPhase3 #rubAiBtn')"), "Check with AI is not in wPhase3"
    pg.evaluate(
        "(txt) => { document.getElementById('wTextDraft').value = txt; onWritingDraftChange(); }",
        DRAFT,
    )
    dlog_before = pg.evaluate("D.log.length")
    pg.evaluate("showView('hoy'); switchWritingPhase('audit')")
    pg.evaluate("checkRubricWithAI()")
    pg.wait_for_timeout(500)
    assert seen.get("method") == "POST", f"rubric check did not POST: {seen}"
    assert seen.get("url", "").endswith("/api/ai/writing"), f"wrong endpoint: {seen}"
    body = seen.get("body") or {}
    assert body.get("text") == DRAFT.strip(), "the rubric check did not send the draft"
    for key in ("text", "task", "kind", "prompt"):
        assert key in body, f"request body is missing {key}: {body}"
    checked = pg.eval_on_selector_all("#rubList .rub", "els => els.map(e => e.checked)")
    reasons = pg.eval_on_selector_all("#rubList .rub-reason", "els => els.map(e => e.textContent.trim())")
    assert any(checked), "the rubric boxes were not pre-checked"
    assert all(reasons), f"a criterion has no reason: {reasons}"
    assert "16/20" in pg.inner_text("#rubAiStatus"), pg.inner_text("#rubAiStatus")
    assert pg.evaluate("D.log.length") == dlog_before, "the rubric check wrote to D.log"
    # Force the hidden session open so the screenshot shows the result.
    pg.evaluate("""() => {
        switchWritingPhase('audit');
        let el = document.getElementById('wPhase3');
        while (el && el !== document.body) { el.style.display = 'block'; el = el.parentElement; }
        showView('hoy');
    }""")
    pg.wait_for_timeout(300)
    pg.locator("#wPhase3").screenshot(path=os.path.join(OUT, "writing_phase3_ai.png"))
    out["5_ai_rubric"] = {"endpoint": seen.get("url"), "checked": checked, "status": pg.inner_text("#rubAiStatus")}
    pg.unroute("**/api/ai/writing")

    # 6. The matrix is read-only again; thresholds live in PLAN.
    pg.click("nav button[data-view='prog']")
    pg.wait_for_timeout(400)
    assert pg.eval_on_selector_all("#gates input[type=number]", "els => els.length") == 0, (
        "the matrix still has number inputs"
    )
    assert pg.eval_on_selector_all("#gates .ov-label input[type=checkbox]", "els => els.length") > 0, (
        "the manual override checkboxes disappeared"
    )
    assert "Complete all criteria within a stage to advance." in pg.evaluate(
        "document.querySelector('#gates').parentElement.innerText"
    )
    out["6_matrix_read_only"] = True

    # 7. The trimmed profile and top bar.
    assert not pg.evaluate("!!document.getElementById('stageBadge')"), "#stageBadge is still in the DOM"
    assert not pg.evaluate("!!document.querySelector('#userChip .stage-badge')"), "the chip still has a stage badge"
    page_text = pg.evaluate("document.body.innerText")
    for banned in ("Class Schedule", "Storage Status"):
        assert banned not in page_text, f"{banned} is still visible"

    # 8. Zero page errors for the whole run.
    assert page_errors == [], f"page errors: {page_errors}"
    out["7_trimmed"] = True
    out["8_errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
