"""Phase 100: the Week plan and Today show the active week block.

The card names the pair of skills working now and the one that comes next,
lists the next four sessions with their real day and unit, and Today carries
the same block line.
"""
import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TODAY = WD[datetime.now().weekday()]
DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
TODAY_NUM = DAY_NUM[TODAY.lower()]
OTHER = [d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") if d != TODAY.lower()]


def seed(pg, days, per=1):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(
        """([schedule, per]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: schedule.map(s => s.day),
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.errs = [];
            D.log = [];
            D.sessionOffset = 0;
            D.settings.schedule = schedule;
            D.settings.rotationMode = 'by-part';
            D.settings.itemsPerSession = per;
            save();
            refreshAll();
        }""",
        [schedule, per],
    )
    pg.wait_for_timeout(300)


READ_JS = """() => ({
    block: (document.getElementById('wpWeekBlock') || {}).textContent || '',
    blockShown: document.getElementById('wpWeekBlock')
        ? getComputedStyle(document.getElementById('wpWeekBlock')).display !== 'none' : false,
    rows: [...document.querySelectorAll('#wpQueuePreview .wp-next')].map(r => ({
        day: r.dataset.day,
        units: (r.dataset.units || '').split(',').filter(Boolean),
        text: r.textContent.trim(),
    })),
    expected: planNextSessions(4).map(s => ({
        day: s.day,
        units: s.units.map(u => u.skill + ':' + u.value),
        text: s.units.map(queueUnitLabel).join(' · '),
    })),
    todayMode: (document.querySelector('#todaySession .ts-mode') || {}).textContent || '',
    todayText: (document.getElementById('todaySession') || {}).innerText || '',
    todaySkill: (() => {
        const sl = buildWeeklyPlan(D).slots.find(s => s.day === planTodayLabel());
        if (!sl) return null;
        return {type: sl.type, units: (sl.units || []).map(u => u.skill)};
    })(),
    cardMode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
})"""


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

    # 1. Two days: the active pair and the next one, with skill names.
    seed(pg, [TODAY.lower(), OTHER[0]], per=1)
    state = pg.evaluate(READ_JS)
    assert state["blockShown"], f"the week block line is hidden: {state}"
    block = state["block"]
    assert "This week:" in block and "next week:" in block, (
        f"the block line is not clear: {block!r}"
    )
    for skill in ("Reading & UoE", "Listening", "Writing", "Speaking"):
        assert skill in block, f"{skill} missing from the block line: {block!r}"
    assert block.index("Reading & UoE") < block.index("Listening") < block.index("Writing") < block.index("Speaking"), (
        f"the block line does not name the current pair then the next: {block!r}"
    )
    OUT["1_block_two_days"] = block

    # 2. The next four sessions carry real day + unit, in plan order.
    assert len(state["rows"]) == 4, f"the card does not show four sessions: {state['rows']}"
    for row, expected in zip(state["rows"], state["expected"]):
        assert row["day"] == expected["day"], (
            f"session day drifted from the plan: {row} vs {expected}"
        )
        assert row["units"] == expected["units"], (
            f"session units drifted from the plan: {row} vs {expected}"
        )
        day_name = pg.evaluate("(d) => planDayLabel(d) || d", row["day"])
        assert row["text"] == f"{day_name} · {expected['text']}", (
            f"the row does not show day and unit: {row['text']!r}"
        )
    labels = [r["text"].split(" · ", 1)[1] for r in state["rows"]]
    assert labels == [
        "Reading part 1", "Listening part 1", "Writing essay", "Speaking part 1",
    ], f"the next four sessions are not the week blocks: {labels}"
    OUT["2_next_four"] = state["rows"]

    # 3. The active block lives in PLAN only; Today names the session it shows.
    assert state["todayMode"], f"Today has no session line: {state}"
    assert state["todaySkill"], f"Today has no plan row: {state}"
    pair = block.split(" — next week:")[0]
    assert pair not in state["todayMode"], (
        f"Today still repeats the week block: {state['todayMode']!r} vs {pair!r}"
    )
    assert "This week:" not in state["todayText"], (
        f"Today still shows the week block line: {state['todayText']!r}"
    )
    assert "next week:" not in state["todayText"].lower(), (
        f"Today still shows next week's block: {state['todayText']!r}"
    )
    assert state["cardMode"] and state["cardMode"].startswith(pair), (
        f"What comes next lost the block line: {state['cardMode']!r}"
    )
    skill = state["todaySkill"]["units"][0] if state["todaySkill"]["units"] else state["todaySkill"]["type"]
    skill_word = {"rue": "Reading", "l": "Listening", "w": "Writing", "sp": "Speaking", "ue": "Reading"}[skill]
    assert skill_word in state["todayMode"], (
        f"Today does not name its own skill: {state['todayMode']!r} (want {skill_word})"
    )
    OUT["3_today_block"] = {"today": state["todayMode"], "card": state["cardMode"]}

    # 4. More than two days: the line lists every real day with its skill.
    seed(pg, ["mon", "wed", "fri"], per=1)
    three = pg.evaluate(READ_JS)
    expected_days = "Monday · Reading & UoE, Wednesday · Listening, Friday · Reading & UoE"
    assert expected_days in three["block"], (
        f"the block line does not list the schedule days: {three['block']!r}"
    )
    assert "next week: Writing + Speaking" in three["block"], three["block"]
    OUT["4_three_days"] = three["block"]

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
