"""Practice hub acceptance: two intents, inline parts, direct routes.

Contract:
  1. Practice shows exactly two intents: Full mock and Practise by part.
  2. The old Library card is not visible in Practice.
  3. The part chooser is inline: 17 rows, one button each, no extra actions.
  4. Reading/Listening part -> Session. Writing part -> Contents + corrector CTA.
     Speaking part -> Speaking exam overlay.
  5. Recent practice block is present; progress charts are not shown in Practice.
  6. 390x844 / 1280x800: no horizontal overflow, no page errors.
"""
import os
import sys

from playwright.sync_api import sync_playwright

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

from helpers import isolated_server, login_owner  # noqa: E402

URL = isolated_server() + "/"
OUT = os.path.join(TESTS, "out")
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(350)

    assert pg.evaluate("document.querySelectorAll('.practice-intent-card').length") == 2
    assert pg.evaluate("document.getElementById('practiceLibraryCard').hidden")
    assert pg.evaluate("document.querySelectorAll('#practiceOverview .practice-progress-card').length") == 0
    assert pg.evaluate("!!document.querySelector('#practiceOverview .practice-recent')")
    assert pg.evaluate("document.querySelectorAll('#practicePartChooser .part-row').length") == 17
    assert pg.evaluate("document.querySelectorAll('#practicePartChooser button:not([data-action=startPart])').length") == 0

    # By-part button activates: scrolls to the inline chooser.
    before = pg.evaluate("window.scrollY")
    pg.click("#practiceIntentByPart")
    pg.wait_for_timeout(800)
    assert pg.evaluate("window.scrollY") > before, "By-part button did not scroll to the chooser"

    # Reading Part 1 -> Session (not Contents).
    pg.evaluate("window.scrollTo(0,0)")
    pg.click("#practicePartChooser .part-row[data-i='0']")
    pg.wait_for_timeout(450)
    assert pg.evaluate("!document.getElementById('sessionTabSession').hidden")
    assert pg.evaluate("document.getElementById('sessionTabContents').hidden")
    pg.evaluate("closeSessionStudios()")

    # Writing Part 1 -> materials first, then corrector.
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(250)
    pg.click("#practicePartChooser .part-row[data-i='15']")
    pg.wait_for_timeout(450)
    assert pg.evaluate("!document.getElementById('sessionTabContents').hidden")
    assert pg.evaluate("!document.getElementById('sessionWritingCta').hidden")
    pg.click("#sessionWritingCta button")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.getElementById('v-ia').classList.contains('active')")
    pg.evaluate("closeSessionStudios()")

    # Speaking Part 1 -> AI speaking overlay, no Session detour.
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(250)
    pg.click("#practicePartChooser .part-row[data-i='11']")
    pg.wait_for_timeout(900)
    assert pg.evaluate("document.getElementById('speakingOverlay').classList.contains('is-open')")
    assert pg.evaluate("typeof SPEAKING !== 'undefined' && SPEAKING.view === 'exam'")
    pg.evaluate("SPEAKING.close()")
    pg.wait_for_timeout(200)

    # Full mock intent still opens the exam preflight.
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(250)
    pg.click("#practiceIntentFullMock")
    pg.wait_for_timeout(450)
    assert pg.evaluate("document.getElementById('v-exam').classList.contains('active')")
    pg.evaluate("closeMockStartModal(false)")

    # Mobile and desktop overflow + screenshots.
    pg.evaluate("window.scrollTo(0,0)")
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1
    pg.screenshot(path=os.path.join(OUT, "practice_flow_390.png"))

    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.evaluate("window.scrollTo(0,0)")
    pg.wait_for_timeout(250)
    assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1
    pg.screenshot(path=os.path.join(OUT, "practice_flow_1280.png"))

    assert errors == [], errors
    browser.close()
print("practice flow ok: 2 intents, 17 inline parts, direct session/speaking/writing routes")
