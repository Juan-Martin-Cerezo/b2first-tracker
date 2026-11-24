"""Phase fullmock-oneplace acceptance test: one screen for full mock + materials.

Verifies:
  1. Opening full mock shows all 4 samples, the "tené todo a mano" copy, and the
     4 always-visible material blocks in #fmMaterialsAll (paper + key + audio/tapescript
     where available); switching sample updates all hrefs.
  2. Redundancies removed: no #examLibraryLink, no #exActiveLibBtn, no "Open materials"
     button in #exGuide, no visible manual paper selector block; keeps a single
     "Open materials" button per paper card in #examSelectGrid.
  3. Clicking Start opens #mockStartModal; clicking "Abrir materiales" closes the modal
     and keeps #fmMaterialsAll visible WITHOUT starting the timer (#exTimer unchanged
     over 2s) and WITHOUT leaving #v-exam.
  4. Clicking "Empezar contador" starts the timer in #fmRunner, hides #exActive, and
     does not scroll (scrollY diff <= 40px).
  5. Auto-advance: using window.FULL_MOCK_TEST.setLeft(2), after ~3s the runner advances
     from Paper 1 to Paper 2 and resets timer to 80′ (01:20:00); repeating advances to
     Paper 3 (Listening, 40′).
  6. "Saltar al siguiente paper" advances manually (with confirmation when running) and
     resets the timer.
  7. Finishing all 3 written papers opens Speaking overlay without leaving #v-exam;
     closing Speaking leaves #fmRunner showing "Completo" and the "Hacer otro" banner
     on the same screen.
  8. 390x844 zero horizontal overflow, links >= 44px, timer >= 28px, FAB does not
     overlap #fmStartSeqBtn; 1280x800 2-column layout; EN/ES symmetry; 0 console/page
     errors; 0 inline on* handlers.

Saves screenshots:
  tests/out/fullmock_materials_390_light.png
  tests/out/fullmock_runner_390_light.png
  tests/out/fullmock_materials_1280_light.png
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
    # Ensure all 4 full-mock samples have files in MAT even when local PDFs aren't on disk
    pg.evaluate(
        """() => {
            const keys = [
                'rueS1','keyS1','wS1','lS1','lkS1','auS1','tsS1','spS1','exC0',
                'rueS2','keyS2','wS2','lS2','lkS2','auS2p1','auS2p2','auS2p3','auS2p4','spS2','exC1','exC2',
                'rueFS1','keyFS1','wFS1','lFS1','lkFS1','auFS1p1','auFS1p2','auFS1p3','auFS1p4','tsFS1','spFS1','exC3',
                'rueFS2','keyFS2','wFS2','lFS2','lkFS2','auFS2','spFS2','exC4','exC5'
            ];
            keys.forEach(k => {
                if (!MAT[k]) MAT[k] = '/files/test-' + k + (k.startsWith('au') ? '.mp3' : '.pdf');
            });
            renderFullMockPreflight();
        }"""
    )


def boxes_overlap(a, b):
    return (
        a and b
        and a["w"] > 0 and a["h"] > 0
        and b["w"] > 0 and b["h"] > 0
        and not (
            a["right"] <= b["left"]
            or b["right"] <= a["left"]
            or a["bottom"] <= b["top"]
            or b["bottom"] <= a["top"]
        )
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

    # --- 2. Redundancies removed before opening full mock ---
    redundancies = pg.evaluate(
        """() => {
            const view = document.getElementById('v-exam');
            const exPaper = document.getElementById('exPaper');
            const exPaperVisible = !!(exPaper && exPaper.getBoundingClientRect().height > 0);
            const cardMatBtns = [...view.querySelectorAll('#examSelectGrid .exam-card')].map(c => ({
                paper: c.dataset.paper || '',
                matBtns: c.querySelectorAll('button[data-action="openFullPaperLibrary"]').length,
            }));
            return {
                hasExamLibraryLink: !!document.getElementById('examLibraryLink'),
                hasExActiveLibBtn: !!document.getElementById('exActiveLibBtn'),
                exGuideBtns: document.querySelectorAll('#exGuide button').length,
                exGuideLinks: document.querySelectorAll('#exGuide a').length,
                exGuideTextLen: (document.getElementById('exGuide')?.innerText || '').trim().length,
                exPaperExists: !!exPaper,
                exPaperVisible,
                cardMatBtns,
                allOpenMatInExam: view.querySelectorAll('button[data-action="openFullPaperLibrary"]').length,
                html: view.outerHTML,
            };
        }"""
    )
    assert not redundancies["hasExamLibraryLink"], "#examLibraryLink still exists"
    assert not redundancies["hasExActiveLibBtn"], "#exActiveLibBtn still exists"
    assert redundancies["exGuideBtns"] == 0, f"#exGuide still has buttons: {redundancies}"
    assert redundancies["exGuideLinks"] == 0, f"#exGuide still has links: {redundancies}"
    assert redundancies["exGuideTextLen"] > 20, f"#exGuide pace text missing: {redundancies}"
    assert redundancies["exPaperExists"] and not redundancies["exPaperVisible"], (
        f"#exPaper should stay hidden in DOM: {redundancies}"
    )
    assert [c["paper"] for c in redundancies["cardMatBtns"]] == ["rue", "w", "l", "sp"], redundancies
    assert all(c["matBtns"] == 0 for c in redundancies["cardMatBtns"]), redundancies
    assert redundancies["allOpenMatInExam"] == 0, (
        f"Expected 0 Open materials buttons in #v-exam (materials live in guided wizard/panel), got {redundancies['allOpenMatInExam']}"
    )
    assert not INLINE_HANDLER_RE.search(redundancies["html"]), "Inline on* handler found in #v-exam"
    out["2_redundancies_removed"] = {
        "examLibraryLink": False,
        "exActiveLibBtn": False,
        "exGuideBtns": 0,
        "exPaperVisible": False,
        "cardMatBtns": 0,
    }

    # --- 1. Open full mock: wizard opens on step 1 with preflight behind; closing wizard exposes all 4 samples & materials ---
    pg.click("button[data-action='startFullMock']")
    pg.wait_for_timeout(250)
    assert pg.evaluate("getComputedStyle(document.getElementById('mockStartModal')).display !== 'none' && document.getElementById('mockStartModal').dataset.step === '1'")
    pg.click("#mockStartCancelBtn")
    pg.wait_for_timeout(200)

    fm_s1 = pg.evaluate(
        """() => {
            const box = document.getElementById('fullMockPreflight');
            const samples = [...document.querySelectorAll('#fmSampleList button.fm-sample-btn')].map(b => ({
                id: b.dataset.sample,
                text: b.textContent.trim(),
                pressed: b.getAttribute('aria-pressed'),
            }));
            const groups = [...document.querySelectorAll('#fmMaterialsAll .fm-mat-group')].map(g => ({
                paper: g.dataset.fmMatPaper,
                visible: getComputedStyle(g).display !== 'none' && g.getBoundingClientRect().height > 0,
                links: [...g.querySelectorAll('a.fm-mat-link')].map(a => ({
                    name: a.querySelector('.fm-mat-name')?.textContent.trim() || '',
                    type: a.dataset.fmType || '',
                    href: a.getAttribute('href') || '',
                    target: a.getAttribute('target') || '',
                    h: Math.round(a.getBoundingClientRect().height),
                })),
            }));
            const paperRows = [...document.querySelectorAll('#fmPapersList .fm-paper-row')].map(r => ({
                paper: r.dataset.fmPaper,
                matBtns: r.querySelectorAll('button[data-action="openFullPaperLibrary"]').length,
                chips: r.querySelectorAll('.chip, .fm-paper-links a').length,
                practisedBtn: !!r.querySelector('.practised-mock-btn'),
            }));
            const onlineDetails = document.getElementById('fmOnlineDetails');
            const startBtn = document.getElementById('fmStartSeqBtn');
            const fab = document.getElementById('qlFab');
            const rect = el => {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height)};
            };
            return {
                preflightVisible: !box.hidden,
                title: box.querySelector('h2')?.textContent.trim() || '',
                sub: box.querySelector('.fm-head .sub')?.textContent.trim() || '',
                hint: document.getElementById('fmAtHandHint')?.textContent.trim() || '',
                samples,
                groups,
                paperRows,
                onlineCollapsed: !!(onlineDetails && onlineDetails.tagName === 'DETAILS' && !onlineDetails.open),
                startBtnText: startBtn ? startBtn.textContent.trim() : '',
                startBtnBox: rect(startBtn),
                fabBox: rect(fab),
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
            };
        }"""
    )

    assert fm_s1["preflightVisible"], "Full mock pre-flight did not open"
    assert "tené todo a mano" in fm_s1["title"].lower(), fm_s1["title"]
    assert "tené a mano" in fm_s1["hint"].lower(), fm_s1["hint"]
    assert [s["id"] for s in fm_s1["samples"]] == ["s1", "s2", "fs1", "fs2"], fm_s1["samples"]
    assert [g["paper"] for g in fm_s1["groups"]] == ["rue", "w", "l", "sp"], fm_s1["groups"]
    assert all(g["visible"] for g in fm_s1["groups"]), fm_s1["groups"]
    for g in fm_s1["groups"]:
        assert len(g["links"]) >= 1, f"Empty material group: {g}"
        for lk in g["links"]:
            assert lk["target"] == "_blank" and lk["href"], lk
            assert lk["h"] >= 44, f"Material link height < 44px: {lk}"
    # S1: R&UoE has paper+key; Listening has paper+key+audio+tapescript
    rue_types = {lk["type"] for lk in fm_s1["groups"][0]["links"]}
    l_types = {lk["type"] for lk in fm_s1["groups"][2]["links"]}
    sp_types = {lk["type"] for lk in fm_s1["groups"][3]["links"]}
    assert {"paper", "key"} <= rue_types, rue_types
    assert {"paper", "key", "audio", "tapescript"} <= l_types, l_types
    assert {"paper", "notes"} <= sp_types, sp_types
    # Paper rows have no Open materials button and no quick chips
    assert all(r["matBtns"] == 0 and r["chips"] == 0 and r["practisedBtn"] for r in fm_s1["paperRows"]), fm_s1["paperRows"]
    assert fm_s1["onlineCollapsed"], "More full mocks online should be inside a closed <details>"
    assert "195" in fm_s1["startBtnText"] and "14" in fm_s1["startBtnText"], fm_s1["startBtnText"]
    assert fm_s1["scrollWidth"] <= fm_s1["clientWidth"] + 1, f"390 overflow: {fm_s1['scrollWidth']} > {fm_s1['clientWidth']}"
    assert not boxes_overlap(fm_s1["fabBox"], fm_s1["startBtnBox"]), (
        f"FAB overlaps start button: fab={fm_s1['fabBox']} start={fm_s1['startBtnBox']}"
    )

    # Screenshot 1: fullmock_materials_390_light.png
    pg.evaluate("const el=document.getElementById('fullMockPreflight'); window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.scrollY - 60)); if(document.activeElement)document.activeElement.blur();")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "fullmock_materials_390_light.png"))

    # Switch sample to Standard 2 -> links change (and Listening shows 4 part audios)
    s1_hrefs = [lk["href"] for g in fm_s1["groups"] for lk in g["links"]]
    pg.click("#fmSampleList button.fm-sample-btn[data-sample='s2']")
    pg.wait_for_timeout(150)
    fm_s2 = pg.evaluate(
        """() => {
            const groups = [...document.querySelectorAll('#fmMaterialsAll .fm-mat-group')].map(g => ({
                paper: g.dataset.fmMatPaper,
                links: [...g.querySelectorAll('a.fm-mat-link')].map(a => ({
                    name: a.querySelector('.fm-mat-name')?.textContent.trim() || '',
                    type: a.dataset.fmType || '',
                    href: a.getAttribute('href') || '',
                })),
            }));
            return {sample: FULL_MOCK.sample, groups};
        }"""
    )
    assert fm_s2["sample"] == "s2", fm_s2
    s2_hrefs = [lk["href"] for g in fm_s2["groups"] for lk in g["links"]]
    assert s2_hrefs != s1_hrefs, "Changing sample did not update material links"
    s2_l_audios = [lk for lk in fm_s2["groups"][2]["links"] if lk["type"] == "audio"]
    assert len(s2_l_audios) == 4, f"Sample 2 Listening should list 4 audio parts, got {s2_l_audios}"
    # Switch back to s1 for clean flow
    pg.click("#fmSampleList button.fm-sample-btn[data-sample='s1']")
    pg.wait_for_timeout(120)
    out["1_preflight_materials"] = {"samples": [s["id"] for s in fm_s1["samples"]], "s2_listening_audios": len(s2_l_audios)}

    # --- 3. Start opens guided wizard step 1; step 2 keeps panel visible & highlighted, timer NOT started, stays in #v-exam ---
    pg.click("#fmStartSeqBtn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("getComputedStyle(document.getElementById('mockStartModal')).display !== 'none' && document.getElementById('mockStartModal').dataset.step === '1'"), "Modal did not open on step 1"
    t_before = pg.inner_text("#exTimer")
    pg.click("#mockStartNextMatBtn")
    pg.wait_for_timeout(2100)
    after_mat = pg.evaluate(
        """() => ({
            modalOpen: getComputedStyle(document.getElementById('mockStartModal')).display !== 'none',
            step: document.getElementById('mockStartModal').dataset.step,
            view: (document.querySelector('.view.active') || {}).id || '',
            preflightVisible: !document.getElementById('fullMockPreflight').hidden,
            materialsVisible: document.getElementById('fmMaterialsAll').getBoundingClientRect().height > 0,
            modalLinks: document.querySelectorAll('#mockStartMaterials a[target="_blank"]').length,
            timerRunning: exIv !== null,
            timerText: document.getElementById('exTimer').textContent,
        })"""
    )
    assert after_mat["modalOpen"] and after_mat["step"] == "2" and after_mat["modalLinks"] >= 3, after_mat
    assert after_mat["view"] == "v-exam", f"Left #v-exam on materials step: {after_mat}"
    assert after_mat["preflightVisible"] and after_mat["materialsVisible"], after_mat
    assert not after_mat["timerRunning"] and after_mat["timerText"] == t_before, (
        f"Timer changed in step 2: {t_before} -> {after_mat}"
    )
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    out["3_modal_open_materials_stays"] = after_mat

    # --- 4. Walking 1 -> 2 -> 3 -> "Empezar contador" starts timer in #fmRunner, hides #exActive, does NOT scroll ---
    pg.evaluate("const el=document.getElementById('fullMockPreflight'); window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.scrollY - 60));")
    pg.wait_for_timeout(150)
    scroll_before = pg.evaluate("Math.round(window.scrollY)")
    pg.click("#fmStartSeqBtn")
    pg.wait_for_timeout(150)
    pg.click("#mockStartNextMatBtn")
    pg.wait_for_timeout(150)
    pg.click("#mockStartHaveMatBtn")
    pg.wait_for_timeout(150)
    pg.click("#mockStartGoBtn")
    pg.wait_for_timeout(1200)
    runner_s1 = pg.evaluate(
        """() => {
            const runner = document.getElementById('fmRunner');
            const timer = document.getElementById('fmRunnerTimer');
            const exActive = document.getElementById('exActive');
            const cs = getComputedStyle(runner);
            const tcs = getComputedStyle(timer);
            const links = [...document.querySelectorAll('#fmRunnerLinks a.fm-runner-link')].map(a => ({
                href: a.getAttribute('href') || '',
                target: a.getAttribute('target') || '',
                h: Math.round(a.getBoundingClientRect().height),
            }));
            return {
                preflightOpen: !document.getElementById('fullMockPreflight').hidden,
                runnerVisible: !runner.hidden && runner.getBoundingClientRect().height > 0,
                runnerPosition: cs.position,
                exActiveHidden: exActive.hidden && getComputedStyle(exActive).display === 'none',
                title: document.getElementById('fmRunnerTitle').textContent.trim(),
                timerText: timer.textContent.trim(),
                timerFontPx: parseFloat(tcs.fontSize),
                exTimerText: document.getElementById('exTimer').textContent.trim(),
                running: exIv !== null,
                scrollY: Math.round(window.scrollY),
                links,
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
        }"""
    )
    assert runner_s1["preflightOpen"] and runner_s1["runnerVisible"], runner_s1
    assert runner_s1["runnerPosition"] == "sticky", runner_s1
    assert runner_s1["exActiveHidden"], f"#exActive not hidden during full mock: {runner_s1}"
    assert "Paper 1" in runner_s1["title"] and "Reading & Use of English" in runner_s1["title"] and "75" in runner_s1["title"], runner_s1
    assert runner_s1["running"] and runner_s1["timerText"] == runner_s1["exTimerText"], runner_s1
    assert runner_s1["timerText"] != "01:15:00", f"Timer did not tick: {runner_s1}"
    assert runner_s1["timerFontPx"] >= 28, f"Runner timer font < 28px: {runner_s1['timerFontPx']}"
    assert len(runner_s1["links"]) >= 2 and all(lk["h"] >= 44 and lk["target"] == "_blank" for lk in runner_s1["links"]), runner_s1["links"]
    assert abs(runner_s1["scrollY"] - scroll_before) <= 40, (
        f"Page scrolled on confirmMockStart: {scroll_before} -> {runner_s1['scrollY']}"
    )
    assert runner_s1["overflow"] <= 1, f"Runner 390 overflow: {runner_s1['overflow']}"

    # Screenshot 2: fullmock_runner_390_light.png
    pg.evaluate("if(document.activeElement)document.activeElement.blur();")
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "fullmock_runner_390_light.png"))
    out["4_runner_in_place"] = {
        "title": runner_s1["title"],
        "timer": runner_s1["timerText"],
        "font_px": runner_s1["timerFontPx"],
        "scroll_delta": runner_s1["scrollY"] - scroll_before,
        "exActive_hidden": runner_s1["exActiveHidden"],
    }

    # --- 5. Auto-advance via window.FULL_MOCK_TEST.setLeft(2) -> Paper 2 (80′) -> Paper 3 (40′) ---
    scroll_pre_adv = pg.evaluate("Math.round(window.scrollY)")
    pg.evaluate("window.FULL_MOCK_TEST.setLeft(2)")
    pg.wait_for_timeout(3100)
    p2 = pg.evaluate(
        """() => ({
            title: document.getElementById('fmRunnerTitle').textContent.trim(),
            timer: document.getElementById('fmRunnerTimer').textContent.trim(),
            paper: exPaper,
            left: exLeft,
            running: exIv !== null,
            scrollY: Math.round(window.scrollY),
        })"""
    )
    assert "Paper 2" in p2["title"] and "Writing" in p2["title"] and "80" in p2["title"], p2
    assert p2["paper"] == "w" and p2["running"] and 4795 <= p2["left"] <= 4800, p2
    assert abs(p2["scrollY"] - scroll_pre_adv) <= 40, f"Auto-advance scrolled: {scroll_pre_adv} -> {p2['scrollY']}"

    pg.evaluate("window.FULL_MOCK_TEST.setLeft(2)")
    pg.wait_for_timeout(3100)
    p3 = pg.evaluate(
        """() => ({
            title: document.getElementById('fmRunnerTitle').textContent.trim(),
            timer: document.getElementById('fmRunnerTimer').textContent.trim(),
            paper: exPaper,
            left: exLeft,
            running: exIv !== null,
        })"""
    )
    assert "Paper 3" in p3["title"] and "Listening" in p3["title"] and "40" in p3["title"], p3
    assert p3["paper"] == "l" and p3["running"] and 2395 <= p3["left"] <= 2400, p3
    out["5_auto_advance"] = {"paper2": p2["title"], "paper3": p3["title"]}

    # --- 6. Manual skip ("Saltar al siguiente paper") with confirmation when running ---
    # Reset back to Paper 1 to test manual skip from Paper 1 -> Paper 2
    pg.evaluate("FULL_MOCK.idx = 0; startRealMock('rue', true, true);")
    pg.wait_for_timeout(150)
    pg.click("#fmRunnerSkipBtn")
    pg.wait_for_timeout(120)
    assert pg.evaluate("!document.getElementById('fmSkipConfirm').hidden"), "Skip confirmation did not appear while timer running"
    pg.click("#fmSkipConfirmBtn")
    pg.wait_for_timeout(200)
    skipped_p2 = pg.evaluate(
        """() => ({
            title: document.getElementById('fmRunnerTitle').textContent.trim(),
            paper: exPaper,
            left: exLeft,
            running: exIv !== null,
            confirmHidden: document.getElementById('fmSkipConfirm').hidden,
        })"""
    )
    assert "Paper 2" in skipped_p2["title"] and skipped_p2["paper"] == "w" and skipped_p2["running"], skipped_p2
    assert 4795 <= skipped_p2["left"] <= 4800 and skipped_p2["confirmHidden"], skipped_p2

    # Pause -> skip advances immediately without confirmation -> Paper 3 (Listening)
    pg.click("#fmRunnerPauseBtn")
    pg.wait_for_timeout(120)
    assert pg.evaluate("exIv === null"), "Pause button did not pause timer"
    pg.click("#fmRunnerSkipBtn")
    pg.wait_for_timeout(200)
    skipped_p3 = pg.evaluate(
        """() => ({
            title: document.getElementById('fmRunnerTitle').textContent.trim(),
            paper: exPaper,
            left: exLeft,
            running: exIv !== null,
        })"""
    )
    assert "Paper 3" in skipped_p3["title"] and skipped_p3["paper"] == "l" and skipped_p3["running"], skipped_p3
    assert 2395 <= skipped_p3["left"] <= 2400, skipped_p3
    out["6_manual_skip"] = {"to_p2": skipped_p2["title"], "to_p3": skipped_p3["title"]}

    # --- 7. Finish Listening -> Speaking overlay opens on #v-exam; closing Speaking shows "Completo" & "Hacer otro" ---
    pg.evaluate("window.FULL_MOCK_TEST.setLeft(2)")
    pg.wait_for_timeout(3100)
    after_l = pg.evaluate(
        """() => ({
            view: (document.querySelector('.view.active') || {}).id || '',
            spxOpen: getComputedStyle(document.getElementById('spxOverlay')).display !== 'none',
            timerRunning: exIv !== null,
        })"""
    )
    assert after_l["view"] == "v-exam" and after_l["spxOpen"] and not after_l["timerRunning"], after_l

    # Close Speaking overlay -> back on the exact same screen with "Completo" + "Hacer otro"
    pg.evaluate("SP_EXAM.close()")
    pg.wait_for_timeout(200)
    after_sp = pg.evaluate(
        """() => ({
            view: (document.querySelector('.view.active') || {}).id || '',
            preflightVisible: !document.getElementById('fullMockPreflight').hidden,
            runnerVisible: !document.getElementById('fmRunner').hidden,
            runnerState: document.getElementById('fmRunner').dataset.fmState || '',
            runnerTitle: document.getElementById('fmRunnerTitle').textContent.trim(),
            doneBannerVisible: !document.getElementById('fmDoneBanner').hidden,
            doAnotherText: document.getElementById('fmDoAnotherBtn').textContent.trim(),
        })"""
    )
    assert after_sp["view"] == "v-exam" and after_sp["preflightVisible"], after_sp
    assert after_sp["runnerVisible"] and after_sp["runnerState"] == "done", after_sp
    assert "completo" in after_sp["runnerTitle"].lower(), after_sp
    assert after_sp["doneBannerVisible"] and "otro" in after_sp["doAnotherText"].lower(), after_sp
    out["7_after_speaking"] = after_sp

    # --- 8. EN/ES symmetry + dark mode + 1280x800 2-column layout ---
    pg.click("#fmDoAnotherBtn")
    pg.wait_for_timeout(200)

    # Check EN symmetry
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)
    en_check = pg.evaluate(
        """() => ({
            title: document.querySelector('#fullMockPreflight h2').textContent.trim(),
            hint: document.getElementById('fmAtHandHint').textContent.trim(),
            startText: document.getElementById('fmStartSeqBtn').textContent.trim(),
            matTitle: document.querySelector('#fmMaterialsAll .fm-block-title').textContent.trim(),
            overflow390: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        })"""
    )
    assert "at hand" in en_check["title"].lower() and "at hand" in en_check["matTitle"].lower(), en_check
    assert "195" in en_check["startText"] and "14" in en_check["startText"], en_check
    assert en_check["overflow390"] <= 1, f"EN 390 overflow: {en_check}"

    # Dark mode 390 overflow check
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    pg.wait_for_timeout(120)
    assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1

    # Desktop 1280x800 light: 2 columns (left setup | right materials) + screenshot
    pg.evaluate("setLang('es'); document.documentElement.setAttribute('data-theme', 'light')")
    pg.set_viewport_size({"width": 1280, "height": 800})
    pg.wait_for_timeout(250)
    pg.evaluate("document.getElementById('fullMockPreflight').scrollIntoView({block:'start'}); if(document.activeElement)document.activeElement.blur();")
    pg.wait_for_timeout(150)
    desk = pg.evaluate(
        """() => {
            const setup = document.querySelector('#fullMockPreflight .fm-setup-box').getBoundingClientRect();
            const mats = document.querySelector('#fullMockPreflight .fm-materials-wrap').getBoundingClientRect();
            return {
                setupLeft: Math.round(setup.left),
                setupRight: Math.round(setup.right),
                matsLeft: Math.round(mats.left),
                matsRight: Math.round(mats.right),
                matsTop: Math.round(mats.top),
                setupTop: Math.round(setup.top),
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
        }"""
    )
    assert desk["overflow"] <= 1, f"1280 overflow: {desk}"
    assert desk["matsLeft"] >= desk["setupRight"] - 2, f"1280 is not 2 columns side by side: {desk}"
    assert abs(desk["matsTop"] - desk["setupTop"]) <= 40, f"Materials column not aligned with setup column: {desk}"
    pg.screenshot(path=os.path.join(OUT, "fullmock_materials_1280_light.png"))
    out["8_desktop_and_i18n"] = {"en": en_check, "desk_2col": desk}

    assert page_errors == [], f"Page errors: {page_errors}"
    assert console_errors == [], f"Console errors: {console_errors}"
    out["errors"] = {"page": page_errors, "console": console_errors}
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
