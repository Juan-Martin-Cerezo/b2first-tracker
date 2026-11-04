"""Phase 84: the "What comes next" card explains the rotation.

A seeded log gives a known position; changing the cycle input repaints the card
at once; with no history the card says it starts at the first item instead of
inventing a position.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"

STATE_JS = """() => {
    const block = skill => {
        const el = document.querySelector(
            '#rotationCardBody .rot-skill[data-skill="' + skill + '"]'
        );
        if (!el) return null;
        return {
            text: el.innerText,
            current: (el.querySelector('.rot-chip.rot-cur') || {}).textContent || '',
            next: (el.querySelector('.rot-next') || {}).textContent || '',
            chips: [...el.querySelectorAll('.rot-chip')].map(c => c.textContent.trim()),
        };
    };
    return {
        rue: block('rue'), l: block('l'), w: block('w'), sp: block('sp'),
        hint: document.getElementById('rotationHint').innerText,
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

    # 0. The default rotation mode is the part-by-part behaviour this card
    #    explains; the selector is the only place that decides it.
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
        D.settings.rueCycle = [1, 2, 3, 4];
        D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
        D.settings.lCycle = [1, 2, 3, 4];
        D.settings.spCycle = [1, 2, 3, 4];
        delete D.weekOverrides.w;
        save(); renderPlan();
    }"""
    )
    pg.wait_for_timeout(250)

    # 1. Every skill has a block, with a current item, a concrete next item and
    #    the full cycle.
    state = pg.evaluate(STATE_JS)
    assert state["rue"] and state["l"] and state["w"] and state["sp"], (
        f"a skill block is missing: {state}"
    )
    assert "current: Part 2" in state["rue"]["text"], (
        f"the current position is not shown: {state['rue']}"
    )
    assert "next: Part 3" in state["rue"]["text"], (
        f"the next exercise is not shown: {state['rue']}"
    )
    assert state["rue"]["current"].strip() == "Part 2 · Open cloze", (
        f"the current cycle item is not highlighted: {state['rue']}"
    )
    assert len(state["rue"]["chips"]) == 4, (
        f"the full cycle is not shown: {state['rue']}"
    )
    out["1_seeded"] = state["rue"]

    # 2. The hint says how the rotation works and where the next item comes from.
    assert "rotation" in state["hint"].lower(), f"no rotation explanation: {state['hint']}"
    assert "Week" in state["hint"], f"the source week is not named: {state['hint']}"
    assert "in order" in state["hint"], f"the order is not explained: {state['hint']}"

    # 3. Editing the cycle repaints the card and changes the next item.
    pg.fill("#pRueCycle", "4,1,2,3")
    pg.wait_for_timeout(200)
    changed = pg.evaluate(STATE_JS)
    assert "next: Part 2" in changed["rue"]["text"], (
        f"the next item did not follow the new cycle: {changed['rue']}"
    )
    assert changed["rue"]["current"].strip() == "Part 1 · Multiple-choice cloze", (
        f"the current item did not follow the new cycle: {changed['rue']}"
    )
    stored = pg.evaluate("D.settings.rueCycle")
    assert stored == [4, 1, 2, 3], f"the new cycle was not saved: {stored}"
    out["3_cycle_change"] = {"card": changed["rue"], "stored": stored}

    # 4. A manual writing override is named in the explanation.
    pg.evaluate("D.weekOverrides.w = 'Report'; save(); renderRotationCard();")
    pg.wait_for_timeout(150)
    hinted = pg.evaluate(STATE_JS)
    assert "Manual override: Report" in hinted["hint"], (
        f"the manual override is not named: {hinted['hint']}"
    )
    out["4_override"] = hinted["hint"]

    # 5. Without matching history the card is honest about the start.
    pg.evaluate(
        "D.log = []; D.settings.rueCycle = [1,2,3,4];"
        " delete D.weekOverrides.w; save(); renderPlan();"
    )
    pg.wait_for_timeout(250)
    empty = pg.evaluate(STATE_JS)
    assert "starting at the first item" in empty["rue"]["text"], (
        f"no-history state is not explicit: {empty['rue']}"
    )
    assert "next: Part 1 · Multiple-choice cloze" in empty["rue"]["text"], (
        f"the first item is not announced: {empty['rue']}"
    )
    out["5_no_history"] = empty["rue"]

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
