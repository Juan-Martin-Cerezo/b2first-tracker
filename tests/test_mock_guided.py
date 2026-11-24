"""Phase mock-guided acceptance test: 3-step wizard (Explanation -> Materials -> Timer).

Verifies:
  1. Clicking a paper card opens #mockStartModal at step 1 with title, duration,
     progress bar ("1 Materiales · 2 Timer"), and does NOT start the timer over 2s.
  2. "Continuar a los materiales ->" advances to step 2 with >= 3 real paper links
     (`target="_blank"`), background materials panel visible & highlighted, `#v-exam`
     still active, clicking a link does not close modal, timer still off.
  3. "Ya tengo el material ->" advances to step 3 ("Listo para empezar", button >= 48px);
     "Empezar contador" closes modal and starts `#exTimer` (ticks within 2s).
     Repeating a mock returns to step 1.
  4. "Volver" from steps 2 & 3, Escape, and backdrop click do NOT start the timer;
     focus is trapped inside the modal and restored on close.
  5. Full mock ("Empezar simulacro completo") follows the exact same 3-step wizard;
     starting shows `#fmRunner` and advancing via `window.FULL_MOCK_TEST.setLeft(2)`
     does NOT reopen the wizard between papers.
  6. Zero "Abrir materiales" controls navigating to Library from mock start; zero
     duplicate visible material links in the same viewport (mobile 390 & desktop 1280).
  7. 390x844 zero horizontal overflow (light & dark), all wizard buttons >= 48px,
     EN/ES copy symmetry across all 3 steps, 0 inline handlers, 0 page/console errors.

Saves screenshots:
  tests/out/mock_guided_step1_390_light.png
  tests/out/mock_guided_step2_390_light.png
  tests/out/mock_guided_step3_390_light.png
  tests/out/mock_guided_step2_1280_light.png
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


def seed_all_sample_mats(pg):
    pg.evaluate("loadMaterial()")
    pg.wait_for_timeout(350)
    pg.evaluate(
        """() => {
            const keys = [
                'rueS1','keyS1','wS1','lS1','lkS1','auS1','tsS1','spS1','exC0',
                'ansRue','ansW','ansL','wCheck',
                'rueS2','keyS2','wS2','lS2','lkS2','auS2p1','auS2p2','auS2p3','auS2p4','spS2','exC1','exC2'
            ];
            keys.forEach(k => {
                if (!MAT[k]) MAT[k] = '/files/test-' + k + (k.startsWith('au') ? '.mp3' : '.pdf');
            });
            renderEx();
            renderFullMockPreflight();
        }"""
    )


def count_visible_duplicate_links(pg):
    return pg.evaluate(
        """() => {
            const els = [...document.querySelectorAll('#v-exam a[href], #mockStartModal a[href]')].filter(a => {
                if (a.closest('[hidden]')) return false;
                const cs = getComputedStyle(a);
                if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
                const r = a.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            });
            const counts = {};
            els.forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href) return;
                counts[href] = (counts[href] || 0) + 1;
            });
            const dups = Object.entries(counts).filter(([, c]) => c > 1);
            return { total: els.length, unique: Object.keys(counts).length, dups };
        }"""
    )


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    console_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.on(
        "console",
        lambda m: console_errors.append(m.text)
        if m.type == "error" and "Failed to load resource" not in m.text
        else None,
    )

    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('es'); document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(250)
    seed_all_sample_mats(pg)

    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(250)

    # --- 6a. No loose "Abrir materiales" controls anywhere in #v-exam or #mockStartModal ---
    no_loose = pg.evaluate(
        """() => {
            const exam = document.getElementById('v-exam');
            const modal = document.getElementById('mockStartModal');
            return {
                cardMatBtns: exam.querySelectorAll('.exam-card-mat-btn').length,
                openFullPaperBtns: document.querySelectorAll('button[data-action="openFullPaperLibrary"]').length,
                openMockMatBtns: document.querySelectorAll('button[data-action="openMockStartMaterials"]').length,
                mockStartMatBtn: !!document.getElementById('mockStartMatBtn'),
                exGuideBtns: document.querySelectorAll('#exGuide button').length,
                examLibraryLink: !!document.getElementById('examLibraryLink'),
                exActiveLibBtn: !!document.getElementById('exActiveLibBtn'),
                modalHtml: modal.outerHTML,
                examHtml: exam.outerHTML,
            };
        }"""
    )
    assert no_loose["cardMatBtns"] == 0, no_loose
    assert no_loose["openFullPaperBtns"] == 0, no_loose
    assert no_loose["openMockMatBtns"] == 0, no_loose
    assert not no_loose["mockStartMatBtn"], no_loose
    assert no_loose["exGuideBtns"] == 0, no_loose
    assert not no_loose["examLibraryLink"] and not no_loose["exActiveLibBtn"], no_loose
    assert not INLINE_HANDLER_RE.search(no_loose["modalHtml"]), "Inline handler in #mockStartModal"
    assert not INLINE_HANDLER_RE.search(no_loose["examHtml"]), "Inline handler in #v-exam"
    out["6_no_open_materials_controls"] = True

    # --- 1. Click R&UoE card -> Step 1 (Explanation), timer unchanged over 2s ---
    pg.click("#examSelectGrid .exam-card[data-paper='rue']")
    pg.wait_for_timeout(150)
    t0 = pg.inner_text("#exTimer")
    pg.wait_for_timeout(2100)
    t1 = pg.inner_text("#exTimer")
    assert t0 == "01:15:00" and t1 == "01:15:00", f"Timer moved in step 1: {t0} -> {t1}"
    assert pg.evaluate("exIv === null"), "exIv should be null in step 1"

    step1 = pg.evaluate(
        """() => {
            const ov = document.getElementById('mockStartModal');
            const visBtns = [...ov.querySelectorAll('button')].filter(b => !b.hidden && getComputedStyle(b).display !== 'none').map(b => ({
                id: b.id,
                text: b.textContent.trim(),
                h: Math.round(b.getBoundingClientRect().height),
            }));
            return {
                open: getComputedStyle(ov).display !== 'none',
                step: ov.dataset.step,
                role: ov.getAttribute('role'),
                ariaModal: ov.getAttribute('aria-modal'),
                progress: document.getElementById('mockGuidedProgress').textContent.replace(/\\s+/g, ' ').trim(),
                title: document.getElementById('mockStartTitle').textContent.trim(),
                body: document.getElementById('mockStartBody').textContent.trim(),
                visBtns,
                focusedId: document.activeElement ? document.activeElement.id : '',
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
        }"""
    )
    assert step1["open"] and step1["step"] == "1" and step1["role"] == "dialog" and step1["ariaModal"] == "true", step1
    assert "Reading & Use of English" in step1["title"], step1
    assert "75" in step1["body"], step1
    assert "1" in step1["progress"] and "Materiales" in step1["progress"] and "2" in step1["progress"] and "Timer" in step1["progress"], step1
    assert [b["id"] for b in step1["visBtns"]] == ["mockStartNextMatBtn", "mockStartCancelBtn"], step1["visBtns"]
    assert all(b["h"] >= 48 for b in step1["visBtns"]), f"Step 1 button < 48px: {step1['visBtns']}"
    assert step1["focusedId"] == "mockStartNextMatBtn", step1
    assert step1["overflow"] <= 1, step1
    pg.screenshot(path=os.path.join(OUT, "mock_guided_step1_390_light.png"))
    out["1_step1_rue"] = {"title": step1["title"], "progress": step1["progress"], "btns": step1["visBtns"]}

    # --- 2. "Continuar a los materiales ->" -> Step 2, >=3 links, target=_blank, bg panel visible & highlighted, 0 dups ---
    pg.click("#mockStartNextMatBtn")
    pg.wait_for_timeout(200)
    step2 = pg.evaluate(
        """() => {
            const ov = document.getElementById('mockStartModal');
            const links = [...ov.querySelectorAll('#mockStartMaterials a[href]')].map(a => ({
                text: a.textContent.trim(),
                href: a.getAttribute('href') || '',
                target: a.getAttribute('target') || '',
                h: Math.round(a.getBoundingClientRect().height),
            }));
            const visBtns = [...ov.querySelectorAll('button')].filter(b => !b.hidden && getComputedStyle(b).display !== 'none').map(b => ({
                id: b.id,
                text: b.textContent.trim(),
                h: Math.round(b.getBoundingClientRect().height),
            }));
            const bgPanel = document.getElementById('exPaperMaterials');
            const matBox = document.getElementById('mockStartMaterials');
            return {
                open: getComputedStyle(ov).display !== 'none',
                step: ov.dataset.step,
                view: (document.querySelector('.view.active') || {}).id || '',
                body: document.getElementById('mockStartBody').textContent.trim(),
                links,
                visBtns,
                timerRunning: exIv !== null,
                bgVisible: !!(bgPanel && !bgPanel.hidden && bgPanel.getBoundingClientRect().height > 0),
                bgHighlighted: !!(bgPanel && bgPanel.classList.contains('is-guided-highlight')),
                matMaxHeight: getComputedStyle(matBox).maxHeight,
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
        }"""
    )
    assert step2["open"] and step2["step"] == "2", step2
    assert step2["view"] == "v-exam", f"Left #v-exam in step 2: {step2}"
    assert not step2["timerRunning"], "Timer started in step 2!"
    assert "Abrí el paper" in step2["body"], step2
    assert len(step2["links"]) >= 3, f"Expected >= 3 links for R&UoE in step 2, got {step2['links']}"
    assert all(lk["target"] == "_blank" and lk["href"] for lk in step2["links"]), step2["links"]
    assert step2["bgVisible"] and step2["bgHighlighted"], f"Background paper materials panel not visible/highlighted: {step2}"
    assert [b["id"] for b in step2["visBtns"]] == ["mockStartHaveMatBtn", "mockStartBack1Btn"], step2["visBtns"]
    assert all(b["h"] >= 48 for b in step2["visBtns"]), f"Step 2 button < 48px: {step2['visBtns']}"
    assert step2["overflow"] <= 1, step2
    dups_paper_390 = count_visible_duplicate_links(pg)
    assert dups_paper_390["dups"] == [], f"Duplicate visible links in paper step 2 (390): {dups_paper_390}"
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(80)
    pg.screenshot(path=os.path.join(OUT, "mock_guided_step2_390_light.png"))

    # Verify clicking a material link (preventing actual navigation) does NOT close the modal
    still_open = pg.evaluate(
        """() => {
            const a = document.querySelector('#mockStartMaterials a[href]');
            const handler = e => e.preventDefault();
            a.addEventListener('click', handler, { once: true });
            a.click();
            return getComputedStyle(document.getElementById('mockStartModal')).display !== 'none'
                && document.getElementById('mockStartModal').dataset.step === '2';
        }"""
    )
    assert still_open, "Clicking a material link closed the modal or left step 2"
    out["2_step2_materials"] = {"links": len(step2["links"]), "dups": dups_paper_390["dups"]}

    # --- 4a. "Volver" from step 2 -> step 1 does NOT start timer ---
    pg.click("#mockStartBack1Btn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('mockStartModal').dataset.step === '1' && exIv === null")
    pg.click("#mockStartNextMatBtn")
    pg.wait_for_timeout(150)

    # --- 3. "Ya tengo el material ->" -> Step 3 -> "Empezar contador" starts #exTimer ---
    pg.click("#mockStartHaveMatBtn")
    pg.wait_for_timeout(150)
    step3 = pg.evaluate(
        """() => {
            const ov = document.getElementById('mockStartModal');
            const visBtns = [...ov.querySelectorAll('button')].filter(b => !b.hidden && getComputedStyle(b).display !== 'none').map(b => ({
                id: b.id,
                text: b.textContent.trim(),
                h: Math.round(b.getBoundingClientRect().height),
            }));
            return {
                open: getComputedStyle(ov).display !== 'none',
                step: ov.dataset.step,
                title: document.getElementById('mockStartTitle').textContent.trim(),
                body: document.getElementById('mockStartBody').textContent.trim(),
                visBtns,
                focusedId: document.activeElement ? document.activeElement.id : '',
                timerRunning: exIv !== null,
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
        }"""
    )
    assert step3["open"] and step3["step"] == "3", step3
    assert step3["title"] == "Listo para empezar", step3
    assert "75" in step3["body"] and "Empezar" in step3["body"], step3
    assert not step3["timerRunning"], "Timer started before clicking Start in step 3"
    assert [b["id"] for b in step3["visBtns"]] == ["mockStartGoBtn", "mockStartBack2Btn", "mockStartCancelBtn"], step3["visBtns"]
    assert all(b["h"] >= 48 for b in step3["visBtns"]), f"Step 3 button < 48px: {step3['visBtns']}"
    assert step3["focusedId"] == "mockStartGoBtn", step3
    assert step3["overflow"] <= 1, step3
    pg.screenshot(path=os.path.join(OUT, "mock_guided_step3_390_light.png"))

    # --- 4b. "Volver" from step 3 -> step 2 does NOT start timer; Tab trap & Escape ---
    pg.click("#mockStartBack2Btn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('mockStartModal').dataset.step === '2' && exIv === null")
    pg.click("#mockStartHaveMatBtn")
    pg.wait_for_timeout(150)

    # Focus trap in step 3: Go -> Back2 -> Cancel -> Go
    pg.keyboard.press("Tab")
    assert pg.evaluate("document.activeElement.id") == "mockStartBack2Btn"
    pg.keyboard.press("Tab")
    assert pg.evaluate("document.activeElement.id") == "mockStartCancelBtn"
    pg.keyboard.press("Tab")
    assert pg.evaluate("document.activeElement.id") == "mockStartGoBtn"

    # Escape closes without starting timer
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    assert pg.evaluate("getComputedStyle(document.getElementById('mockStartModal')).display === 'none' && exIv === null")

    # Click card again -> starts back at step 1 (repeating returns to step 1)
    pg.click("#examSelectGrid .exam-card[data-paper='rue']")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('mockStartModal').dataset.step === '1'")
    # Backdrop click closes without starting timer
    pg.evaluate("document.getElementById('mockStartModal').click()")
    pg.wait_for_timeout(150)
    assert pg.evaluate("getComputedStyle(document.getElementById('mockStartModal')).display === 'none' && exIv === null")
    out["4_back_escape_backdrop_no_start"] = True

    # Now complete 1 -> 2 -> 3 -> "Empezar contador" and verify #exTimer changes in 2s
    pg.click("#examSelectGrid .exam-card[data-paper='rue']")
    pg.wait_for_timeout(120)
    pg.click("#mockStartNextMatBtn")
    pg.wait_for_timeout(120)
    pg.click("#mockStartHaveMatBtn")
    pg.wait_for_timeout(120)
    pg.click("#mockStartGoBtn")
    pg.wait_for_timeout(2100)
    started = pg.evaluate(
        """() => ({
            modalOpen: getComputedStyle(document.getElementById('mockStartModal')).display !== 'none',
            running: exIv !== null,
            timer: document.getElementById('exTimer').textContent.trim(),
            paperMatVisible: !document.getElementById('exPaperMaterials').hidden && document.querySelectorAll('#exPaperMatList a').length >= 3,
        })"""
    )
    assert not started["modalOpen"] and started["running"] and started["timer"] != "01:15:00", started
    assert started["paperMatVisible"], started
    pg.evaluate("exResetUser()")
    out["3_start_timer"] = started

    # --- 5. Full mock: same 3-step wizard; runner starts & auto-advances without reopening wizard ---
    pg.click("#examSelectGrid .exam-card-full[data-action='startFullMock']")
    pg.wait_for_timeout(200)
    fm_s1 = pg.evaluate(
        """() => ({
            open: getComputedStyle(document.getElementById('mockStartModal')).display !== 'none',
            step: document.getElementById('mockStartModal').dataset.step,
            title: document.getElementById('mockStartTitle').textContent.trim(),
            body: document.getElementById('mockStartBody').textContent.trim(),
            running: exIv !== null,
        })"""
    )
    assert fm_s1["open"] and fm_s1["step"] == "1" and not fm_s1["running"], fm_s1
    assert "Full mock" in fm_s1["title"] and "195" in fm_s1["body"] and "14" in fm_s1["body"], fm_s1

    pg.click("#mockStartNextMatBtn")
    pg.wait_for_timeout(200)
    fm_s2 = pg.evaluate(
        """() => {
            const links = [...document.querySelectorAll('#mockStartMaterials a[href]')];
            const fmAll = document.getElementById('fmMaterialsAll');
            return {
                step: document.getElementById('mockStartModal').dataset.step,
                linkCount: links.length,
                allBlank: links.every(a => a.getAttribute('target') === '_blank'),
                bgVisible: !document.getElementById('fullMockPreflight').hidden && fmAll.getBoundingClientRect().height > 0,
                bgHighlighted: fmAll.classList.contains('is-guided-highlight'),
                running: exIv !== null,
                view: (document.querySelector('.view.active') || {}).id || '',
            };
        }"""
    )
    assert fm_s2["step"] == "2" and fm_s2["linkCount"] >= 3 and fm_s2["allBlank"] and not fm_s2["running"], fm_s2
    assert fm_s2["bgVisible"] and fm_s2["bgHighlighted"] and fm_s2["view"] == "v-exam", fm_s2
    dups_fm_390 = count_visible_duplicate_links(pg)
    assert dups_fm_390["dups"] == [], f"Duplicate visible links in full mock step 2 (390): {dups_fm_390}"

    pg.click("#mockStartHaveMatBtn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('mockStartModal').dataset.step === '3' && exIv === null")
    pg.click("#mockStartGoBtn")
    pg.wait_for_timeout(300)
    fm_run = pg.evaluate(
        """() => ({
            modalOpen: getComputedStyle(document.getElementById('mockStartModal')).display !== 'none',
            runnerVisible: !document.getElementById('fmRunner').hidden,
            exActiveHidden: document.getElementById('exActive').hidden,
            running: exIv !== null,
            paper: exPaper,
        })"""
    )
    assert fm_run == {"modalOpen": False, "runnerVisible": True, "exActiveHidden": True, "running": True, "paper": "rue"}, fm_run

    # Advance via test hook -> moves to Writing without reopening wizard
    pg.evaluate("window.FULL_MOCK_TEST.setLeft(2)")
    pg.wait_for_timeout(3100)
    fm_adv = pg.evaluate(
        """() => ({
            modalOpen: getComputedStyle(document.getElementById('mockStartModal')).display !== 'none',
            runnerVisible: !document.getElementById('fmRunner').hidden,
            running: exIv !== null,
            paper: exPaper,
        })"""
    )
    assert fm_adv == {"modalOpen": False, "runnerVisible": True, "running": True, "paper": "w"}, fm_adv
    pg.evaluate("closeFullMockPreflight(); exResetUser();")
    out["5_full_mock_guided"] = {"step2_links": fm_s2["linkCount"], "advanced": fm_adv}

    # --- 7. EN/ES symmetry + dark mode + Desktop 1280x800 Step 2 screenshot ---
    pg.evaluate("setLang('en'); document.documentElement.setAttribute('data-theme', 'dark')")
    pg.wait_for_timeout(200)
    pg.click("#examSelectGrid .exam-card[data-paper='w']")
    pg.wait_for_timeout(150)
    en_s1 = pg.evaluate(
        """() => ({
            progress: document.getElementById('mockGuidedProgress').textContent.replace(/\\s+/g, ' ').trim(),
            title: document.getElementById('mockStartTitle').textContent.trim(),
            body: document.getElementById('mockStartBody').textContent.trim(),
            nextText: document.getElementById('mockStartNextMatBtn').textContent.trim(),
            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        })"""
    )
    assert "Materials" in en_s1["progress"] and "Timer" in en_s1["progress"], en_s1
    assert "Writing" in en_s1["title"] and "80" in en_s1["body"], en_s1
    assert "Continue to materials" in en_s1["nextText"], en_s1
    assert en_s1["overflow"] <= 1, en_s1

    pg.click("#mockStartNextMatBtn")
    pg.wait_for_timeout(150)
    en_s2 = pg.evaluate(
        """() => ({
            body: document.getElementById('mockStartBody').textContent.trim(),
            links: document.querySelectorAll('#mockStartMaterials a[href]').length,
            haveText: document.getElementById('mockStartHaveMatBtn').textContent.trim(),
            backText: document.getElementById('mockStartBack1Btn').textContent.trim(),
            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        })"""
    )
    assert "Open the paper" in en_s2["body"] and en_s2["links"] >= 3, en_s2
    assert "I have the material" in en_s2["haveText"] and "Back" in en_s2["backText"], en_s2
    assert en_s2["overflow"] <= 1, en_s2

    pg.click("#mockStartHaveMatBtn")
    pg.wait_for_timeout(150)
    en_s3 = pg.evaluate(
        """() => ({
            title: document.getElementById('mockStartTitle').textContent.trim(),
            goText: document.getElementById('mockStartGoBtn').textContent.trim(),
            backText: document.getElementById('mockStartBack2Btn').textContent.trim(),
            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        })"""
    )
    assert en_s3["title"] == "Ready to start" and en_s3["goText"] == "Start timer" and "Materials" in en_s3["backText"], en_s3
    assert en_s3["overflow"] <= 1, en_s3
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)

    # Desktop 1280x800 light Step 2 screenshot + 520px card + 0 duplicate visible links
    pg.evaluate("setLang('es'); document.documentElement.setAttribute('data-theme', 'light')")
    pg.set_viewport_size({"width": 1280, "height": 800})
    pg.wait_for_timeout(250)
    pg.click("#examSelectGrid .exam-card[data-paper='l']")
    pg.wait_for_timeout(150)
    pg.click("#mockStartNextMatBtn")
    pg.wait_for_timeout(200)
    desk_s2 = pg.evaluate(
        """() => {
            const card = document.querySelector('#mockStartModal .mock-start-card');
            const r = card.getBoundingClientRect();
            return {
                cardW: Math.round(r.width),
                links: document.querySelectorAll('#mockStartMaterials a[href]').length,
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
        }"""
    )
    assert 480 <= desk_s2["cardW"] <= 525, f"Desktop modal width not ~520px: {desk_s2}"
    assert desk_s2["links"] >= 3, desk_s2
    assert desk_s2["overflow"] <= 1, desk_s2
    dups_desk = count_visible_duplicate_links(pg)
    assert dups_desk["dups"] == [], f"Duplicate visible links on 1280 desktop step 2: {dups_desk}"
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(80)
    pg.screenshot(path=os.path.join(OUT, "mock_guided_step2_1280_light.png"))
    out["7_en_dark_and_desktop"] = {"en_s3": en_s3, "desk_s2": desk_s2, "desk_dups": dups_desk["dups"]}

    assert page_errors == [], f"Page errors: {page_errors}"
    assert console_errors == [], f"Console errors: {console_errors}"
    out["errors"] = {"page": page_errors, "console": console_errors}
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
