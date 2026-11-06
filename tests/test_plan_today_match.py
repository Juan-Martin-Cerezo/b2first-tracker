"""Phase 86: PLAN and TODAY describe the same session.

buildWeeklyPlan(D) is the only selector. This suite seeds a profile whose
chosen days include today (and then a day that does not) and checks that the
TODAY block is literally the plan row for today: same title, same parts, same
duration, same order. A non-zero sessionOffset must move both sides together.
"""
import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TODAY = WD[datetime.now().weekday()]
TODAY_L = TODAY.lower()
OTHER = WD[(datetime.now().weekday() + 1) % 7]
OTHER_L = OTHER.lower()

READ_JS = """() => {
    const strip = t => t.replace(/^\\w{3} · /, '');
    const plan = [...document.querySelectorAll('#wpRows .wp-row')].map(e => ({
        day: e.dataset.day,
        type: e.dataset.type,
        parts: e.dataset.parts || '',
        units: e.dataset.units || '',
        min: Number(e.dataset.min),
        title: strip((e.querySelector('.wp-title') || {}).textContent || ''),
    }));
    const today = [...document.querySelectorAll('#todaySession .ts-row:not(.ts-next-unit)')].map(e => ({
        day: e.dataset.day,
        type: e.dataset.type,
        parts: e.dataset.parts || '',
        units: e.dataset.units || '',
        min: Number(e.dataset.min),
        title: strip((e.querySelector('.ts-title') || {}).textContent || ''),
    }));
    return {
        plan: plan,
        today: today,
        rest: !!document.querySelector('#todaySession [data-rest]'),
        todayText: document.getElementById('todaySession').innerText,
    };
}"""


DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}


def seed(pg, days, offset=0, hours=4):
    """Seed the profile and the session schedule (the plan's real source)."""
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(
        """([days, offset, hours, schedule]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: hours, days: days,
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.log = [];
            D.errs = [];
            D.sessionOffset = offset;
            D.settings.schedule = schedule;
            D.settings.rotationMode = 'by-part';
            save();
            refreshAll();
        }""",
        [days, offset, hours, schedule],
    )
    pg.wait_for_timeout(250)


def shape(rows):
    return [(r["title"], r["parts"], r["units"], r["min"], r["type"]) for r in rows]


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

    # 1. Today is a chosen day: TODAY is exactly the plan row(s) for today.
    seed(pg, [TODAY_L], offset=0)
    state = pg.evaluate(READ_JS)
    plan_today = [r for r in state["plan"] if r["day"] == TODAY]
    assert state["today"], f"TODAY did not render today's plan row: {state}"
    assert not state["rest"], f"TODAY claims a rest day on a chosen day: {state}"
    assert shape(state["today"]) == shape(plan_today), (
        "TODAY and PLAN disagree on today's session:\n"
        f"today={shape(state['today'])}\nplan={shape(plan_today)}"
    )
    assert all(r["day"] == TODAY for r in plan_today)
    OUT["1_today_matches_plan"] = shape(state["today"])

    # 2. A day that is not among the chosen days is a rest day on both sides.
    seed(pg, [OTHER_L], offset=0)
    rest = pg.evaluate(READ_JS)
    plan_other = [r for r in rest["plan"] if r["day"] == TODAY]
    assert rest["rest"] is True, f"TODAY did not report a rest day: {rest}"
    assert "rest day" in rest["todayText"].lower(), (
        f"TODAY does not say 'rest day': {rest['todayText']!r}"
    )
    assert not rest["today"], f"TODAY invented a session on a rest day: {rest}"
    assert plan_other == [], f"PLAN invented a row for today: {plan_other}"
    assert all(r["day"] == OTHER for r in rest["plan"]), (
        f"PLAN put slots outside the chosen day: {rest['plan']}"
    )
    OUT["2_rest_day"] = rest["todayText"]

    # 3. A non-zero sessionOffset still keeps both sides identical, and it
    #    really moves the rotation (the order changes). Two scheduled days are
    #    needed for the rotation to be observable.
    seed(pg, [TODAY_L, OTHER_L], offset=0)
    base = pg.evaluate(READ_JS)
    seed(pg, [TODAY_L, OTHER_L], offset=1)
    shifted = pg.evaluate(READ_JS)
    plan_shifted = [r for r in shifted["plan"] if r["day"] == TODAY]
    assert shape(shifted["today"]) == shape(plan_shifted), (
        "TODAY and PLAN disagree with sessionOffset=1:\n"
        f"today={shape(shifted['today'])}\nplan={shape(plan_shifted)}"
    )
    assert shape(shifted["today"]) != shape(base["today"]), (
        "sessionOffset did not move the rotation on either side"
    )
    OUT["3_offset"] = {
        "base": shape(base["today"]),
        "offset_1": shape(shifted["today"]),
    }

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
