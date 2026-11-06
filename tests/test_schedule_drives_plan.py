"""Phase 95: the session schedule is the only source of the study days.

The schedule card owns the days; profile.days only seeds it the first time.
This suite seeds a schedule of Mon 15:30, Wed 18:00 and Sat 10:00 while the
profile still says Mon-Fri, and checks that the Week plan and Today show exactly
those three days, with their hours. Adding, deleting and emptying the schedule
repaints both screens without a reload, and every rotation mode distributes its
slots over the schedule days.
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
NUM_DAY = {v: k for k, v in DAY_NUM.items()}

SCHEDULE = [
    {"day": 1, "time": "15:30"},
    {"day": 3, "time": "18:00"},
    {"day": 6, "time": "10:00"},
]

READ_JS = """() => {
    const rows = sel => [...document.querySelectorAll(sel)].map(e => ({
        day: e.dataset.day,
        time: e.dataset.time || '',
        title: (e.querySelector('.wp-title, .ts-title') || {}).textContent || '',
    }));
    return {
        plan: rows('#wpRows .wp-row'),
        today: rows('#todaySession .ts-row'),
        rest: !!document.querySelector('#todaySession [data-rest]'),
        todayText: document.getElementById('todaySession').innerText,
        weekText: document.getElementById('wpRows').innerText,
    };
}"""


def seed(pg, schedule, profile_days=None):
    pg.evaluate(
        """([schedule, profileDays]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: profileDays,
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.log = [];
            D.errs = [];
            D.sessionOffset = 0;
            D.settings.schedule = schedule;
            D.settings.rotationMode = 'by-part';
            D.settings.customPlan = {};
            save();
            refreshAll();
        }""",
        [schedule, profile_days or ["mon", "tue", "wed", "thu", "fri"]],
    )
    pg.wait_for_timeout(250)


def add_day(pg, day_num, time="20:00"):
    """Add a session through the card and point it at day_num."""
    before = pg.eval_on_selector_all(".sched-day-select", "els => els.map(e => +e.value)")
    pg.click("button:has-text('Add Session Day')")
    pg.wait_for_timeout(200)
    after = pg.eval_on_selector_all(".sched-day-select", "els => els.map(e => +e.value)")
    idx = next(i for i, v in enumerate(after) if v not in before)
    row = pg.locator(".sched-day-select").nth(idx)
    row.select_option(str(day_num))
    pg.locator(".sched-time-input").nth(idx).fill(time)
    pg.locator(".sched-time-input").nth(idx).dispatch_event("change")
    pg.wait_for_timeout(300)


def remove_day(pg, day_num):
    """Click the delete button of the row that holds day_num."""
    pg.evaluate(
        """(day) => {
            const rows = [...document.querySelectorAll('#scheduleRowsContainer .row')];
            const row = rows.find(r => +r.querySelector('.sched-day-select').value === day);
            if (row) row.querySelector('button').click();
        }""",
        day_num,
    )
    pg.wait_for_timeout(300)


def mode_days(pg, mode):
    return pg.evaluate(
        """(mode) => {
            D.settings.rotationMode = mode;
            save();
            refreshAll();
            return buildWeeklyPlan(D).slots.map(s => s.day);
        }""",
        mode,
    )


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

    # 1. The schedule wins over profile.days: exactly Mon/Wed/Sat, with hours.
    seed(pg, SCHEDULE)
    state = pg.evaluate(READ_JS)
    assert [r["day"] for r in state["plan"]] == ["Mon", "Wed", "Sat"], (
        f"the Week plan did not follow the schedule: {state['plan']}"
    )
    assert [r["time"] for r in state["plan"]] == ["15:30", "18:00", "10:00"], (
        f"the Week plan lost the session hours: {state['plan']}"
    )
    assert "Tue" not in [r["day"] for r in state["plan"]], (
        f"the Week plan invented a profile day: {state['plan']}"
    )
    titles = pg.evaluate("() => buildWeeklyPlan(D).slots.map(s => slotTitleText(s))")
    assert titles == [
        "Reading part 1 · 8 min",
        "Listening part 1 · 10 min",
        "Reading part 2 · 8 min",
    ], f"the queue did not follow the schedule days: {titles}"
    out_today = TODAY in ("Mon", "Wed", "Sat")
    if out_today:
        assert state["today"] and not state["rest"], (
            f"Today should be a session day ({TODAY}): {state}"
        )
        assert all(r["day"] == TODAY for r in state["today"]), state["today"]
    else:
        assert state["rest"], f"Today should be a rest day ({TODAY}): {state}"
        assert not state["today"], f"Today invented a session on a rest day: {state['today']}"
    OUT["1_schedule_wins"] = {"plan": state["plan"], "today": TODAY, "rest": state["rest"]}

    # 2. Once the schedule exists, changing profile.days does not move the plan.
    pg.evaluate(
        """() => {
            D.profile.days = ['thu', 'fri'];
            save();
            refreshAll();
        }"""
    )
    pg.wait_for_timeout(250)
    again = pg.evaluate(READ_JS)
    assert [r["day"] for r in again["plan"]] == ["Mon", "Wed", "Sat"], (
        f"profile.days still decides the plan: {again['plan']}"
    )
    OUT["2_profile_ignored"] = [r["day"] for r in again["plan"]]

    # 3. profile.days only seeds the schedule when no schedule exists yet.
    seeded = pg.evaluate(
        """() => {
            delete D.settings.schedule;
            D.profile.days = ['mon', 'tue'];
            save();
            refreshAll();
            return {
                schedule: D.settings.schedule,
                days: buildWeeklyPlan(D).slots.map(s => s.day),
            };
        }"""
    )
    assert seeded["days"] == ["Mon", "Tue"], f"profile.days did not seed the plan: {seeded}"
    assert len(seeded["schedule"]) == 2, f"the schedule was not seeded: {seeded}"
    OUT["3_seeded_from_profile"] = seeded

    # 4. Adding a day repaints the plan and Today without a reload.
    seed(pg, SCHEDULE)
    add_day(pg, DAY_NUM["thu"])
    added = pg.evaluate(READ_JS)
    assert [r["day"] for r in added["plan"]] == ["Mon", "Wed", "Thu", "Sat"], (
        f"the added day did not land in week order: {added['plan']}"
    )
    assert any(r["day"] == "Thu" and r["time"] == "20:00" for r in added["plan"]), (
        f"the added day lost its hour: {added['plan']}"
    )
    if TODAY == "Thu":
        assert added["today"] and not added["rest"], (
            f"Today did not pick up the added Thursday: {added}"
        )
    else:
        # Make today a scheduled day through the same card, then check Today.
        if not any(r["day"] == TODAY for r in added["plan"]):
            add_day(pg, DAY_NUM[TODAY.lower()], "19:00")
        live = pg.evaluate(READ_JS)
        assert live["today"] and not live["rest"], (
            f"Today did not react to the new day: {live}"
        )
    OUT["4_add_repaints"] = [r["day"] for r in added["plan"]]

    # 5. Deleting a day removes it from both screens.
    seed(pg, SCHEDULE)
    remove_day(pg, DAY_NUM["wed"])
    removed = pg.evaluate(READ_JS)
    assert [r["day"] for r in removed["plan"]] == ["Mon", "Sat"], (
        f"the deleted day is still in the Week plan: {removed['plan']}"
    )
    if TODAY == "Wed":
        assert removed["rest"] and not removed["today"], (
            f"Today did not become a rest day after deleting Wednesday: {removed}"
        )
    OUT["5_delete_repaints"] = [r["day"] for r in removed["plan"]]

    # 6. An empty schedule says so and never invents a day.
    pg.evaluate(
        """() => {
            D.settings.schedule = [];
            save();
            refreshAll();
        }"""
    )
    pg.wait_for_timeout(300)
    empty = pg.evaluate(READ_JS)
    assert empty["plan"] == [], f"the Week plan invented days with an empty schedule: {empty['plan']}"
    assert "no session days configured" in empty["weekText"].lower(), (
        f"the Week plan does not say there are no days: {empty['weekText']!r}"
    )
    assert empty["rest"] and not empty["today"], (
        f"Today is not a rest day with an empty schedule: {empty}"
    )
    OUT["6_empty"] = empty["weekText"]

    # 7. Every rotation mode distributes over the schedule days.
    seed(pg, SCHEDULE)
    for mode, expected in (
        ("by-part", ["Mon", "Wed", "Sat"]),
        ("full-section", ["Mon", "Wed", "Sat"]),
        ("custom", ["Mon", "Wed", "Sat"]),
    ):
        days = mode_days(pg, mode)
        assert days == expected, f"{mode} did not use the schedule days: {days}"
    OUT["7_modes"] = ["by-part", "full-section", "custom"]

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
