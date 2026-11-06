"""Phase 97: "What comes next" shows the queue the user actually built.

The card no longer explains internal cycles: it names the active mode in plain
language and lists the next real units with the day of their session. Editing a
cycle repaints the list at once, a manual writing override is named, and an
empty log honestly starts at the first unit.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"

STATE_JS = """() => {
    const rows = [...document.querySelectorAll('#planUpcomingPreview .up-row')];
    return {
        mode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
        override: (document.querySelector('#rotationCardBody .rot-override') || {}).textContent || '',
        items: rows.map(r => ((r.querySelector('.badge') || {}).textContent || '').trim()),
        days: rows.map(r => r.dataset.day),
        hintExists: !!document.getElementById('rotationHint'),
        cardText: document.getElementById('rotationCard').innerText,
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

    # 0. The default rotation mode is still by-part.
    mode = pg.evaluate(
        "() => ({mode: D.settings.rotationMode,"
        " select: document.getElementById('wpRotationMode').value})"
    )
    assert mode == {"mode": "by-part", "select": "by-part"}, (
        f"the card is not on the default mode: {mode}"
    )
    out["0_default_mode"] = mode

    # Seed a known history: two R&UE parts in a four-item cycle.
    pg.evaluate(
        """() => {
        D.log = [
            {date: '2026-10-01', type: 'ue', part: 1, correct: 6, total: 8, min: 10},
            {date: '2026-10-02', type: 'ue', part: 2, correct: 6, total: 8, min: 10},
        ];
        D.sessionOffset = 0;
        D.settings.itemsPerSession = 1;
        D.settings.rueCycle = [1, 2, 3, 4];
        D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
        D.settings.lCycle = [1, 2, 3, 4];
        D.settings.spCycle = [1, 2, 3, 4];
        delete D.weekOverrides.w;
        save(); renderPlan();
    }"""
    )
    pg.wait_for_timeout(250)

    # 1. The upcoming list starts exactly where the log left the queue: two
    #    logged units put the next session on Writing, and the list is real.
    state = pg.evaluate(STATE_JS)
    assert state["mode"].strip() == "One exercise per session.", (
        f"the mode line is not plain language: {state['mode']!r}"
    )
    assert state["items"][:2] == ["Writing essay", "Speaking part 1"], (
        f"the upcoming queue does not follow the log: {state['items']}"
    )
    assert len(state["items"]) == 6, f"the card did not list six units: {state['items']}"
    out["1_seeded"] = {"mode": state["mode"], "items": state["items"]}

    # 2. The card no longer explains cycles, laps or internal positions.
    assert not state["hintExists"], "the old cycle hint is still in the card"
    lowered = state["cardText"].lower()
    for jargon in ("lap ", "one item per session", "component by component", "4-step"):
        assert jargon not in lowered, f"internal cycle copy leaked: {jargon!r} in {state['cardText']!r}"

    # 3. Editing the R&UE cycle repaints the real next unit.
    pg.evaluate("D.log = []; D.settings.rueCycle = [1,2,3,4]; save(); renderPlan();")
    pg.wait_for_timeout(200)
    pg.fill("#pRueCycle", "4,1,2,3")
    pg.evaluate("onCycleCommit()")
    pg.wait_for_timeout(250)
    changed = pg.evaluate(STATE_JS)
    assert changed["items"][0] == "Reading part 4", (
        f"the next unit did not follow the new cycle: {changed['items']}"
    )
    stored = pg.evaluate("D.settings.rueCycle")
    assert stored == [4, 1, 2, 3], f"the new cycle was not saved: {stored}"
    out["3_cycle_change"] = {"items": changed["items"], "stored": stored}

    # 4. A manual writing override is named in the card.
    pg.evaluate("D.weekOverrides.w = 'Report'; save(); renderRotationCard();")
    pg.wait_for_timeout(150)
    hinted = pg.evaluate(STATE_JS)
    assert "Manual override: Report" in hinted["override"], (
        f"the manual override is not named: {hinted['override']!r}"
    )
    out["4_override"] = hinted["override"]

    # 5. Without history the card is honest about the start.
    pg.evaluate(
        "D.log = []; D.settings.rueCycle = [1,2,3,4];"
        " delete D.weekOverrides.w; save(); renderPlan();"
    )
    pg.wait_for_timeout(250)
    empty = pg.evaluate(STATE_JS)
    assert empty["items"][0] == "Reading part 1", (
        f"the first item is not announced: {empty['items']}"
    )
    assert empty["mode"].strip() == "One exercise per session.", empty["mode"]
    assert empty["override"] == "", f"the override did not clear: {empty['override']!r}"
    out["5_no_history"] = {"items": empty["items"], "mode": empty["mode"]}

    # 6. With two exercises per session the preview shows two units of the
    #    same skill, never one of each.
    queue = pg.evaluate(
        """() => {
            D.log = [];
            D.settings.itemsPerSession = 2;
            save();
            renderWeeklyPlan();
            renderRotationCard();
            const sel = document.getElementById('wpItemsPerSession');
            return {
                value: sel.value,
                options: [...sel.options].map(o => o.value),
                preview: document.getElementById('wpQueuePreview').textContent,
                mode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
                items: [...document.querySelectorAll('#planUpcomingPreview .up-row .badge')]
                    .map(el => el.textContent.trim()),
            };
        }"""
    )
    pg.wait_for_timeout(200)
    assert queue["value"] == "2", f"the select did not reflect itemsPerSession: {queue}"
    assert queue["options"] == ["1", "2", "3", "4"], f"the select options are wrong: {queue}"
    assert "Next up:" in queue["preview"], f"the preview lost its label: {queue}"
    labels = queue["preview"].split("Next up:")[1].strip().split(" · ")
    assert labels == [
        "Reading part 1",
        "Reading part 2",
        "Listening part 1",
        "Listening part 2",
        "Writing essay",
        "Writing article",
    ], f"the preview is not the next six units of the real sessions: {labels}"
    assert "two" in queue["mode"].lower() and "Reading" in queue["mode"], (
        f"the mode line does not describe two same-skill exercises: {queue['mode']!r}"
    )
    assert queue["items"][:2] == ["Reading part 1", "Reading part 2"], queue["items"]
    for jargon in ("cycle", "queue", "parallel"):
        assert jargon not in queue["preview"].lower(), (
            f"internal jargon leaked into the preview: {queue['preview']!r}"
        )
    out["6_queue_preview"] = queue

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
