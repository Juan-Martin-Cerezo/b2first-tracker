#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 UI end-to-end tests + real mobile (390x844) and desktop (1280x800) screenshots.

Runs completely offline with B2_SPK_TEST_MODE=1 and an in-browser audio stub.
Run: cd tests && uv run --with playwright python test_speaking_v3_ui.py
"""
import json
import os
import sys
import tempfile
import urllib.request

from playwright.sync_api import sync_playwright

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
OUT_DIR = os.path.join(TESTS_DIR, "out")
os.makedirs(OUT_DIR, exist_ok=True)

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

from helpers import isolated_server, login_owner, OWNER_NAME  # noqa: E402

# Minimal valid 8x8 PNG for own-task upload tests
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def assert_no_horizontal_overflow(pg, label):
    dims = pg.evaluate("() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})")
    assert dims["sw"] <= dims["iw"], f"{label}: horizontal overflow {dims}"


def assert_no_script_or_transcript_in_dom(pg, label, forbidden_snippets=()):
    txt = pg.evaluate("() => (document.getElementById('speakingOverlay') || {}).innerText || ''").lower()
    base_forbidden = [
        "good morning",
        "good afternoon",
        "good evening",
        "and your names are",
        "where do you live",
        "compare the photographs",
        "all right?",
        "wrong answer",
        "ai is thinking",
        "transcript",
        "pronunciation",
    ]
    for s in base_forbidden + list(forbidden_snippets):
        assert s.lower() not in txt, f"{label}: forbidden text {s!r} leaked into Speaking DOM: {txt!r}"


def wait_for_mic_ready(pg, timeout=15000):
    pg.wait_for_function(
        """() => {
            const b = document.getElementById('speakingMicBtn');
            return b && !b.disabled && b.getAttribute('data-mic-state') === 'ready';
        }""",
        timeout=timeout,
    )
    pg.wait_for_timeout(160)


def hold_to_speak(pg, transcript_text, hold_ms=120):
    """Simulate push-to-talk pointerdown -> pointerup with stub audio and test transcript."""
    pg.evaluate(
        """(tx) => {
            window.__SPK_TEST_AUDIO_STUB__ = true;
            window.__SPK_TEST_TRANSCRIPT_FN__ = () => tx;
        }""",
        transcript_text,
    )
    box = pg.locator("#speakingMicBtn").bounding_box()
    assert box and box["height"] >= 56, f"Mic button too small: {box}"
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    pg.mouse.move(cx, cy)
    pg.mouse.down()
    pg.wait_for_timeout(hold_ms)
    rec_state = pg.evaluate("() => document.getElementById('speakingMicBtn').getAttribute('data-mic-state')")
    assert rec_state == "recording", f"Expected recording state during hold, got {rec_state}"
    pg.mouse.up()


def install_next_turn_delay(pg, delay_ms=1500):
    """Delay the next /turn fetch once inside the page so checking UI stays visible."""
    pg.evaluate(
        """(ms) => {
            if (!window.__origFetch) window.__origFetch = window.fetch;
            window.__nextTurnDelayMs = ms;
            if (!window.__delayPatched) {
                window.__delayPatched = true;
                window.fetch = function(url, opts) {
                    const p = window.__origFetch.apply(this, arguments);
                    if (window.__nextTurnDelayMs > 0 && String(url).includes('/turn')) {
                        const waitMs = window.__nextTurnDelayMs;
                        window.__nextTurnDelayMs = 0;
                        return new Promise((resolve, reject) => setTimeout(() => p.then(resolve, reject), waitMs));
                    }
                    return p;
                };
            }
        }""",
        delay_ms,
    )


def main():
    base = isolated_server(extra_env={
        "B2_SPK_TEST_MODE": "1",
        "B2_OWNER_UIDS": OWNER_NAME,
    })
    url = base + "/"

    # Create two temporary PNG files for own-task upload testing
    tmp_dir = tempfile.mkdtemp(prefix="b2spk-ui-")
    img1_path = os.path.join(tmp_dir, "city.png")
    img2_path = os.path.join(tmp_dir, "nature.png")
    with open(img1_path, "wb") as f:
        f.write(TINY_PNG)
    with open(img2_path, "wb") as f:
        f.write(TINY_PNG)

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # =====================================================================
        # PART A: Mobile 390x844 full user flow + screenshots
        # =====================================================================
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        pg = ctx.new_page()
        page_errors = []
        console_errors = []
        console_logs = []
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.on(
            "console",
            lambda m: (
                console_errors.append(m.text)
                if m.type == "error" and "Failed to load resource" not in m.text
                else console_logs.append(m.text)
            ),
        )

        # Track network requests to verify POSTs & sequence
        net_calls = []
        pg.on("request", lambda req: net_calls.append((req.method, req.url, req.post_data)))

        pg.goto(url + "app", wait_until="networkidle")
        login_owner(pg, url)
        pg.evaluate("setLang('en')")
        pg.wait_for_timeout(250)

        # Open Speaking chooser via openSpeakingExam()
        pg.evaluate("openSpeakingExam()")
        pg.wait_for_selector("#speakingOverlay.is-open")
        pg.wait_for_selector("#speakingCatalogGrid .spk3-exam-card")
        pg.wait_for_timeout(200)

        # 1. Verify exact 4 tests + partner names + Full mock + Practise a part 1-4 + Use my own task
        cards = pg.evaluate(
            """() => Array.from(document.querySelectorAll('#speakingCatalogGrid .spk3-exam-card')).map(c => ({
                id: c.dataset.testId,
                title: c.querySelector('.spk3-exam-title').textContent.trim(),
                partner: c.querySelector('.spk3-exam-partner').textContent.trim(),
                parts: Array.from(c.querySelectorAll('.spk3-chip')).map(b => b.textContent.trim()),
                hasFull: !!c.querySelector('.spk3-full-btn'),
            }))"""
        )
        assert len(cards) == 4, f"Expected 4 tests in chooser, got {cards}"
        assert [c["title"] for c in cards] == [
            "B2 First Sample Paper 1",
            "B2 First Sample Paper 2",
            "B2 First for Schools Sample Paper 1",
            "B2 First for Schools Sample Paper 2",
        ], cards
        assert "with Alex" in cards[0]["partner"], cards[0]
        assert all(c["parts"] == ["1", "2", "3", "4"] and c["hasFull"] for c in cards), cards
        assert pg.is_visible("#speakingOwnTaskBtn"), "Use my own task button missing"
        assert_no_horizontal_overflow(pg, "chooser-390")
        assert_no_script_or_transcript_in_dom(pg, "chooser-390")
        pg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_chooser_390.png"))
        results["chooser"] = {"cards": len(cards)}

        # 2. Start Part 2 of Test 01 -> verify Intro plays examiner first, then enables mic
        # Observe role transitions during playback via MutationObserver
        pg.evaluate(
            """() => {
                window.__roleLog = [];
                const record = () => {
                    const active = Array.from(document.querySelectorAll('#speakingRoles .spk3-role'))
                        .filter(el => el.getAttribute('data-active') === 'true')
                        .map(el => el.dataset.role);
                    const micDis = document.getElementById('speakingMicBtn').disabled;
                    const entry = active.join(',') + '|dis:' + micDis;
                    if (window.__roleLog[window.__roleLog.length - 1] !== entry) {
                        window.__roleLog.push(entry);
                    }
                };
                window.__obs = new MutationObserver(record);
                window.__obs.observe(document.getElementById('speakingViewExam'), {
                    attributes: true, subtree: true, attributeFilter: ['data-active', 'disabled']
                });
            }"""
        )

        pg.click('.spk3-exam-card[data-test-id="01"] .spk3-chip[data-part="2"]')
        pg.wait_for_selector('#speakingViewExam.is-active')
        wait_for_mic_ready(pg)

        # Screenshot of Intro (ready to speak, clean exam desk, timer --:--)
        intro_timer = pg.text_content("#speakingTimer").strip()
        assert intro_timer == "--:--", f"Timer must not run during intro, got {intro_timer}"
        assert_no_horizontal_overflow(pg, "intro-390")
        assert_no_script_or_transcript_in_dom(pg, "intro-390")
        pg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_intro_390.png"))

        # Verify examiner spoke with mic disabled BEFORE mic enabled for YOU
        intro_log = pg.evaluate("() => window.__roleLog.slice()")
        assert any(x.startswith("examiner|dis:true") for x in intro_log), f"Examiner did not speak with mic disabled: {intro_log}"
        assert intro_log[-1] == "you|dis:false", f"Expected YOU active with mic enabled after intro audio: {intro_log}"

        # 3. Direct auto-send UX (no preflight, no buttons, animated checking state)
        removed_count = pg.evaluate(
            "() => document.querySelectorAll('#speakingPreflight, #speakingCheckBtn, #speakingRecordAgainBtn, #speakingPreflightSkipBtn, #speakingAutoCheck').length"
        )
        assert removed_count == 0, f"Preflight elements still present in DOM: {removed_count}"

        pg.evaluate("() => { window.__roleLog = []; }")
        net_calls.clear()
        install_next_turn_delay(pg, 1400)
        canary_name = "My name is Juan"
        hold_to_speak(pg, canary_name)
        pg.wait_for_selector("#speakingCheckingBox:not([hidden])", timeout=5000)

        turn_posts_immediate = [c for c in net_calls if c[0] == "POST" and "/turn" in c[1]]
        assert turn_posts_immediate, f"Releasing mic did not send POST /turn immediately: {net_calls}"

        chk_info = pg.evaluate(
            """() => {
                const box = document.getElementById('speakingCheckingBox');
                const stage = document.getElementById('speakingConvStage');
                const stageBar = stage.querySelector('.spk3-wave i');
                const chkBar = box.querySelector('.spk3-checking-wave i');
                const progBar = box.querySelector('.spk3-checking-bar');
                return {
                    visible: !box.hidden,
                    waveBars: box.querySelectorAll('.spk3-wave i').length,
                    buttons: box.querySelectorAll('button').length,
                    hasProgress: !!box.querySelector('.spk3-checking-progress .spk3-checking-bar'),
                    title: (document.getElementById('speakingCheckingTitle').textContent || '').trim(),
                    note: (document.getElementById('speakingCheckingNote').textContent || '').trim(),
                    micState: document.getElementById('speakingMicBtn').getAttribute('data-mic-state'),
                    micDisabled: document.getElementById('speakingMicBtn').disabled,
                    stageLive: stage.getAttribute('data-live'),
                    stageAnim: stageBar ? getComputedStyle(stageBar).animationName : '',
                    chkAnim: chkBar ? getComputedStyle(chkBar).animationName : '',
                    progAnim: progBar ? getComputedStyle(progBar).animationName : '',
                };
            }"""
        )
        assert chk_info["visible"] and chk_info["waveBars"] == 7, chk_info
        assert chk_info["buttons"] == 0 and chk_info["hasProgress"], chk_info
        assert "Checking your answer" in chk_info["title"] and chk_info["title"].endswith("s"), chk_info
        assert chk_info["note"] == "Checking your answers takes a few seconds.", chk_info
        assert chk_info["micState"] == "sending" and chk_info["micDisabled"], chk_info
        assert chk_info["stageLive"] == "checking" and chk_info["stageAnim"] == "spk3Wave", chk_info
        assert chk_info["chkAnim"] == "spk3Wave" and chk_info["progAnim"] == "spk3Progress", chk_info
        assert_no_horizontal_overflow(pg, "checking-intro-390")

        # Verify prefers-reduced-motion disables animations while keeping progress & text visible
        pg.emulate_media(reduced_motion="reduce")
        rm_info = pg.evaluate(
            """() => {
                const box = document.getElementById('speakingCheckingBox');
                const stageBar = document.querySelector('#speakingConvStage .spk3-wave i');
                const chkBar = box.querySelector('.spk3-checking-wave i');
                const progBar = box.querySelector('.spk3-checking-bar');
                return {
                    visible: !box.hidden,
                    stageAnim: getComputedStyle(stageBar).animationName,
                    chkAnim: getComputedStyle(chkBar).animationName,
                    progAnim: getComputedStyle(progBar).animationName,
                    progW: progBar.getBoundingClientRect().width,
                };
            }"""
        )
        assert rm_info["visible"] and rm_info["progW"] > 0, rm_info
        assert rm_info["stageAnim"] == "none" and rm_info["chkAnim"] == "none" and rm_info["progAnim"] == "none", rm_info
        pg.emulate_media(reduced_motion="no-preference")

        wait_for_mic_ready(pg)
        assert not pg.is_visible("#speakingCheckingBox"), "Checking box remained visible after mic ready"
        seq_log = pg.evaluate("() => window.__roleLog.slice()")
        p_idx = next((i for i, x in enumerate(seq_log) if x == "partner|dis:true"), -1)
        e_idx = next((i for i, x in enumerate(seq_log) if x == "examiner|dis:true" and i > p_idx), -1)
        y_idx = next((i for i, x in enumerate(seq_log) if x == "you|dis:false" and i > e_idx), -1)
        assert 0 <= p_idx < e_idx < y_idx, f"Sequence did not respect partner -> examiner -> you with mic locked: {seq_log}"
        assert_no_script_or_transcript_in_dom(pg, "after-name", [canary_name])
        results["auto_checking"] = {"immediate_post": True, "wave_bars": 7, "reduced_motion_ok": True}

        # Verify retry (accepted: false, retry: true) sends directly and does not display "wrong answer"
        hold_to_speak(pg, "I like pizza")
        wait_for_mic_ready(pg)
        assert pg.evaluate("() => SPEAKING.step") == "ask_home"
        assert_no_script_or_transcript_in_dom(pg, "after-retry", ["I like pizza"])

        # Answer ask_home -> enters Part 2
        net_calls.clear()
        hold_to_speak(pg, "I live in Buenos Aires")
        wait_for_mic_ready(pg)
        assert any(c[0] == "POST" and "/turn" in c[1] for c in net_calls), "Turn did not submit automatically"

        assert pg.evaluate("() => SPEAKING.phase") == "part2"
        p2_info = pg.evaluate(
            """() => {
                const imgs = [document.getElementById('speakingPhoto1'), document.getElementById('speakingPhoto2')];
                const vw = window.innerWidth;
                const vh = window.innerHeight;
                const mic = document.getElementById('speakingMicBtn').getBoundingClientRect();
                return {
                    timer: document.getElementById('speakingTimer').textContent.trim(),
                    photosHidden: document.getElementById('speakingPhotos').hidden,
                    micHeight: Math.round(mic.height),
                    imgs: imgs.map(im => {
                        const r = im.getBoundingClientRect();
                        return {
                            src: im.getAttribute('src') || '',
                            complete: im.complete,
                            nw: im.naturalWidth,
                            left: Math.round(r.left),
                            right: Math.round(r.right),
                            bottom: Math.round(r.bottom),
                            vw, vh,
                        };
                    }),
                };
            }"""
        )
        assert not p2_info["photosHidden"], p2_info
        assert p2_info["timer"] != "--:--", f"Part 2 timer did not start: {p2_info}"
        assert p2_info["micHeight"] >= 56, f"Mic button height < 56px: {p2_info}"
        assert p2_info["imgs"][0]["src"].endswith("/assets/speaking/exams/01/p2-1a.jpg"), p2_info
        assert p2_info["imgs"][1]["src"].endswith("/assets/speaking/exams/01/p2-1b.jpg"), p2_info
        for im in p2_info["imgs"]:
            assert im["complete"] and im["nw"] > 0, f"Photo failed to load: {im}"
            assert im["left"] >= 0 and im["right"] <= im["vw"], f"Photo overflows viewport horizontally: {im}"
            assert im["bottom"] <= im["vh"], f"Photo overflows viewport vertically: {im}"
        assert_no_horizontal_overflow(pg, "part2-390")
        assert_no_script_or_transcript_in_dom(pg, "part2-390", ["Buenos Aires"])
        pg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_part2_390.png"))
        results["part2_mobile"] = p2_info

        # Complete Part 2 (comparing photos -> partner sequence -> Task 2 photos -> follow-up -> report!)
        # Delay Part 2 turn briefly to verify checking panel is visible over photos on mobile + capture screenshot
        install_next_turn_delay(pg, 1400)
        canary_p2 = "Both photographs show people helping others, whereas the first shows a football player and the second shows a police officer."
        hold_to_speak(pg, canary_p2)
        pg.wait_for_selector("#speakingCheckingBox:not([hidden])", timeout=5000)
        pg.wait_for_timeout(150)
        p2_chk_rect = pg.evaluate(
            """() => {
                const r = document.getElementById('speakingCheckingBox').getBoundingClientRect();
                const guide = document.getElementById('speakingPartGuide').getBoundingClientRect();
                const photo1 = document.getElementById('speakingPhoto1').getBoundingClientRect();
                return {
                    top: Math.round(r.top),
                    bottom: Math.round(r.bottom),
                    vh: window.innerHeight,
                    w: Math.round(r.width),
                    guideBottom: Math.round(guide.bottom),
                    photo1Top: Math.round(photo1.top),
                };
            }"""
        )
        assert p2_chk_rect["w"] > 200 and p2_chk_rect["bottom"] <= p2_chk_rect["vh"], p2_chk_rect
        assert p2_chk_rect["photo1Top"] >= p2_chk_rect["guideBottom"], p2_chk_rect
        assert_no_horizontal_overflow(pg, "checking-part2-390")
        pg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_checking_390.png"))
        wait_for_mic_ready(pg)
        p2_t2_srcs = pg.evaluate(
            "() => [document.getElementById('speakingPhoto1').getAttribute('src'), document.getElementById('speakingPhoto2').getAttribute('src')]"
        )
        assert p2_t2_srcs[0].endswith("/assets/speaking/exams/01/p2-2a.jpg"), p2_t2_srcs
        assert p2_t2_srcs[1].endswith("/assets/speaking/exams/01/p2-2b.jpg"), p2_t2_srcs

        hold_to_speak(pg, "I would prefer the quiet private garden because I enjoy peaceful nature and looking after plants.")

        # 4. Report view: 3 bands, NO pronunciation, NO transcript; Save report calls endpoint!
        pg.wait_for_selector("#speakingViewReport.is-active", timeout=15000)
        pg.wait_for_selector("#speakingReportBands .spk3-band-card", timeout=15000)
        rep_info = pg.evaluate(
            """() => ({
                labels: Array.from(document.querySelectorAll('#speakingReportBands .spk3-band-lbl')).map(e => e.textContent.trim()),
                vals: Array.from(document.querySelectorAll('#speakingReportBands .spk3-band-val')).map(e => e.textContent.trim()),
                text: document.getElementById('speakingViewReport').innerText,
            })"""
        )
        assert rep_info["labels"] == [
            "Grammar & Vocabulary",
            "Discourse Management",
            "Interactive Communication",
        ], rep_info
        assert "pronunciation" not in rep_info["text"].lower(), rep_info
        assert "transcript" not in rep_info["text"].lower(), rep_info
        assert canary_p2.lower() not in rep_info["text"].lower(), rep_info
        assert_no_horizontal_overflow(pg, "report-390")
        pg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_report_390.png"))

        # Click Save report -> calls POST .../report with save:true
        net_calls.clear()
        pg.click("#speakingSaveReportBtn")
        pg.wait_for_function("() => SPEAKING.reportSaved === true", timeout=10000)
        save_posts = [c for c in net_calls if c[0] == "POST" and "/report" in c[1] and c[2] and '"save":true' in c[2].replace(" ", "")]
        assert save_posts, f"Save report did not POST save:true: {net_calls}"
        assert "Report saved" in pg.text_content("#speakingSaveReportBtn")
        # Verify nothing about transcripts leaked into localStorage or console
        ls_dump = pg.evaluate("() => JSON.stringify(localStorage)")
        assert canary_p2 not in ls_dump, "Transcript leaked to localStorage!"
        assert all(canary_p2 not in c for c in console_logs), "Transcript leaked to console!"
        results["report"] = {"labels": rep_info["labels"], "saved": True}

        # 5. Part 3: card visible, 15s prep countdown, automatic prep_done!
        pg.click('#speakingViewReport [data-action="speakingBackToChooser"]')
        pg.wait_for_selector("#speakingViewChooser.is-active")
        # Speed up prep tick AFTER checking initial 15s display so test completes quickly
        pg.evaluate("() => { SPEAKING._prepStepMs = 35; }")
        pg.click('.spk3-exam-card[data-test-id="01"] .spk3-chip[data-part="3"]')
        pg.wait_for_selector("#speakingViewExam.is-active")
        wait_for_mic_ready(pg)
        hold_to_speak(pg, "My name is Juan")
        wait_for_mic_ready(pg)
        net_calls.clear()
        hold_to_speak(pg, "I live in Buenos Aires")

        # Wait for Part 3 card to show and prep_done to fire automatically -> discussion_0 -> mic ready!
        wait_for_mic_ready(pg, timeout=15000)
        p3_state = pg.evaluate(
            """() => {
                const img = document.getElementById('speakingCardImg');
                const r = img.getBoundingClientRect();
                return {
                    phase: SPEAKING.phase,
                    step: SPEAKING.step,
                    cardHidden: document.getElementById('speakingCardWrap').hidden,
                    src: img.getAttribute('src') || '',
                    complete: img.complete,
                    nw: img.naturalWidth,
                    right: Math.round(r.right),
                    vw: window.innerWidth,
                };
            }"""
        )
        assert p3_state["phase"] == "part3" and p3_state["step"] == "discussion_0", p3_state
        assert not p3_state["cardHidden"] and p3_state["src"].endswith("/assets/speaking/exams/01/p3-card.png"), p3_state
        assert p3_state["complete"] and p3_state["nw"] > 0 and p3_state["right"] <= p3_state["vw"], p3_state
        prep_calls = [c for c in net_calls if c[0] == "POST" and "/turn" in c[1] and c[2] and "prep_done" in c[2]]
        assert prep_calls, f"Automatic prep_done was not sent: {net_calls}"
        assert_no_horizontal_overflow(pg, "part3-390")
        assert_no_script_or_transcript_in_dom(pg, "part3-390")
        pg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_part3_390.png"))

        # Verify Part 3 discussion auto-submits POST /turn immediately on release
        net_calls.clear()
        hold_to_speak(pg, "Providing parks is a nice idea")
        wait_for_mic_ready(pg)
        turn_posts = [c for c in net_calls if c[0] == "POST" and "/turn" in c[1]]
        assert turn_posts and pg.evaluate("() => SPEAKING.step") == "discussion_1", f"Auto-send failed in Part 3: {net_calls}"

        # Verify safe Skip turn ONLY appears when mic is denied, calling /skip and NEVER /turn
        assert not pg.is_visible("#speakingSkipBtn"), "Skip button must stay hidden while mic works"
        pg.evaluate(
            """() => {
                window.__SPK_TEST_AUDIO_STUB__ = false;
                window.__origGetUserMedia = navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
                if (navigator.mediaDevices) {
                    navigator.mediaDevices.getUserMedia = () => Promise.reject(new Error('Permission denied'));
                }
            }"""
        )
        net_calls.clear()
        box = pg.locator("#speakingMicBtn").bounding_box()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pg.mouse.down()
        pg.wait_for_selector("#speakingSkipBtn:not([hidden])", timeout=5000)
        pg.mouse.up()
        pg.click("#speakingSkipBtn")
        wait_for_mic_ready(pg)
        skip_posts = [c for c in net_calls if c[0] == "POST" and "/skip" in c[1]]
        turn_posts_after_skip = [c for c in net_calls if c[0] == "POST" and "/turn" in c[1]]
        assert skip_posts and not turn_posts_after_skip, f"Mic-denied skip race: skip={skip_posts}, turn={turn_posts_after_skip}"
        assert pg.evaluate("() => SPEAKING.step") == "decision_0"
        pg.evaluate(
            """() => {
                window.__SPK_TEST_AUDIO_STUB__ = true;
                if (navigator.mediaDevices && window.__origGetUserMedia) {
                    navigator.mediaDevices.getUserMedia = window.__origGetUserMedia;
                }
            }"""
        )
        results["part3"] = {"step": p3_state["step"], "prep_done_sent": True, "auto_send": True, "safe_mic_denied_skip": True}

        # 6. Own task: open form, test validation per part, create Part 2 own task, start & verify images, delete
        pg.evaluate("() => { SPEAKING.backToChooser(); }")
        pg.wait_for_selector("#speakingViewChooser.is-active")
        pg.click("#speakingOwnTaskBtn")
        pg.wait_for_selector("#speakingViewOwn.is-active")
        assert_no_horizontal_overflow(pg, "own-task-390")
        pg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_own_task_390.png"))

        # Validation: empty title
        pg.click("#spkOwnSaveBtn")
        assert pg.locator("#speakingOwnErr.is-visible").is_visible()
        # Validation: Part 1 requires questions
        pg.fill("#spkOwnTitle", "My Part 1 Set")
        pg.select_option("#spkOwnPart", "1")
        pg.click("#spkOwnSaveBtn")
        assert "question" in pg.text_content("#speakingOwnErr").lower()
        # Validation: Part 3 requires discussion
        pg.select_option("#spkOwnPart", "3")
        pg.click("#spkOwnSaveBtn")
        assert "discussion" in pg.text_content("#speakingOwnErr").lower()
        # Validation: Part 2 requires prompt and 2 photos
        pg.select_option("#spkOwnPart", "2")
        pg.click("#spkOwnSaveBtn")
        assert "part 2" in pg.text_content("#speakingOwnErr").lower()
        pg.fill("#spkOwnPrompt", "Compare city life and quiet nature")
        pg.click("#spkOwnSaveBtn")
        assert "2 photograph" in pg.text_content("#speakingOwnErr").lower()

        # Upload 2 PNGs and save valid Part 2 own task
        pg.fill("#spkOwnTitle", "City vs Nature")
        pg.set_input_files("#spkOwnPhoto1", img1_path)
        pg.set_input_files("#spkOwnPhoto2", img2_path)
        pg.click("#spkOwnSaveBtn")
        pg.wait_for_selector("#speakingViewChooser.is-active", timeout=10000)
        pg.wait_for_selector(".spk3-own-card", timeout=10000)
        own_titles = pg.eval_on_selector_all(".spk3-own-name", "els => els.map(e => e.textContent.trim())")
        assert "City vs Nature" in own_titles, own_titles

        # Start own task -> complete intro -> verify authenticated own-task images render!
        pg.click('.spk3-own-card [data-action="speakingStartOwn"]')
        pg.wait_for_selector("#speakingViewExam.is-active")
        wait_for_mic_ready(pg)
        hold_to_speak(pg, "Juan")
        wait_for_mic_ready(pg)
        hold_to_speak(pg, "Buenos Aires")
        wait_for_mic_ready(pg)
        own_imgs = pg.evaluate(
            """() => [document.getElementById('speakingPhoto1'), document.getElementById('speakingPhoto2')].map(i => ({
                src: i.getAttribute('src') || '', complete: i.complete, nw: i.naturalWidth
            }))"""
        )
        assert all(i["src"].startswith("data:image/") and i["complete"] and i["nw"] > 0 for i in own_imgs), own_imgs

        # Return and delete own task
        pg.evaluate("() => SPEAKING.backToChooser()")
        pg.wait_for_selector("#speakingViewChooser.is-active")
        pg.click('.spk3-own-card [data-action="speakingDeleteOwn"]')
        pg.wait_for_function("() => document.querySelectorAll('.spk3-own-card').length === 0", timeout=10000)
        results["own_task"] = {"created": True, "started_with_images": True, "deleted": True}

        # 7. Error handling: 503 speech_not_configured, 429 quota, 410 expired
        # Mock 503 on POST /api/speaking/v3/sessions
        def route_503(route):
            if route.request.method == "POST":
                route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": "speech_not_configured"}))
            else:
                route.continue_()

        pg.route("**/api/speaking/v3/sessions*", route_503)
        pg.click('.spk3-exam-card[data-test-id="01"] .spk3-full-btn')
        pg.wait_for_selector("#speakingExamErr.is-visible")
        err503_txt = pg.text_content("#speakingExamErr")
        assert "not configured" in err503_txt.lower(), err503_txt
        assert pg.locator('#speakingExamErr [data-action="speakingOpenSettings"]').is_visible()
        pg.unroute("**/api/speaking/v3/sessions*", route_503)

        # Mock 429 quota
        pg.evaluate("() => SPEAKING.backToChooser()")
        pg.wait_for_selector("#speakingViewChooser.is-active")

        def route_429(route):
            if route.request.method == "POST":
                route.fulfill(status=429, content_type="application/json", body=json.dumps({"error": "limit_reached", "limit": "speaking", "reset": "2026-11-27"}))
            else:
                route.continue_()

        pg.route("**/api/speaking/v3/sessions*", route_429)
        pg.click('.spk3-exam-card[data-test-id="01"] .spk3-full-btn')
        pg.wait_for_selector("#speakingExamErr.is-visible")
        err429_txt = pg.text_content("#speakingExamErr")
        assert "limit" in err429_txt.lower(), err429_txt
        pg.unroute("**/api/speaking/v3/sessions*", route_429)

        # Mock 410 session_expired on turn -> returns to chooser with notice
        pg.evaluate("() => SPEAKING.backToChooser()")
        pg.wait_for_selector("#speakingViewChooser.is-active")
        pg.click('.spk3-exam-card[data-test-id="01"] .spk3-chip[data-part="1"]')
        wait_for_mic_ready(pg)

        def route_410(route):
            route.fulfill(status=410, content_type="application/json", body=json.dumps({"error": "session_expired"}))

        pg.route("**/api/speaking/v3/sessions/*/turn*", route_410)
        hold_to_speak(pg, "Juan")
        pg.wait_for_selector("#speakingViewChooser.is-active", timeout=10000)
        pg.wait_for_selector("#speakingChooserErr.is-visible")
        assert "expired" in pg.text_content("#speakingChooserErr").lower()
        pg.unroute("**/api/speaking/v3/sessions/*/turn*", route_410)
        results["errors_handled"] = {"503": True, "429": True, "410": True}

        assert page_errors == [], f"Mobile page errors: {page_errors}"
        assert console_errors == [], f"Mobile console errors: {console_errors}"
        ctx.close()

        # =====================================================================
        # PART B: Desktop 1280x800 layout & screenshot
        # =====================================================================
        dctx = browser.new_context(viewport={"width": 1280, "height": 800})
        dpg = dctx.new_page()
        d_errors = []
        dpg.on("pageerror", lambda e: d_errors.append(str(e)))
        dpg.goto(url + "app", wait_until="networkidle")
        login_owner(dpg, url)
        dpg.evaluate("setLang('en')")
        dpg.wait_for_timeout(200)

        # Open chooser on desktop, check overflow, then enter Part 2 and screenshot desktop exam!
        dpg.evaluate("SPEAKING.open()")
        dpg.wait_for_selector("#speakingCatalogGrid .spk3-exam-card")
        assert_no_horizontal_overflow(dpg, "chooser-1280")

        dpg.click('.spk3-exam-card[data-test-id="02"] .spk3-chip[data-part="2"]')
        wait_for_mic_ready(dpg)
        hold_to_speak(dpg, "Juan")
        wait_for_mic_ready(dpg)
        hold_to_speak(dpg, "Buenos Aires")
        wait_for_mic_ready(dpg)

        desk_info = dpg.evaluate(
            """() => {
                const imgs = [document.getElementById('speakingPhoto1'), document.getElementById('speakingPhoto2')];
                const mic = document.getElementById('speakingMicBtn').getBoundingClientRect();
                const desk = document.getElementById('speakingDesk').getBoundingClientRect();
                const panel = document.getElementById('speakingPanel').getBoundingClientRect();
                const guide = (document.getElementById('speakingPartGuide').textContent || '').trim();
                return {
                    sw: document.documentElement.scrollWidth,
                    iw: window.innerWidth,
                    micH: Math.round(mic.height),
                    twoCol: desk.right <= panel.left + 4 && Math.abs(desk.top - panel.top) < 120,
                    deskW: Math.round(desk.width),
                    panelW: Math.round(panel.width),
                    photoW: Math.round(imgs[0].getBoundingClientRect().width),
                    guideLen: guide.length,
                    photosInView: imgs.every(im => {
                        const r = im.getBoundingClientRect();
                        return im.complete && im.naturalWidth > 0 && r.left >= 0 && r.right <= window.innerWidth && r.bottom <= window.innerHeight;
                    }),
                };
            }"""
        )
        assert desk_info["sw"] <= desk_info["iw"], desk_info
        assert desk_info["micH"] >= 56, desk_info
        assert desk_info["twoCol"], f"Desktop is not two-column: {desk_info}"
        assert desk_info["photoW"] >= 280, f"Desktop photos still too small: {desk_info}"
        assert desk_info["guideLen"] > 20, f"Part explanation missing on desktop panel: {desk_info}"
        assert desk_info["photosInView"], desk_info
        assert_no_script_or_transcript_in_dom(dpg, "desktop-part2-1280")
        dpg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_desktop_1280.png"))

        # Desktop Part 3 card screenshot (two-column with large card)
        dpg.evaluate("() => { SPEAKING.backToChooser(); SPEAKING._prepStepMs = 30; }")
        dpg.wait_for_selector("#speakingViewChooser.is-active")
        dpg.click('.spk3-exam-card[data-test-id="01"] .spk3-chip[data-part="3"]')
        wait_for_mic_ready(dpg)
        hold_to_speak(dpg, "Juan")
        wait_for_mic_ready(dpg)
        hold_to_speak(dpg, "Buenos Aires")
        wait_for_mic_ready(dpg, timeout=15000)
        p3_desk = dpg.evaluate(
            """() => {
                const card = document.getElementById('speakingCardImg').getBoundingClientRect();
                const panel = document.getElementById('speakingPanel').getBoundingClientRect();
                return { cardW: Math.round(card.width), cardH: Math.round(card.height), twoCol: card.right <= panel.left + 8 };
            }"""
        )
        assert p3_desk["twoCol"] and p3_desk["cardH"] >= 260, p3_desk
        assert_no_script_or_transcript_in_dom(dpg, "desktop-part3-1280")
        dpg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_part3_1280.png"))

        # Desktop Part 4 conversation stage (no empty white box; active role + waveform + timer, no questions)
        dpg.evaluate("() => SPEAKING.backToChooser()")
        dpg.wait_for_selector("#speakingViewChooser.is-active")
        dpg.click('.spk3-exam-card[data-test-id="01"] .spk3-chip[data-part="4"]')
        wait_for_mic_ready(dpg)
        hold_to_speak(dpg, "Juan")
        wait_for_mic_ready(dpg)
        hold_to_speak(dpg, "Buenos Aires")
        wait_for_mic_ready(dpg)
        p4_desk = dpg.evaluate(
            """() => {
                const st = document.getElementById('speakingConvStage');
                const r = st.getBoundingClientRect();
                return {
                    hidden: st.hidden,
                    h: Math.round(r.height),
                    speaker: document.getElementById('speakingStageSpeaker').textContent.trim(),
                    timer: document.getElementById('speakingStageTimer').textContent.trim(),
                    waveBars: st.querySelectorAll('.spk3-wave i').length,
                };
            }"""
        )
        assert not p4_desk["hidden"] and p4_desk["h"] >= 200 and p4_desk["waveBars"] >= 5, p4_desk
        assert p4_desk["timer"] != "--:--", p4_desk
        assert_no_script_or_transcript_in_dom(dpg, "desktop-part4-1280")
        dpg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_part4_1280.png"))

        # Desktop checking state screenshot (Part 4: shows animated stage wave + checking panel in sidebar)
        install_next_turn_delay(dpg, 1400)
        hold_to_speak(dpg, "I think people enjoy holidays because they can relax and explore new places.")
        dpg.wait_for_selector("#speakingCheckingBox:not([hidden])", timeout=5000)
        dpg.wait_for_timeout(150)
        chk_desk = dpg.evaluate(
            """() => {
                const box = document.getElementById('speakingCheckingBox').getBoundingClientRect();
                const stage = document.getElementById('speakingConvStage');
                const stageBar = stage.querySelector('.spk3-wave i');
                return {
                    sw: document.documentElement.scrollWidth,
                    iw: window.innerWidth,
                    boxBottom: Math.round(box.bottom),
                    vh: window.innerHeight,
                    stageLive: stage.getAttribute('data-live'),
                    stageAnim: getComputedStyle(stageBar).animationName,
                    hasProgress: !!document.querySelector('#speakingCheckingBox .spk3-checking-bar'),
                };
            }"""
        )
        assert chk_desk["sw"] <= chk_desk["iw"] and chk_desk["boxBottom"] <= chk_desk["vh"], chk_desk
        assert chk_desk["stageLive"] == "checking" and chk_desk["stageAnim"] == "spk3Wave" and chk_desk["hasProgress"], chk_desk
        dpg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_checking_1280.png"))
        wait_for_mic_ready(dpg)

        assert d_errors == [], f"Desktop page errors: {d_errors}"
        results["desktop"] = {"part2": desk_info, "part3": p3_desk, "part4": p4_desk, "checking": chk_desk}
        dctx.close()

        browser.close()

    print(json.dumps(results, indent=2))
    print("PASS test_speaking_v3_ui")
    return 0


if __name__ == "__main__":
    sys.exit(main())
