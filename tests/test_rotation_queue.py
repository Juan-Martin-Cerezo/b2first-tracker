"""Phase 96: by-part is one continuous rotation queue for every skill.

The queue repeats R&UE -> Listening -> Writing -> Speaking and each skill walks
its own cycle. The position comes from the units already logged, never from a
stored cursor; a session can take more than one unit.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}


def seed(pg, days=("mon", "fri"), per=1, log=None, wcycle=None):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(
        """([schedule, per, log, wCycle]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: schedule.map(s => s.day),
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.errs = [];
            D.log = log || [];
            D.sessionOffset = 0;
            D.settings.schedule = schedule;
            D.settings.rotationMode = 'by-part';
            D.settings.itemsPerSession = per;
            D.settings.rueCycle = [1, 2, 3, 4, 5, 6, 7];
            D.settings.lCycle = [1, 2, 3, 4];
            D.settings.spCycle = [1, 2, 3, 4];
            D.settings.wCycle = wCycle || ['Essay', 'Article', 'Report', 'Review', 'Email'];
            save();
            refreshAll();
        }""",
        [schedule, per, log or [], wcycle],
    )
    pg.wait_for_timeout(250)


SESSIONS_JS = """([days, per, start, count]) => rotationQueueSessions(
    days, per, start, count
).map(s => ({day: s.day, units: s.units.map(queueUnitLabel), min: s.min}))"""

PLAN_JS = """() => buildWeeklyPlan(D).slots.map(s => ({
    day: s.day,
    units: (s.units || []).map(queueUnitLabel),
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
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(250)

    # 1. Mon/Fri, one unit per session: the five first sessions interleave the
    #    skills in the expected order.
    seed(pg, ("mon", "fri"), per=1)
    sessions = pg.evaluate(SESSIONS_JS, [["mon", "fri"], 1, 0, 5])
    assert [s["units"] for s in sessions] == [
        ["Reading part 1"],
        ["Listening part 1"],
        ["Writing essay"],
        ["Speaking part 1"],
        ["Reading part 2"],
    ], f"the queue order is wrong: {sessions}"
    assert [s["day"] for s in sessions] == ["mon", "fri", "mon", "fri", "mon"], sessions
    OUT["1_queue_order"] = sessions

    # 2. Two units per session: both units always come from the SAME skill; the
    #    session duration is the sum of its units.
    seed(pg, ("mon", "fri"), per=2)
    pairs = pg.evaluate(SESSIONS_JS, [["mon", "fri"], 2, 0, 3])
    assert [s["units"] for s in pairs] == [
        ["Reading part 1", "Reading part 2"],
        ["Listening part 1", "Listening part 2"],
        ["Writing essay", "Writing article"],
    ], f"itemsPerSession=2 mixed skills or took the wrong units: {pairs}"
    slot_min = pg.evaluate("Math.max(1, Number(D.settings.slotMin) || 45)")
    assert [s["min"] for s in pairs] == [slot_min * 2, slot_min * 2, slot_min * 2], (
        f"the session duration is not the sum of its units: {pairs}"
    )
    OUT["2_two_per_session"] = {"min": slot_min, "sessions": pairs}

    # 3. A different wCycle rotates Writing through those genres and loops.
    seed(pg, ("mon", "fri"), per=1, wcycle=["Article", "Report"])
    writing = pg.evaluate(
        """() => {
            const cycles = queueCycles(D.settings);
            const out = [];
            for (let i = 0; i < 16; i++) {
                const u = queueUnit(i, cycles);
                if (u.skill === 'w') out.push(queueUnitLabel(u));
            }
            return out;
        }"""
    )
    assert writing == [
        "Writing article", "Writing report", "Writing article", "Writing report",
    ], f"Writing did not follow wCycle: {writing}"
    OUT["3_wcycle"] = writing

    # 4. The queue wraps without gaps or repeats.
    wrap = pg.evaluate(
        """() => {
            const cycles = queueCycles(D.settings);
            const seen = {rue: [], l: [], w: [], sp: []};
            for (let i = 0; i < 140; i++) {
                const u = queueUnit(i, cycles);
                seen[u.skill].push(u.value);
            }
            const rule = (arr, cycle) => arr.every((v, i) => v === cycle[i % cycle.length]);
            return {
                rue: rule(seen.rue, cycles.rue),
                l: rule(seen.l, cycles.l),
                w: rule(seen.w, cycles.w),
                sp: rule(seen.sp, cycles.sp),
                counts: Object.fromEntries(Object.entries(seen).map(([k, v]) => [k, v.length])),
            };
        }"""
    )
    assert wrap["rue"] and wrap["l"] and wrap["w"] and wrap["sp"], (
        f"a skill skipped or repeated a unit while wrapping: {wrap}"
    )
    assert wrap["counts"] == {"rue": 35, "l": 35, "w": 35, "sp": 35}, wrap
    OUT["4_wrap"] = wrap

    # 5. History decides the position; no history starts at the first unit.
    seed(pg, ("mon", "fri"), per=1)
    empty = pg.evaluate(PLAN_JS)
    assert empty[0]["units"] == ["Reading part 1"], f"no-history did not start at unit 1: {empty}"

    history = [
        {"date": "2026-10-01", "type": "ue", "part": 1, "correct": 6, "total": 8, "min": 10},
        {"date": "2026-10-02", "type": "lp", "part": 1, "correct": 6, "total": 8, "min": 10},
        {"date": "2026-10-03", "type": "w", "kind": "Essay", "score": 12, "min": 40},
    ]
    seed(pg, ("mon", "fri"), per=1, log=history)
    after = pg.evaluate(PLAN_JS)
    assert after[0]["units"] == ["Speaking part 1"], (
        f"three logged units did not move the queue to unit 4: {after}"
    )
    assert pg.evaluate("queueLogCount(D.settings, D.log)") == 3, "the log was not counted"
    OUT["5_position"] = {"empty": empty[0], "after_history": after[0]}

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
