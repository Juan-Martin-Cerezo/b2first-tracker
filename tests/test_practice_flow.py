"""Practice hub acceptance: two intents, inline parts, direct routes.

Contract:
  1. Practice shows exactly two intents: Full mock and Practise by part.
  2. The old Library card is not visible in Practice.
  3. The part chooser is inline: 17 rows, one button each, no extra actions.
  4. Reading/Listening part -> Session. Writing part -> Contents + corrector CTA.
     Speaking part -> Speaking exam overlay.
  5. Recent practice block is absent in EN and ES; progress charts are not shown in Practice.
  6. 390x844 / 1280x800: .practice-shell matches Today/Progress content edges (±2 px),
     no horizontal overflow, no page errors.
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
    assert pg.evaluate("document.getElementById('practiceOverview') === null")
    assert pg.evaluate("document.querySelectorAll('#practiceOverview .practice-progress-card').length") == 0
    assert pg.evaluate("document.querySelector('.practice-recent') === null")
    no_recent_js = (
        "Array.from(document.querySelectorAll('#v-practice *')).every(el => {"
        " const t = (el.textContent || '').trim();"
        " return !t.includes('Recent practice') && !t.includes('Práctica reciente');"
        "})"
    )
    assert pg.evaluate(no_recent_js), "Recent practice copy still present in EN"
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    assert pg.evaluate("document.getElementById('practiceOverview') === null")
    assert pg.evaluate("document.querySelector('.practice-recent') === null")
    assert pg.evaluate(no_recent_js), "Recent practice copy still present in ES"
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)
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

    # Mobile and desktop width parity + overflow + screenshots.
    def measure_shell_edges(label, width, height):
        pg.set_viewport_size({"width": width, "height": height})
        pg.evaluate("window.scrollTo(0,0)")
        pg.click("nav button[data-view='hoy']")
        pg.wait_for_timeout(250)
        hoy = pg.evaluate("""() => {
            const col = document.querySelector('#v-hoy .today-shell') || document.querySelector('main');
            const r = col.getBoundingClientRect();
            return {left: r.left, right: r.right, width: r.width};
        }""")
        pg.click("nav button[data-view='prog']")
        pg.wait_for_timeout(250)
        prog = pg.evaluate("""() => {
            const col = document.querySelector('#v-prog .card') || document.querySelector('#v-prog');
            const r = col.getBoundingClientRect();
            return {left: r.left, right: r.right, width: r.width};
        }""")
        pg.click("nav button[data-view='practice']")
        pg.wait_for_timeout(250)
        prac = pg.evaluate("""() => {
            const el = document.querySelector('#v-practice .practice-shell');
            const r = el.getBoundingClientRect();
            return {
                left: r.left, right: r.right, width: r.width,
                scrollWidth: document.documentElement.scrollWidth,
                innerWidth: window.innerWidth,
            };
        }""")
        assert prac["scrollWidth"] <= prac["innerWidth"] + 1, (
            f"{label}: horizontal overflow {prac['scrollWidth']} > {prac['innerWidth']}"
        )
        d_hoy_l = abs(prac["left"] - hoy["left"])
        d_hoy_r = abs(prac["right"] - hoy["right"])
        d_prog_l = abs(prac["left"] - prog["left"])
        d_prog_r = abs(prac["right"] - prog["right"])
        print(
            f"edges {label} ({width}x{height}): "
            f"practice=[{prac['left']:.1f},{prac['right']:.1f}] w={prac['width']:.1f} | "
            f"today=[{hoy['left']:.1f},{hoy['right']:.1f}] dL={d_hoy_l:.1f} dR={d_hoy_r:.1f} | "
            f"progress=[{prog['left']:.1f},{prog['right']:.1f}] dL={d_prog_l:.1f} dR={d_prog_r:.1f} | "
            f"scroll={prac['scrollWidth']}/{prac['innerWidth']}"
        )
        assert d_hoy_l <= 2 and d_hoy_r <= 2, (
            f"{label}: .practice-shell vs Today edge delta ({d_hoy_l:.1f}, {d_hoy_r:.1f}) > 2px"
        )
        assert d_prog_l <= 2 and d_prog_r <= 2, (
            f"{label}: .practice-shell vs Progress edge delta ({d_prog_l:.1f}, {d_prog_r:.1f}) > 2px"
        )

    measure_shell_edges("mobile", 390, 844)
    pg.screenshot(path=os.path.join(OUT, "practice_flow_390.png"))
    pg.screenshot(path=os.path.join(OUT, "practice_width_390.png"))

    measure_shell_edges("desktop", 1280, 800)
    pg.screenshot(path=os.path.join(OUT, "practice_width_1280.png"))
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    assert pg.evaluate(no_recent_js), "Recent practice copy present in ES at 1280"
    pg.screenshot(path=os.path.join(OUT, "practice_no_recent_es_1280.png"))
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(150)

    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.evaluate("window.scrollTo(0,0)")
    pg.wait_for_timeout(200)
    assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1
    pg.screenshot(path=os.path.join(OUT, "practice_flow_1280.png"))

    assert errors == [], errors
    browser.close()
print("practice flow ok: 2 intents, 17 inline parts, direct session/speaking/writing routes")
