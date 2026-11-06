"""Phase 97: the rotation card no longer explains laps or internal cycles.

The position still advances with the logged work: each logged unit moves the
upcoming queue one session forward, and the card shows that real next item.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"

SEED = """(count) => {
    D.log = [];
    for (let i = 0; i < count; i++) {
        D.log.push({date: '2026-10-0' + ((i % 9) + 1), type: 'ue', part: (i % 4) + 1,
                    correct: 6, total: 8, min: 10});
    }
    D.sessionOffset = 0;
    D.settings.itemsPerSession = 1;
    D.settings.rueCycle = [1, 2, 3, 4];
    save();
    renderPlan();
}"""

READ = """() => {
    const first = document.querySelector('#planUpcomingPreview .up-row .badge');
    return {
        mode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
        first: first ? first.textContent.trim() : null,
        lapEls: document.querySelectorAll('#rotationCardBody .rot-lap').length,
        skillEls: document.querySelectorAll('#rotationCardBody .rot-skill').length,
        text: document.getElementById('rotationCard').innerText,
    };
}"""

out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(300)

    expected = {
        0: "Reading part 1",
        1: "Listening part 1",
        2: "Writing essay",
        3: "Speaking part 1",
        4: "Reading part 2",
    }
    seen = {}
    for count, first in expected.items():
        pg.evaluate(SEED, count)
        pg.wait_for_timeout(150)
        state = pg.evaluate(READ)
        assert state["first"] == first, (
            f"{count} logged units should start at {first!r}: {state['first']!r}"
        )
        assert state["mode"].strip() == "One exercise per session.", state["mode"]
        assert state["lapEls"] == 0, "the lap line is still rendered"
        assert state["skillEls"] == 0, "the per-skill cycle blocks are still rendered"
        assert "lap " not in state["text"].lower(), (
            f"lap copy leaked into the card: {state['text']!r}"
        )
        seen[str(count)] = state["first"]
    out["positions"] = seen

    # The mode line is bilingual and still free of cycle jargon.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    spanish = pg.evaluate(READ)
    assert spanish["mode"].strip() == "Un ejercicio por sesión.", spanish["mode"]
    assert "vuelta" not in spanish["text"].lower(), spanish["text"]
    out["spanish"] = spanish["mode"]

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
