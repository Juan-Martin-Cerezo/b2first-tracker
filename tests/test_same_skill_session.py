"""Phase 97: a session is always a block of units from ONE skill.

Two exercises in the same session are two Reading parts, two Listening parts,
two writing genres or two Speaking parts — never a mix. Per=1 keeps the Phase 96
interleaved order; per=3 wraps each skill's own cycle instead of borrowing from
another skill. The duration is the exact sum of the units.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

SESSIONS_JS = """([days, per, start, count]) => rotationQueueSessions(
    days, per, start, count
).map(s => ({
    day: s.day,
    units: s.units.map(queueUnitLabel),
    skills: [...new Set(s.units.map(u => u.skill))],
    min: s.min,
}))"""


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    pg.evaluate(
        """() => {
            D.sessionOffset = 0;
            D.settings.rueCycle = [1, 2, 3, 4, 5, 6, 7];
            D.settings.lCycle = [1, 2, 3, 4];
            D.settings.spCycle = [1, 2, 3, 4];
            D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
            save();
        }"""
    )

    slot_min = pg.evaluate("Math.max(1, Number(D.settings.slotMin) || 45)")

    # 1. itemsPerSession=2: the first eight sessions, one skill each.
    pairs = pg.evaluate(SESSIONS_JS, [["mon", "fri"], 2, 0, 8])
    assert [s["units"] for s in pairs] == [
        ["Reading part 1", "Reading part 2"],
        ["Listening part 1", "Listening part 2"],
        ["Writing essay", "Writing article"],
        ["Speaking part 1", "Speaking part 2"],
        ["Reading part 3", "Reading part 4"],
        ["Listening part 3", "Listening part 4"],
        ["Writing report", "Writing review"],
        ["Speaking part 3", "Speaking part 4"],
    ], f"the per=2 session sequence is wrong: {pairs}"
    for s in pairs:
        assert len(s["skills"]) == 1, f"a session mixed skills: {s}"
        assert s["min"] == slot_min * len(s["units"]), (
            f"the duration is not the sum of the units: {s}"
        )
    OUT["per2"] = pairs

    # 2. itemsPerSession=3: same invariant, including each skill's own wrap.
    triples = pg.evaluate(SESSIONS_JS, [["mon", "fri"], 3, 0, 8])
    assert [s["units"] for s in triples] == [
        ["Reading part 1", "Reading part 2", "Reading part 3"],
        ["Listening part 1", "Listening part 2", "Listening part 3"],
        ["Writing essay", "Writing article", "Writing report"],
        ["Speaking part 1", "Speaking part 2", "Speaking part 3"],
        ["Reading part 4", "Reading part 5", "Reading part 6"],
        ["Listening part 4", "Listening part 1", "Listening part 2"],
        ["Writing review", "Writing email", "Writing essay"],
        ["Speaking part 4", "Speaking part 1", "Speaking part 2"],
    ], f"the per=3 session sequence is wrong (wrap included): {triples}"
    for s in triples:
        assert len(s["skills"]) == 1, f"a per=3 session mixed skills: {s}"
        assert s["min"] == slot_min * len(s["units"]), (
            f"the per=3 duration is not the sum of the units: {s}"
        )
    OUT["per3"] = triples

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
