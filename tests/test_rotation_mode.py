"""Phase 86: the user chooses how the plan rotates.

by-part keeps loose exercises/parts; full-section makes every session one
whole paper with its official exam time; custom follows the user's day-by-day
settings. Switching the mode repaints TODAY without a reload, and an invalid
customPlan falls back to the default of that day instead of breaking.
"""
import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TODAY = WD[datetime.now().weekday()]
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
FOUR_DAYS = ["mon", "tue", "wed", "thu"]


DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}


def seed_profile(pg, days=FOUR_DAYS, mode="by-part", custom=None):
    """The schedule is the plan's source of days; profile.days only seeds it."""
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(
        """([days, mode, custom, schedule]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: days,
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.log = [];
            D.errs = [];
            D.sessionOffset = 0;
            D.settings.schedule = schedule;
            D.settings.rotationMode = mode;
            D.settings.itemsPerSession = 1;
            D.settings.customPlan = custom || {};
            save();
            refreshAll();
        }""",
        [days, mode, custom, schedule],
    )
    pg.wait_for_timeout(250)


PLAN_JS = """() => buildWeeklyPlan(D).slots.map(s => ({
    day: s.day, type: s.type, part: s.part,
    parts: s.parts || [], min: s.min,
    section: !!s.section, full: !!s.full,
    units: (s.units || []).map(u => u.skill),
    title: slotTitleText(s),
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
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(250)

    # 1. by-part: loose exercises/parts, each timed by its own unit table.
    seed_profile(pg, FOUR_DAYS, "by-part")
    by_part = pg.evaluate(PLAN_JS)
    assert len(by_part) == 4, f"by-part should fill the four chosen days: {by_part}"
    assert any(s["type"] == "ue" and s["part"] is not None for s in by_part), (
        f"by-part lost its loose parts: {by_part}"
    )
    assert not any(s["section"] for s in by_part), f"by-part used a full section: {by_part}"
    assert all(len(set(s["units"])) == 1 for s in by_part if s["units"]), (
        f"by-part mixed skills inside a session: {by_part}"
    )
    assert [s["min"] for s in by_part] == [8, 10, 40, 2], (
        f"by-part is not using the per-unit durations: {by_part}"
    )
    assert [s["title"] for s in by_part] == [
        "Reading part 1 · 8 min",
        "Listening part 1 · 10 min",
        "Writing essay · 40 min",
        "Speaking part 1 · 2 min",
    ], f"by-part is not the continuous queue: {[s['title'] for s in by_part]}"
    OUT["1_by_part"] = by_part

    # 2. full-section: one whole paper per chosen day, official times, cycling.
    seed_profile(pg, FOUR_DAYS, "full-section")
    full = pg.evaluate(PLAN_JS)
    assert [s["type"] for s in full] == ["ue", "l", "w", "sp"], (
        f"full-section did not cover the four papers: {full}"
    )
    assert [s["min"] for s in full] == [75, 40, 80, 14], (
        f"full-section is not using the official exam times: {full}"
    )
    assert [s["title"] for s in full] == [
        "Full R&UE (75 min)",
        "Full Listening (40 min)",
        "Full Writing (80 min)",
        "Full Speaking (14 min)",
    ], f"full-section titles are wrong: {[s['title'] for s in full]}"
    assert all(s["section"] and s["full"] for s in full), (
        f"full-section slots are not whole papers: {full}"
    )
    OUT["2_full_section"] = full

    # 3. custom: exactly what the user asked for, day by day.
    custom = {
        "Mon": {"skill": "rue", "parts": "1,3", "min": 50},
        "Tue": {"skill": "l", "parts": "1-4", "min": 40},
        "Wed": {"skill": "w", "parts": "", "min": 80},
        "Thu": {"skill": "sp", "parts": "2", "min": 30},
    }
    seed_profile(pg, FOUR_DAYS, "custom", custom)
    got = {s["day"]: s for s in pg.evaluate(PLAN_JS)}
    assert got["Mon"]["type"] == "ue" and got["Mon"]["parts"] == [1, 3] and got["Mon"]["min"] == 50, got["Mon"]
    assert got["Tue"]["type"] == "l" and got["Tue"]["parts"] == [1, 2, 3, 4] and got["Tue"]["min"] == 40, got["Tue"]
    assert got["Wed"]["type"] == "w" and got["Wed"]["parts"] == [] and got["Wed"]["min"] == 80, got["Wed"]
    assert got["Thu"]["type"] == "sp" and got["Thu"]["parts"] == [2] and got["Thu"]["min"] == 30, got["Thu"]
    OUT["3_custom"] = got

    # 4. Switching the mode repaints TODAY in place, with no reload.
    seed_profile(pg, ALL_DAYS, "by-part")
    before = pg.evaluate("document.getElementById('todaySession').innerText")
    pg.select_option("#wpRotationMode", "full-section")
    pg.wait_for_timeout(400)
    after = pg.evaluate(
        """() => ({
            mode: D.settings.rotationMode,
            text: document.getElementById('todaySession').innerText,
        })"""
    )
    assert after["mode"] == "full-section", f"the select did not persist the mode: {after}"
    assert after["text"] != before, "TODAY did not repaint when the mode changed"
    assert "Full " in after["text"], f"TODAY is not showing a full paper: {after['text']}"
    OUT["4_repaint"] = {"before": before, "after": after["text"]}

    # 5. An invalid customPlan falls back to the default custom day, which is
    #    the plan without any custom entries (custom kept its old behaviour).
    seed_profile(pg, FOUR_DAYS, "custom", {})
    baseline = {s["day"]: s for s in pg.evaluate(PLAN_JS)}
    seed_profile(
        pg,
        FOUR_DAYS,
        "custom",
        {
            "Mon": {"skill": "nope", "min": 30},          # bad skill
            "Funday": {"skill": "rue", "min": 30},        # bad day
            "Tue": {"skill": "rue", "min": 999},          # bad duration
            "Wed": {"skill": "rue", "parts": "99", "min": 5},  # parts out of range
            "Thu": {"skill": "sp", "parts": "2", "min": 30},   # valid
        },
    )
    fallback = {s["day"]: s for s in pg.evaluate(PLAN_JS)}
    for day in ("Mon", "Tue", "Wed"):
        assert fallback[day]["type"] == baseline[day]["type"], (
            f"{day} did not fall back to its default: {fallback[day]} vs {baseline[day]}"
        )
        assert fallback[day]["min"] == baseline[day]["min"], (
            f"{day} kept an invalid duration: {fallback[day]}"
        )
    assert fallback["Thu"]["type"] == "sp" and fallback["Thu"]["parts"] == [2], (
        f"the valid custom day did not survive: {fallback['Thu']}"
    )
    OUT["5_invalid_custom"] = fallback

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
