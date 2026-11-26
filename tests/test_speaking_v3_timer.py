#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3: checking the candidate's answer must not consume part time.

Runs offline (B2_SPK_TEST_MODE=1) and stretches the /turn request in the
browser for 6 s. The visible part timer must stay frozen during that wait,
then resume when the examiner/partner audio starts.
"""
import os
import sys

from playwright.sync_api import sync_playwright

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))
sys.path.insert(0, TESTS_DIR)

from helpers import isolated_server, login_owner, OWNER_NAME  # noqa: E402


def mmss_to_s(txt):
    m, s = txt.strip().split(":")
    return int(m) * 60 + int(s)


def wait_mic(pg, timeout=15000):
    pg.wait_for_function(
        "() => { const b=document.getElementById('speakingMicBtn');"
        " return b && !b.disabled && b.getAttribute('data-mic-state')==='ready'; }",
        timeout=timeout,
    )


def say(pg, text, confirm=True):
    pg.evaluate(
        """(tx) => {
            window.__SPK_TEST_AUDIO_STUB__ = true;
            window.__SPK_TEST_TRANSCRIPT_FN__ = () => tx;
        }""",
        text,
    )
    box = pg.locator("#speakingMicBtn").bounding_box()
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    pg.mouse.down()
    pg.wait_for_timeout(120)
    pg.mouse.up()
    if confirm:
        pg.wait_for_selector("#speakingPreflight:not([hidden])", timeout=5000)
        pg.click("#speakingCheckBtn")


def main():
    base = isolated_server(extra_env={"B2_SPK_TEST_MODE": "1", "B2_OWNER_UIDS": OWNER_NAME})
    url = base + "/"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url, wait_until="networkidle")
        login_owner(pg, url)
        pg.evaluate("SPEAKING.open('01',2)")
        wait_mic(pg, 20000)
        say(pg, "My name is Juan")
        wait_mic(pg, 20000)
        say(pg, "I live in Buenos Aires")
        wait_mic(pg, 20000)

        assert pg.evaluate("() => SPEAKING.phase") == "part2"
        pg.wait_for_timeout(1300)
        t0 = pg.text_content("#speakingTimer").strip()
        pg.wait_for_timeout(1300)
        t1 = pg.text_content("#speakingTimer").strip()
        assert mmss_to_s(t1) < mmss_to_s(t0), f"Timer is not running normally: {t0} -> {t1}"

        # Delay only the next turn request, inside the page, for 6 seconds.
        pg.evaluate("""() => {
            if (window.__slowTurnFetch) return;
            window.__slowTurnFetch = true;
            const orig = window.fetch;
            window.fetch = function(url, opts) {
                const p = orig.apply(this, arguments);
                if (String(url).includes('/turn')) {
                    return new Promise((resolve, reject) => setTimeout(() => p.then(resolve, reject), 6000));
                }
                return p;
            };
        }""")

        say(pg, "Both photographs show people helping others, while the first one shows a football player.")
        pg.wait_for_timeout(1100)
        during_a = pg.text_content("#speakingTimer").strip()
        mic_state = pg.get_attribute("#speakingMicBtn", "data-mic-state")
        assert mic_state == "sending", f"Expected sending state while checking, got {mic_state}"
        chk_visible = pg.is_visible("#speakingCheckingBox")
        chk_txt = (pg.text_content("#speakingCheckingBox") or "").lower()
        assert chk_visible and "checking" in chk_txt and "please wait" not in chk_txt, (chk_visible, chk_txt)
        pg.wait_for_timeout(3000)
        during_b = pg.text_content("#speakingTimer").strip()
        assert during_a == during_b, (
            f"Part timer consumed checking time: {during_a} -> {during_b} during a 6 s wait"
        )

        wait_mic(pg, 30000)
        after = pg.text_content("#speakingTimer").strip()
        lost = mmss_to_s(during_b) - mmss_to_s(after)
        assert lost <= 5, f"Timer jumped {lost}s after checking (audio should count, checking should not)"
        assert not errors, f"Page errors: {errors}"
        browser.close()

    print(f"PASS timer frozen while checking ({during_a} -> {during_b}), after audio {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
