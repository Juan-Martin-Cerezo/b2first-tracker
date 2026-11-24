"""Mock start confirmation modal acceptance test.

Verifies:
  1. Clicking a mock paper card (R&UoE / Writing / Listening) does NOT start the
     countdown timer (`#exTimer` stays unchanged over 2s, `exIv === null`).
  2. `#mockStartModal` opens as an accessible dialog (`role="dialog"`, `aria-modal="true"`)
     with paper title, official duration, focus trap, Escape handling, and >=44px buttons.
  3. Cancel and Escape close the modal without starting the timer.
  4. "Open materials" opens Practice Library filtered to that `paper` and `scope='full'`
     without starting the timer.
  5. "Start timer" closes the modal and starts the countdown once (`#exTimer` ticks down).
  6. Full mock pre-flight ("Start 195' sequence") also passes through `#mockStartModal`
     with full mock copy (195 min written + 14 min Speaking); once confirmed, advancing
     to the next paper (`fullMockAdvance`) does NOT re-open the modal.
  7. 390x844 light/dark & EN/ES copy: zero horizontal overflow, zero inline handlers,
     zero page errors.

Saves screenshot: tests/out/mock_start_modal_390_light.png.
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
INLINE_HANDLER_RE = re.compile(r'\bon[a-z]+\s*=\s*"')

out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(300)

    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(250)

    # 1. Click R&UoE card -> opens #mockStartModal, timer does NOT start over 2 seconds
    pg.click("#examSelectGrid .exam-card[data-paper='rue']")
    pg.wait_for_timeout(150)
    t0 = pg.inner_text("#exTimer")
    pg.wait_for_timeout(2100)
    t1 = pg.inner_text("#exTimer")
    assert t0 == "01:15:00" and t1 == "01:15:00", f"Timer started automatically! {t0} -> {t1}"
    assert pg.evaluate("exIv === null"), "exIv should remain null while modal is open"

    modal_en = pg.evaluate(
        """() => {
            const ov = document.getElementById('mockStartModal');
            const btns = [...ov.querySelectorAll('button')].map(b => ({
                id: b.id,
                text: b.textContent.trim(),
                h: Math.round(b.getBoundingClientRect().height),
            }));
            return {
                open: getComputedStyle(ov).display !== 'none',
                role: ov.getAttribute('role'),
                ariaModal: ov.getAttribute('aria-modal'),
                title: document.getElementById('mockStartTitle').textContent.trim(),
                body: document.getElementById('mockStartBody').textContent.trim(),
                focusedId: document.activeElement ? document.activeElement.id : '',
                btns,
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                html: ov.outerHTML,
            };
        }"""
    )
    assert modal_en["open"] and modal_en["role"] == "dialog" and modal_en["ariaModal"] == "true", modal_en
    assert "Reading & Use of English" in modal_en["title"], modal_en
    assert "75" in modal_en["body"], modal_en
    assert modal_en["focusedId"] == "mockStartGoBtn", modal_en
    assert all(b["h"] >= 44 for b in modal_en["btns"]), f"Button < 44px: {modal_en['btns']}"
    assert modal_en["overflow"] <= 1, f"Modal 390 light overflow: {modal_en}"
    assert not INLINE_HANDLER_RE.search(modal_en["html"]), "Inline handler in #mockStartModal"

    # Screenshot 390x844 light
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "mock_start_modal_390_light.png"))

    # Dark mode overflow check
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    pg.wait_for_timeout(120)
    assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")

    # Focus trap: Tab cycles inside modal
    pg.keyboard.press("Tab")
    assert pg.evaluate("document.activeElement.id") == "mockStartMatBtn"
    pg.keyboard.press("Tab")
    assert pg.evaluate("document.activeElement.id") == "mockStartCancelBtn"
    pg.keyboard.press("Tab")
    assert pg.evaluate("document.activeElement.id") == "mockStartGoBtn"

    # Escape closes modal without starting timer
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    assert pg.evaluate("getComputedStyle(document.getElementById('mockStartModal')).display === 'none'")
    assert pg.evaluate("exIv === null")
    out["1_escape_no_start"] = True

    # 2. Spanish copy + Cancel button does not start timer
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    pg.click("#examSelectGrid .exam-card[data-paper='w']")
    pg.wait_for_timeout(150)
    modal_es = pg.evaluate(
        """() => ({
            title: document.getElementById('mockStartTitle').textContent.trim(),
            body: document.getElementById('mockStartBody').textContent.trim(),
            goText: document.getElementById('mockStartGoBtn').textContent.trim(),
            matText: document.getElementById('mockStartMatBtn').textContent.trim(),
            cancelText: document.getElementById('mockStartCancelBtn').textContent.trim(),
        })"""
    )
    assert "80" in modal_es["body"] and "Writing" in modal_es["body"], modal_es
    assert modal_es["goText"] == "Empezar contador", modal_es
    assert modal_es["matText"] == "Abrir materiales", modal_es
    assert modal_es["cancelText"] == "Cancelar", modal_es
    pg.click("#mockStartCancelBtn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("getComputedStyle(document.getElementById('mockStartModal')).display === 'none'")
    assert pg.evaluate("exIv === null")
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(150)
    out["2_cancel_es"] = modal_es

    # 3. "Open materials" opens Library filtered to paper and scope='full', timer not started
    pg.click("#examSelectGrid .exam-card[data-paper='l']")
    pg.wait_for_timeout(150)
    pg.click("#mockStartMatBtn")
    pg.wait_for_timeout(250)
    lib_after_mat = pg.evaluate(
        """() => ({
            view: (document.querySelector('.view.active') || {}).id || '',
            paper: EXLIB_PRACTICE_STATE.paper,
            scope: EXLIB_PRACTICE_STATE.scope,
            timerRunning: !!exIv,
        })"""
    )
    assert lib_after_mat == {"view": "v-practice", "paper": "l", "scope": "full", "timerRunning": False}, lib_after_mat
    out["3_open_materials"] = lib_after_mat

    # 4. "Start timer" closes modal and starts countdown once
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(200)
    pg.click("#examSelectGrid .exam-card[data-paper='rue']")
    pg.wait_for_timeout(150)
    pg.click("#mockStartGoBtn")
    pg.wait_for_timeout(2100)
    started = pg.evaluate(
        """() => ({
            modalOpen: getComputedStyle(document.getElementById('mockStartModal')).display !== 'none',
            running: exIv !== null,
            timer: document.getElementById('exTimer').textContent,
        })"""
    )
    assert not started["modalOpen"] and started["running"] and started["timer"] != "01:15:00", started
    pg.evaluate("exPause()")
    out["4_start_timer"] = started

    # 5. Full mock pre-flight also passes through modal; advancing paper auto-starts without modal
    pg.click("button[data-action='startFullMock']")
    pg.wait_for_timeout(200)
    pg.click("#fmStartSeqBtn")
    pg.wait_for_timeout(150)
    fm_modal = pg.evaluate(
        """() => ({
            open: getComputedStyle(document.getElementById('mockStartModal')).display !== 'none',
            body: document.getElementById('mockStartBody').textContent.trim(),
            running: exIv !== null,
            fullActive: FULL_MOCK.active,
        })"""
    )
    assert fm_modal["open"] and not fm_modal["running"] and fm_modal["fullActive"], fm_modal
    assert "195" in fm_modal["body"] and "14" in fm_modal["body"], fm_modal
    # In full mock modal, "Open materials" keeps user on #v-exam with #fmMaterialsAll visible and timer off
    pg.click("#mockStartMatBtn")
    pg.wait_for_timeout(200)
    assert pg.evaluate("(document.querySelector('.view.active')||{}).id === 'v-exam' && !document.getElementById('fullMockPreflight').hidden && exIv === null")
    pg.click("#fmStartSeqBtn")
    pg.wait_for_timeout(150)
    pg.click("#mockStartGoBtn")
    pg.wait_for_timeout(200)
    assert pg.evaluate("exIv !== null && FULL_MOCK.active && exPaper === 'rue' && !document.getElementById('fmRunner').hidden && document.getElementById('exActive').hidden")

    # Advance to Writing inside started full mock -> auto-starts without reopening modal, stays in #fmRunner
    pg.evaluate("fullMockAdvance()")
    pg.wait_for_timeout(200)
    adv = pg.evaluate(
        """() => ({
            modalOpen: getComputedStyle(document.getElementById('mockStartModal')).display !== 'none',
            running: exIv !== null,
            paper: exPaper,
            fullActive: FULL_MOCK.active,
            runnerVisible: !document.getElementById('fmRunner').hidden,
            exActiveHidden: document.getElementById('exActive').hidden,
        })"""
    )
    assert adv == {"modalOpen": False, "running": True, "paper": "w", "fullActive": True, "runnerVisible": True, "exActiveHidden": True}, adv
    pg.evaluate("exResetUser()")
    out["5_full_mock_modal_and_advance"] = {"modal": fm_modal["body"], "advanced": adv}

    assert page_errors == [], f"Page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
