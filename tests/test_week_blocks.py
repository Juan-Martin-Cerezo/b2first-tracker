"""Phase 100: with few days, skills are split by week blocks.

Week A (1st, 3rd, ...) is Reading & UoE + Listening; week B (2nd, 4th, ...) is
Writing + Speaking. The days of a week split the pair in order, a session never
mixes skills, and each skill's position continues across weeks. The starting
week is anchored to the work already logged, never to the calendar.
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

    # 1. Two days, one exercise: the two weeks alternate the pairs and then
    #    start again, continuing each skill where it was.
    first = pg.evaluate(SESSIONS_JS, [["mon", "fri"], 1, 0, 4])
    assert [s["units"] for s in first] == [
        ["Reading part 1"],
        ["Listening part 1"],
        ["Writing essay"],
        ["Speaking part 1"],
    ], f"the first week block is wrong: {first}"
    assert [s["day"] for s in first] == ["mon", "fri", "mon", "fri"], first
    second = pg.evaluate(SESSIONS_JS, [["mon", "fri"], 1, 4, 4])
    assert [s["units"] for s in second] == [
        ["Reading part 2"],
        ["Listening part 2"],
        ["Writing article"],
        ["Speaking part 2"],
    ], f"the second week block did not continue the positions: {second}"
    OUT["1_two_days"] = {"first": first, "second": second}

    # 2. The four sessions of one turn cover the four skills exactly once.
    skills = [s["skills"][0] for s in first]
    assert sorted(skills) == ["l", "rue", "sp", "w"], (
        f"one turn does not cover the four skills once: {skills}"
    )
    assert all(len(s["skills"]) == 1 for s in first), (
        f"a session mixed skills: {first}"
    )
    OUT["2_four_skills"] = skills

    # 3. Three days: day 1 -> first skill, day 2 -> second, day 3 -> first
    #    again, and the next week starts the other pair.
    three = pg.evaluate(SESSIONS_JS, [["mon", "wed", "fri"], 1, 0, 6])
    assert [s["units"] for s in three] == [
        ["Reading part 1"],
        ["Listening part 1"],
        ["Reading part 2"],
        ["Writing essay"],
        ["Speaking part 1"],
        ["Writing article"],
    ], f"the three-day split is wrong: {three}"
    assert all(len(s["skills"]) == 1 for s in three), (
        f"a three-day session mixed skills: {three}"
    )
    OUT["3_three_days"] = three

    # 4. itemsPerSession keeps every unit inside the session's skill.
    pairs = pg.evaluate(SESSIONS_JS, [["mon", "wed", "fri"], 2, 0, 6])
    for session in pairs:
        assert len(session["skills"]) == 1, (
            f"a multi-unit session mixed skills: {session}"
        )
    assert [s["units"] for s in pairs[:3]] == [
        ["Reading part 1", "Reading part 2"],
        ["Listening part 1", "Listening part 2"],
        ["Reading part 3", "Reading part 4"],
    ], f"the per=2 split is wrong: {pairs[:3]}"
    OUT["4_per_two"] = pairs

    # 5. The position never resets when a week changes: the second time week A
    #    comes round, Reading is at part 3, not part 1.
    reentered = pg.evaluate(SESSIONS_JS, [["mon", "fri"], 1, 8, 2])
    assert reentered[0]["units"] == ["Reading part 3"], (
        f"the skill position reset at the week change: {reentered}"
    )
    OUT["5_no_reset"] = reentered

    # 6. The logged work decides the block: three logged units put the next
    #    session on week B, and a refresh reads the same value.
    seeded = pg.evaluate(
        """() => {
            D.log = [
                {date: '2026-10-01', type: 'ue', part: 1, correct: 6, total: 8, min: 8},
                {date: '2026-10-02', type: 'lp', part: 1, correct: 6, total: 8, min: 10},
                {date: '2026-10-03', type: 'w', kind: 'Essay', score: 12, min: 40},
            ];
            D.settings.itemsPerSession = 1;
            save();
            return {start: planSessionStart(), units: planNextSessions(1)[0].units.map(queueUnitLabel)};
        }"""
    )
    assert seeded["start"] == 3, f"the logged work did not move the start: {seeded}"
    assert seeded["units"] == ["Speaking part 1"], (
        f"three logged units are not in week B: {seeded}"
    )
    again = pg.evaluate(
        "() => ({start: planSessionStart(), units: planNextSessions(1)[0].units.map(queueUnitLabel)})"
    )
    assert again == seeded, f"a refresh moved the block: {again} vs {seeded}"
    OUT["6_from_log"] = seeded

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
