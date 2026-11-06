"""Phase 52.43: once every unit of the day's session is logged, TODAY shows the
session's planned minutes against the minutes really practised.

Both numbers come from the app's own data: the planned minutes are the ones the
plan gave each unit (the row's `unit.min`, else the session table), and the real
minutes are the `min` of the rows in D.log. The plan cursor moves as soon as the
session is logged, so the completed session is rebuilt from today's rows — the
test seeds D.log exactly like the studios would and never mirrors the planner in
Python.

A half session must show nothing; a full one must show the two sums; a repeat
adds real minutes but not planned ones; another day's rows do not count.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

ALL_DAYS = [
    {"day": 1, "time": "15:30"},  # Mon
    {"day": 2, "time": "13:00"},  # Tue
    {"day": 3, "time": "10:00"},  # Wed
    {"day": 4, "time": "18:00"},  # Thu
    {"day": 5, "time": "17:00"},  # Fri
    {"day": 6, "time": "11:00"},  # Sat
    {"day": 0, "time": "09:00"},  # Sun
]

ROW_TYPE = {"rue": "ue", "l": "lp", "w": "w", "sp": "sp"}

SEED = """([schedule, per]) => {
    D.profile = {
        examDate: null, targetGrade: 'B',
        skills: {rue: 3, w: 3, l: 3, sp: 3},
        hoursWeek: 6, days: [0, 1, 2, 3, 4, 5, 6],
        struggles: [], strugglesDeclared: [],
    };
    D.diag = null;
    D.log = [];
    D.errs = [];
    D.sessionOffset = 0;
    D.settings.schedule = schedule;
    D.settings.rotationMode = 'by-part';
    D.settings.itemsPerSession = per;
    save();
    refreshAll();
}"""

PLAN_JS = """() => {
    const plan = buildWeeklyPlan(D);
    const today = planTodayLabel();
    const slot = plan.slots.find(sl => sl.day === today);
    if (!slot || !slot.units || !slot.units.length) return null;
    return {
        day: slot.day,
        per: normalizeItemsPerSession(D.settings.itemsPerSession),
        units: slot.units.map(u => ({
            skill: u.skill,
            value: String(u.value),
            min: Number(u.min),
        })),
    };
}"""

LOG_JS = """(rows) => {
    D.log = rows.map((r, i) => Object.assign({created_at: 1000 + i}, r));
    save();
    refreshAll();
}"""

READ_JS = """() => {
    const el = document.querySelector('#todaySession .ts-summary');
    if (!el) return null;
    return {
        planned: Number(el.dataset.planned),
        real: Number(el.dataset.real),
        text: (el.textContent || '').trim(),
    };
}"""


def log_row(unit, date, real_min, tagged_min=None):
    row = {
        "type": ROW_TYPE[unit["skill"]],
        "date": date,
        "min": real_min,
    }
    if unit["skill"] == "w":
        row["kind"] = unit["value"]
    else:
        try:
            row["part"] = int(unit["value"])
        except ValueError:
            row["part"] = unit["value"]
    row["unit"] = {
        "skill": unit["skill"],
        "value": unit["value"],
        "min": unit["min"] if tagged_min is None else tagged_min,
    }
    return row


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(250)

    # Two units per session, so "all the units" is a real condition.
    pg.evaluate(SEED, [ALL_DAYS, 2])
    pg.wait_for_timeout(220)
    plan = pg.evaluate(PLAN_JS)
    assert plan is not None, "TODAY has no plan session to work with"
    assert len(plan["units"]) == 2, f"the seeded plan did not give two units: {plan}"
    units = plan["units"]
    planned_total = sum(u["min"] for u in units)
    assert planned_total > 0, f"the plan's units have no minutes: {units}"
    OUT["plan"] = plan

    today = pg.evaluate("() => today()")
    yesterday = pg.evaluate("() => dayKey(new Date(Date.now() - 86400000))")

    # 0. Nothing logged: no summary at all.
    pg.evaluate(LOG_JS, [])
    pg.wait_for_timeout(150)
    assert pg.evaluate(READ_JS) is None, "an empty log shows a finished session"
    OUT["0_empty"] = None

    # 1. Half the session: the summary must wait for every unit.
    half = [log_row(units[0], today, units[0]["min"] + 4)]
    pg.evaluate(LOG_JS, half)
    pg.wait_for_timeout(150)
    assert pg.evaluate(READ_JS) is None, (
        f"half a session already reads as done: {pg.evaluate(READ_JS)}"
    )

    # 2. Every unit logged: planned vs real, read from D.log.
    real_minutes = [u["min"] + 4 for u in units]
    full = [log_row(u, today, m) for u, m in zip(units, real_minutes)]
    pg.evaluate(LOG_JS, full)
    pg.wait_for_timeout(150)
    done = pg.evaluate(READ_JS)
    assert done is not None, "the completed session shows no summary"
    assert done["planned"] == planned_total, (
        f"planned minutes are {done['planned']}, the plan says {planned_total}: {done}"
    )
    assert done["real"] == sum(real_minutes), (
        f"real minutes are {done['real']}, the log says {sum(real_minutes)}: {done}"
    )
    assert str(planned_total) in done["text"] and str(sum(real_minutes)) in done["text"], (
        f"the summary does not read the two numbers: {done}"
    )
    OUT["2_done"] = done

    # 3. The real minutes come from the rows: editing one changes the sum.
    edited = [dict(r) for r in full]
    edited[0]["min"] = units[0]["min"] + 20
    pg.evaluate(LOG_JS, edited)
    pg.wait_for_timeout(150)
    changed = pg.evaluate(READ_JS)
    assert changed["real"] == sum(real_minutes) + 16, (
        f"the summary does not follow the rows' minutes: {changed}"
    )
    assert changed["planned"] == planned_total, (
        f"editing the real minutes changed the plan side: {changed}"
    )

    # 4. A repeat of a unit adds real minutes, never planned ones.
    repeat = full + [log_row(units[0], today, units[0]["min"])]
    pg.evaluate(LOG_JS, repeat)
    pg.wait_for_timeout(150)
    again = pg.evaluate(READ_JS)
    assert again["planned"] == planned_total, (
        f"repeating a unit inflated the planned minutes: {again}"
    )
    assert again["real"] == sum(real_minutes) + units[0]["min"], (
        f"repeating a unit did not add its real minutes: {again}"
    )

    # 5. Rows from another day do not complete today's session.
    other_day = [log_row(u, yesterday, m) for u, m in zip(units, real_minutes)]
    pg.evaluate(LOG_JS, other_day)
    pg.wait_for_timeout(150)
    assert pg.evaluate(READ_JS) is None, (
        f"yesterday's rows complete today's session: {pg.evaluate(READ_JS)}"
    )

    # 6. An extra session is off-plan and never counts.
    extra = [dict(r, extra=True) for r in full]
    pg.evaluate(LOG_JS, extra)
    pg.wait_for_timeout(150)
    assert pg.evaluate(READ_JS) is None, (
        f"extra practice counts as the plan's session: {pg.evaluate(READ_JS)}"
    )

    # 7. Planned minutes are the ones the unit was planned for, not a guess:
    #    a row tagged with other plan minutes moves the planned side.
    tagged = [dict(r, unit=dict(r["unit"], min=7)) for r in full]
    pg.evaluate(LOG_JS, tagged)
    pg.wait_for_timeout(150)
    tagged_done = pg.evaluate(READ_JS)
    assert tagged_done["planned"] == 14, (
        f"planned minutes ignore the unit tag: {tagged_done}"
    )

    # 8. Spanish reads from the second dictionary.
    pg.evaluate(LOG_JS, full)
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    spanish = pg.evaluate(READ_JS)
    expected_es = (
        f"Sesión completada: {planned_total} min planificados, "
        f"{sum(real_minutes)} min reales."
    )
    assert spanish["text"] == expected_es, (
        f"Spanish summary reads {spanish['text']!r}, expected {expected_es!r}"
    )
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
