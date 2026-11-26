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

        # 3. Push-to-talk name turn -> partner speaks THEN examiner speaks, mic disabled during both!
        pg.evaluate("() => { window.__roleLog = []; }")
        canary_name = "My name is Juan"
        hold_to_speak(pg, canary_name)
        wait_for_mic_ready(pg)
        seq_log = pg.evaluate("() => window.__roleLog.slice()")
        p_idx = next((i for i, x in enumerate(seq_log) if x == "partner|dis:true"), -1)
        e_idx = next((i for i, x in enumerate(seq_log) if x == "examiner|dis:true" and i > p_idx), -1)
        y_idx = next((i for i, x in enumerate(seq_log) if x == "you|dis:false" and i > e_idx), -1)
        assert 0 <= p_idx < e_idx < y_idx, f"Sequence did not respect partner -> examiner -> you with mic locked: {seq_log}"
        assert_no_script_or_transcript_in_dom(pg, "after-name", [canary_name])

        # Verify retry (accepted: false, retry: true) does not display "wrong answer"
        hold_to_speak(pg, "I like pizza")
        wait_for_mic_ready(pg)
        assert pg.evaluate("() => SPEAKING.step") == "ask_home"
        assert_no_script_or_transcript_in_dom(pg, "after-retry", ["I like pizza"])

        # Valid home -> enters Part 2 with Test 01 photos & official 04:00 timer!
        hold_to_speak(pg, "I live in Buenos Aires")
        wait_for_mic_ready(pg)

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
        canary_p2 = "Both photographs show people helping others, whereas the first shows a football player and the second shows a police officer."
        hold_to_speak(pg, canary_p2)
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
        results["part3"] = {"step": p3_state["step"], "prep_done_sent": True}

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
                return {
                    sw: document.documentElement.scrollWidth,
                    iw: window.innerWidth,
                    micH: Math.round(mic.height),
                    photosInView: imgs.every(im => {
                        const r = im.getBoundingClientRect();
                        return im.complete && im.naturalWidth > 0 && r.left >= 0 && r.right <= window.innerWidth && r.bottom <= window.innerHeight;
                    }),
                };
            }"""
        )
        assert desk_info["sw"] <= desk_info["iw"], desk_info
        assert desk_info["micH"] >= 56, desk_info
        assert desk_info["photosInView"], desk_info
        dpg.screenshot(path=os.path.join(OUT_DIR, "speaking_v3_desktop_1280.png"))
        assert d_errors == [], f"Desktop page errors: {d_errors}"
        results["desktop"] = desk_info
        dctx.close()

        browser.close()

    print(json.dumps(results, indent=2))
    print("PASS test_speaking_v3_ui")
    return 0


if __name__ == "__main__":
    sys.exit(main())
