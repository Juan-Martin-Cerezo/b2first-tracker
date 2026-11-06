"""Phase 86: the user chooses how the plan rotates.

by-part keeps loose exercises/parts; full-section makes every session one
whole paper with its official exam time. Switching the mode repaints TODAY
without a reload, and an unknown stored mode falls back to by-part.
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


def seed_profile(pg, days=FOUR_DAYS, mode="by-part"):
    """The schedule is the plan's source of days; profile.days only seeds it."""
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(
        """([days, mode, schedule]) => {
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
            save();
            refreshAll();
        }""",
        [days, mode, schedule],
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
    assert [s["min"] for s in by_part] == [8, 10, 8, 10], (
        f"by-part is not using the per-unit durations: {by_part}"
    )
    assert [s["title"] for s in by_part] == [
        "Reading part 1 · 8 min",
        "Listening part 1 · 10 min",
        "Reading part 2 · 8 min",
        "Listening part 2 · 10 min",
    ], f"by-part is not the weekly block queue: {[s['title'] for s in by_part]}"
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

    # 3. Switching the mode repaints TODAY in place, with no reload.
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
    OUT["3_repaint"] = {"before": before, "after": after["text"]}

    # 4. A stored unknown mode falls back to by-part instead of breaking.
    seed_profile(pg, FOUR_DAYS, "by-part")
    baseline = pg.evaluate(PLAN_JS)
    legacy = pg.evaluate(
        """() => {
            D.settings.rotationMode = 'custom';
            save();
            refreshAll();
            return {
                normalized: normalizeRotationMode(D.settings.rotationMode),
                select: document.getElementById('wpRotationMode').value,
                plan: buildWeeklyPlan(D).slots.map(s => ({
                    day: s.day, type: s.type, part: s.part,
                    parts: s.parts || [], min: s.min,
                    section: !!s.section, full: !!s.full,
                    units: (s.units || []).map(u => u.skill),
                    title: slotTitleText(s),
                })),
            };
        }"""
    )
    assert legacy["normalized"] == "by-part", f"unknown mode did not fall back: {legacy}"
    assert legacy["select"] == "by-part", f"selector kept the unknown mode: {legacy}"
    assert legacy["plan"] == baseline, (
        f"an unknown mode did not behave as by-part: {legacy['plan']} vs {baseline}"
    )
    OUT["4_unknown_falls_back"] = legacy["normalized"]

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
