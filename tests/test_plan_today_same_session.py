"""Phase 96: Today always shows exactly the plan row for today.

Both screens read buildWeeklyPlan(D), so the units, their order and the total
duration must be identical. Three schedules put today in three different
positions, and itemsPerSession=3 checks a multi-unit session on both sides.
"""
import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TODAY = WD[datetime.now().weekday()]
OTHER = [d for d in WD if d != TODAY]
DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}

READ_JS = """() => {
    const units = e => (e.dataset.units || '').split(',').filter(Boolean);
    const rows = sel => [...document.querySelectorAll(sel)].map(e => ({
        day: e.dataset.day,
        units: units(e),
        min: Number(e.dataset.min),
        type: e.dataset.type,
        title: ((e.querySelector('.wp-title, .ts-title') || {}).textContent || '')
            .replace(/^\\w{3} · /, ''),
    }));
    return {
        plan: rows('#wpRows .wp-row'),
        today: rows('#todaySession .ts-row:not(.ts-next-unit)'),
        rest: !!document.querySelector('#todaySession [data-rest]'),
    };
}"""


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
            D.settings.rueCycle = [1, 2, 3, 4, 5, 6, 7];
            D.settings.lCycle = [1, 2, 3, 4];
            D.settings.spCycle = [1, 2, 3, 4];
            D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
            save();
            refreshAll();
        }""",
        [schedule, per],
    )
    pg.wait_for_timeout(250)


def same_as_plan(pg):
    state = pg.evaluate(READ_JS)
    plan_today = [r for r in state["plan"] if r["day"] == TODAY]
    assert state["today"], f"Today rendered no session: {state}"
    assert not state["rest"], f"Today is a rest day: {state}"
    assert len(plan_today) == 1, f"the plan has no single row for today: {state['plan']}"
    assert len(state["today"]) == 1, f"Today rendered more than one session: {state['today']}"
    today_row = state["today"][0]
    plan_row = plan_today[0]
    # The header format is Today's own (day · units · duration), but the
    # session it names must still be exactly the plan's row.
    for field in ("day", "units", "min", "type"):
        assert today_row[field] == plan_row[field], (
            f"Today and plan disagree on {field}: {today_row} vs {plan_row}"
        )
    return today_row, plan_row


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
    pg.wait_for_timeout(250)

    today_l = TODAY.lower()
    other_l = [d.lower() for d in OTHER]

    # 1-3. Today first, second and third in the schedule: the row must match
    #      the plan every time, including the units and the duration.
    cases = [
        [today_l, other_l[0]],
        [other_l[0], today_l],
        [other_l[0], other_l[1], today_l],
    ]
    seen = []
    for days in cases:
        seed(pg, days, per=1)
        row, plan_row = same_as_plan(pg)
        assert len(row["units"]) == 1, f"one unit per session expected: {row}"
        assert row["units"][0].split(":")[0] in ("rue", "l", "w", "sp"), row
        seen.append(row)
    assert len({tuple(r["units"]) for r in seen}) >= 1, seen
    OUT["1_three_positions"] = seen

    # 4. itemsPerSession=3: both screens show the three units in order.
    seed(pg, [other_l[0], today_l], per=3)
    multi, plan_multi_row = same_as_plan(pg)
    assert len(multi["units"]) == 3, f"Today did not show three units: {multi}"
    assert len({u.split(":")[0] for u in multi["units"]}) == 1, (
        f"a session mixed skills: {multi}"
    )
    expected_min = pg.evaluate(
        """(units) => units.reduce((total, u) => {
            const parts = u.split(':');
            const skill = parts[0], value = parts[1];
            return total + (skill === 'w' ? UNIT_MIN.w[value] : UNIT_MIN[skill][Number(value)]);
        }, 0)""",
        multi["units"],
    )
    assert multi["min"] == expected_min, (
        f"the total duration is not the table sum of the units: {multi} (want {expected_min})"
    )
    assert " + " in multi["title"], (
        f"the single card does not list the units on one line: {multi['title']!r}"
    )
    assert "1)" in plan_multi_row["title"] and "3)" in plan_multi_row["title"], (
        f"the plan row does not number the units in order: {plan_multi_row['title']!r}"
    )
    plan_multi = pg.evaluate(READ_JS)["plan"]
    assert any(r["day"] == TODAY and len(r["units"]) == 3 for r in plan_multi), plan_multi
    OUT["2_three_units"] = multi

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
