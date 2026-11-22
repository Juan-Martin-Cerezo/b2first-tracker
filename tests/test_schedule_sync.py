"""Phase schedule-sync: adding, editing or removing a day keeps Today, Plan,
What comes next, Practice now and the studios in lockstep.

Reproduces Juan's report (Mon/Fri schedule + adding Sun -> Today header vs
exercise box mismatch) and verifies:
1. Initial [Mon 15:30, Fri 15:30] state is captured and coherent.
2. Adding Sun 17:00 via UI (`addScheduleRow` + select) recalculates Today,
   What comes next, Weekly plan, Practice now and studios from the same slot;
   works in both `full-section` (including +1 fast-forward) and `by-part`.
3. Changing a slot's day/time recalculates all views and keeps open studio synced.
4. Removing a day leaves zero references to the removed day in Today, studios
   and preview; queue stays continuous without resetting or repeating done units.
5. Reloading persists the schedule and full coherence.
6. Studios opened from the plan show the slot's real day (never hardcoded
   Monday/Friday); studios opened directly show neutral Session A / Session B
   in both EN and ES.
7. Mobile 390x844 light screenshot at tests/out/schedule_sync_390_light.png
   with zero horizontal overflow.
"""
import json
import os
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = {}

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WD_FULL = {
    "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday",
    "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
}
DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
TODAY = WD[datetime.now().weekday()]
TODAY_NUM = DAY_NUM[TODAY.lower()]

READ_ALL_JS = """() => {
    const vis = id => {
        const el = document.getElementById(id);
        return !!el && getComputedStyle(el).display !== 'none' && el.offsetParent !== null;
    };
    const rowEl = document.querySelector('#todaySession .ts-row:not(.ts-next-unit)');
    const todayRow = rowEl ? {
        day: rowEl.dataset.day,
        time: rowEl.dataset.time || '',
        type: rowEl.dataset.type,
        units: (rowEl.dataset.units || '').split(',').filter(Boolean),
        min: Number(rowEl.dataset.min),
        title: ((rowEl.querySelector('.ts-title') || {}).textContent || '').trim(),
        mode: ((rowEl.querySelector('.ts-mode') || {}).textContent || '').trim(),
    } : null;
    const studios = [
        ['rue', 'studioMonA', 'st1WkBadge', 'st1TimeBadge', 'st1Name', 'st1Dur'],
        ['w',   'studioMonB', 'st2WkBadge', 'st2TimeBadge', 'st2Name', 'st2Dur'],
        ['l',   'studioFriA', 'st3WkBadge', 'st3TimeBadge', 'st3Name', 'st3Dur'],
        ['sp',  'studioFriB', 'st4WkBadge', 'st4TimeBadge', 'st4Name', 'st4Dur'],
    ].map(([skill, cardId, wkId, timeId, nameId, durId]) => {
        const card = document.getElementById(cardId);
        const timeEl = document.getElementById(timeId);
        return {
            skill,
            cardId,
            visible: vis(cardId),
            wk: (document.getElementById(wkId) || {}).textContent.trim(),
            time: timeEl && getComputedStyle(timeEl).display !== 'none'
                ? timeEl.textContent.trim() : '',
            name: (document.getElementById(nameId) || {}).textContent.trim(),
            dur: (document.getElementById(durId) || {}).textContent.trim(),
            planDay: card ? (card.dataset.planDay || '') : '',
            planSource: card ? (card.dataset.planSource || '') : '',
        };
    });
    const planRows = [...document.querySelectorAll('#wpRows .wp-row')].map(r => ({
        day: r.dataset.day,
        time: r.dataset.time || '',
        type: r.dataset.type,
        units: (r.dataset.units || '').split(',').filter(Boolean),
        min: Number(r.dataset.min),
        title: ((r.querySelector('.wp-title') || {}).textContent || '').trim(),
    }));
    const upcoming = [...document.querySelectorAll('#planUpcomingPreview .up-row')].map(r => ({
        day: r.dataset.day,
        time: r.dataset.time || '',
        skill: r.dataset.skill || '',
        text: r.innerText.trim(),
    }));
    const practiceNow = document.getElementById('practiceNow');
    return {
        rest: !!document.querySelector('#todaySession [data-rest]'),
        todayRow,
        todayNext: ((document.getElementById('todayNextValue') || {}).textContent || '').trim(),
        todayCycle: ((document.getElementById('todayCycleValue') || {}).textContent || '').trim(),
        todayText: ((document.getElementById('todaySession') || {}).innerText || '').trim(),
        practiceVisible: !!practiceNow && getComputedStyle(practiceNow).display !== 'none',
        planRows,
        upcoming,
        rotMode: ((document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '').trim(),
        studios,
        openStudios: studios.filter(s => s.visible),
    };
}"""


def seed(pg, schedule, mode="by-part", log=None, offset=0):
    pg.evaluate(
        """([schedule, mode, log, offset]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: ['mon', 'fri'],
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.errs = [];
            D.log = log.slice();
            D.sessionOffset = offset;
            D.weekOverrides = {};
            D.settings.schedule = schedule;
            D.settings.sessions = schedule;
            D.settings.rotationMode = mode;
            D.settings.itemsPerSession = 1;
            closeSessionStudios();
            save();
            refreshAll();
        }""",
        [schedule, mode, log or [], offset],
    )
    pg.wait_for_timeout(250)


def go_view(pg, view):
    pg.evaluate("(v) => showView(v)", view)
    pg.wait_for_timeout(180)


def add_day_via_ui(pg, day_num, time_str="17:00"):
    go_view(pg, "plan")
    before = pg.eval_on_selector_all(".sched-day-select", "els => els.map(e => +e.value)")
    pg.click("button[data-action='addScheduleRow']")
    pg.wait_for_timeout(150)
    after = pg.eval_on_selector_all(".sched-day-select", "els => els.map(e => +e.value)")
    idx = next(i for i, v in enumerate(after) if v not in before)
    pg.locator(".sched-day-select").nth(idx).select_option(str(day_num))
    pg.locator(".sched-time-input").nth(idx).fill(time_str)
    pg.locator(".sched-time-input").nth(idx).dispatch_event("change")
    pg.wait_for_timeout(250)


def change_day_via_ui(pg, from_day_num, to_day_num, new_time=None):
    go_view(pg, "plan")
    idx = pg.evaluate(
        """(fromDay) => {
            const sels = [...document.querySelectorAll('.sched-day-select')];
            return sels.findIndex(s => +s.value === fromDay);
        }""",
        from_day_num,
    )
    assert idx >= 0, f"day {from_day_num} not found in schedule selects"
    pg.locator(".sched-day-select").nth(idx).select_option(str(to_day_num))
    if new_time is not None:
        pg.locator(".sched-time-input").nth(idx).fill(new_time)
        pg.locator(".sched-time-input").nth(idx).dispatch_event("change")
    pg.wait_for_timeout(250)


def remove_day_via_ui(pg, day_num):
    go_view(pg, "plan")
    clicked = pg.evaluate(
        """(day) => {
            const rows = [...document.querySelectorAll('#scheduleRowsContainer .sched-row')];
            const row = rows.find(r => +r.querySelector('.sched-day-select').value === day);
            if (!row) return false;
            row.querySelector("button[data-action='removeScheduleRow']").click();
            return true;
        }""",
        day_num,
    )
    assert clicked, f"could not remove day {day_num}"
    pg.wait_for_timeout(250)


def assert_today_matches_plan_and_studio(state, label):
    """Verify Today's header, plan slot and matching studio share day, skill & minutes."""
    row = state["todayRow"]
    assert row is not None and not state["rest"], f"{label}: Today has no session: {state}"
    plan_today = [r for r in state["planRows"] if r["day"] == row["day"]]
    assert len(plan_today) == 1, f"{label}: plan has no single row for {row['day']}: {state['planRows']}"
    ps = plan_today[0]
    assert row["type"] == ps["type"], f"{label}: Today type {row['type']} != plan {ps['type']}"
    assert row["min"] == ps["min"], f"{label}: Today min {row['min']} != plan {ps['min']}"
    assert row["time"] == ps["time"], f"{label}: Today time {row['time']} != plan {ps['time']}"
    assert row["units"] == ps["units"], f"{label}: Today units {row['units']} != plan {ps['units']}"
    assert f"{row['min']} min" in row["title"], f"{label}: Today title missing minutes: {row['title']}"
    assert row["day"] in row["title"], f"{label}: Today title missing day: {row['title']}"

    skill = "rue" if row["type"] == "ue" else row["type"]
    st = next(s for s in state["studios"] if s["skill"] == skill)
    expected_full_day = WD_FULL[row["day"]]
    assert st["wk"] == expected_full_day, (
        f"{label}: studio badge {st['wk']!r} != {expected_full_day!r}: {st}"
    )
    assert st["dur"] == f"{row['min']} MIN", (
        f"{label}: studio duration {st['dur']!r} != {row['min']} MIN: {st}"
    )
    if row["time"]:
        expected_time_badge = f"{expected_full_day[:3].upper()} {row['time']}"
        assert st["time"] == expected_time_badge, (
            f"{label}: studio time badge {st['time']!r} != {expected_time_badge!r}: {st}"
        )
    # Any currently visible studio opened from the plan must belong to the same slot.
    for open_st in state["openStudios"]:
        assert open_st["skill"] == skill, (
            f"{label}: open studio skill {open_st['skill']} != Today skill {skill}: {open_st}"
        )
        assert open_st["wk"] == expected_full_day, (
            f"{label}: open studio day {open_st['wk']!r} != {expected_full_day!r}: {open_st}"
        )
        assert open_st["dur"] == f"{row['min']} MIN", (
            f"{label}: open studio min {open_st['dur']!r} != {row['min']} MIN: {open_st}"
        )


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(350)

    # ------------------------------------------------------------------
    # 1. Start with [Mon 15:30, Fri 15:30] in full-section (Juan's exact setup)
    #    Capture Today's header & plan state.
    # ------------------------------------------------------------------
    base_sched = [{"day": 1, "time": "15:30"}, {"day": 5, "time": "15:30"}]
    seed(pg, base_sched, mode="full-section", log=[], offset=0)
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(200)
    s1 = pg.evaluate(READ_ALL_JS)
    assert [r["day"] for r in s1["planRows"]] == ["Mon", "Fri"], s1["planRows"]
    assert s1["openStudios"] == [], f"studios should be closed initially: {s1['openStudios']}"
    OUT["1_initial_mon_fri"] = {
        "plan_days": [r["day"] for r in s1["planRows"]],
        "today_rest": s1["rest"],
        "today_row": s1["todayRow"],
    }

    # ------------------------------------------------------------------
    # 2. Add Sun 17:00 from the UI (data-action="addScheduleRow" + select)
    #    Verify Juan's exact bug is gone: Today header & exercise box match,
    #    even after clicking +1 fast-forward!
    # ------------------------------------------------------------------
    add_day_via_ui(pg, 0, "17:00")
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(200)
    s2_full = pg.evaluate(READ_ALL_JS)
    assert [r["day"] for r in s2_full["planRows"]] == ["Mon", "Fri", "Sun"], s2_full["planRows"]
    sun_plan = next(r for r in s2_full["planRows"] if r["day"] == "Sun")
    assert sun_plan["type"] == "w" and sun_plan["min"] == 80 and sun_plan["time"] == "17:00", sun_plan
    assert s2_full["openStudios"] == [], f"full-section should not auto-open a studio: {s2_full['openStudios']}"
    # Check Sunday's Writing studio card in DOM carries Sunday / 80 MIN, never Monday.
    w_studio = next(s for s in s2_full["studios"] if s["skill"] == "w")
    assert w_studio["wk"] == "Sunday" and w_studio["time"] == "SUN 17:00" and w_studio["dur"] == "80 MIN", w_studio
    if TODAY == "Sun":
        assert_today_matches_plan_and_studio(s2_full, "2_full_section_sun")
        assert not s2_full["practiceVisible"], "Practice now must stay hidden on session day"
        # Click +1 fast-forward: Today advances to Full Speaking (14 min) and
        # MUST NOT pop open a mismatched studio box underneath.
        pg.click("#todaySession button[data-action='advanceSession']")
        pg.wait_for_timeout(250)
        s2_ff = pg.evaluate(READ_ALL_JS)
        assert_today_matches_plan_and_studio(s2_ff, "2_full_section_sun_ff")
        assert s2_ff["openStudios"] == [], (
            f"advanceSession popped open a stale studio box: {s2_ff['openStudios']}"
        )
        pg.evaluate("resetSessionOffset()")
        pg.wait_for_timeout(200)

    # Also test by-part mode: add Sun 17:00 (and ensure TODAY is scheduled),
    # click Start on Today, and verify Today header == opened studio card!
    seed(pg, base_sched, mode="by-part", log=[], offset=0)
    add_day_via_ui(pg, 0, "17:00")
    if TODAY not in ("Mon", "Fri", "Sun"):
        add_day_via_ui(pg, TODAY_NUM, "17:00")
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(200)
    s2_bp_before = pg.evaluate(READ_ALL_JS)
    assert_today_matches_plan_and_studio(s2_bp_before, "2_by_part_before_start")
    pg.click("#todaySession .ts-row:not(.ts-next-unit) button[data-action='todayStart']")
    pg.wait_for_timeout(250)
    s2_bp_open = pg.evaluate(READ_ALL_JS)
    assert len(s2_bp_open["openStudios"]) == 1, f"Start did not open 1 studio: {s2_bp_open['openStudios']}"
    assert_today_matches_plan_and_studio(s2_bp_open, "2_by_part_after_start")
    OUT["2_add_sun"] = {
        "full_sun_plan": sun_plan,
        "full_w_studio": w_studio,
        "bp_today": s2_bp_open["todayRow"],
        "bp_open_studio": s2_bp_open["openStudios"][0],
    }

    # ------------------------------------------------------------------
    # 3. Change a slot's day/time from the UI while studio is open:
    #    change Fri (5) -> Wed (3) 18:30 (or another non-today day) and also
    #    change TODAY's time to 19:15; verify Today header, Plan, What comes
    #    next and the open studio ALL recalculate and match!
    # ------------------------------------------------------------------
    change_day_via_ui(pg, 5 if TODAY != "Fri" else 1, 3 if TODAY != "Wed" else 2, "18:30")
    change_day_via_ui(pg, TODAY_NUM, TODAY_NUM, "19:15")
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(250)
    s3 = pg.evaluate(READ_ALL_JS)
    assert_today_matches_plan_and_studio(s3, "3_after_day_change")
    assert s3["todayRow"]["time"] == "19:15", s3["todayRow"]
    assert any(r["time"] == "18:30" for r in s3["planRows"]), s3["planRows"]
    assert any(r["time"] == "18:30" for r in s3["upcoming"]), s3["upcoming"]
    OUT["3_change_day"] = {
        "plan_days": [(r["day"], r["time"]) for r in s3["planRows"]],
        "today_row": s3["todayRow"],
        "open_studio": s3["openStudios"][0] if s3["openStudios"] else None,
    }

    # ------------------------------------------------------------------
    # 4. Remove a day via UI and verify ZERO references to the removed day
    #    remain in Today rows, studios, plan rows or What comes next preview.
    #    Also verify continuous queue (done units never reset or repeat).
    # ------------------------------------------------------------------
    seed(
        pg,
        [{"day": 1, "time": "15:30"}, {"day": 5, "time": "15:30"}, {"day": 0, "time": "17:00"}],
        mode="by-part",
        log=[{"date": "2026-11-20", "type": "ue", "part": 1, "correct": 6, "total": 8, "min": 8}],
        offset=0,
    )
    # Remove Sunday (0) via UI
    remove_day_via_ui(pg, 0)
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(250)
    s4 = pg.evaluate(READ_ALL_JS)
    assert [r["day"] for r in s4["planRows"]] == ["Mon", "Fri"], s4["planRows"]
    assert all(r["day"] != "sun" for r in s4["upcoming"]), s4["upcoming"]
    assert all("Sunday" not in r["text"] for r in s4["upcoming"]), s4["upcoming"]
    assert s4["todayRow"] is None or s4["todayRow"]["day"] != "Sun", s4["todayRow"]
    assert "Sun" not in s4["todayNext"], f"deleted Sun leaked into todayNext: {s4['todayNext']}"
    for st in s4["studios"]:
        assert "Sunday" not in st["wk"] and "SUN" not in st["time"], (
            f"deleted Sun leaked into studio {st['cardId']}: {st}"
        )
    # Queue continuity: Reading part 1 was logged, so first slot must be Listening part 1
    # (and when adding a day back, it must NOT reset to Reading part 1!).
    assert s4["planRows"][0]["units"] == ["l:1"], f"queue reset after removing day: {s4['planRows']}"
    add_day_via_ui(pg, 0, "17:00")
    s4_readded = pg.evaluate(READ_ALL_JS)
    assert s4_readded["planRows"][0]["units"] == ["l:1"], (
        f"queue reset after adding day: {s4_readded['planRows']}"
    )
    assert all("rue:1" not in r["units"] for r in s4_readded["planRows"]), (
        f"already-done unit rue:1 repeated: {s4_readded['planRows']}"
    )
    OUT["4_remove_and_continuity"] = {
        "after_remove_days": [r["day"] for r in s4["planRows"]],
        "after_remove_first_unit": s4["planRows"][0]["units"],
        "after_readd_units": [r["units"] for r in s4_readded["planRows"]],
    }

    # ------------------------------------------------------------------
    # 5. Persistence: reload the page after adding Sun 17:00 and confirm
    #    coherence across Plan, Preview, Today and studio opened from plan.
    # ------------------------------------------------------------------
    seed(pg, base_sched, mode="by-part", log=[], offset=0)
    add_day_via_ui(pg, 0, "17:00")
    if TODAY not in ("Mon", "Fri", "Sun"):
        add_day_via_ui(pg, TODAY_NUM, "17:00")
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(500)
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(250)
    s5_before = pg.evaluate(READ_ALL_JS)
    assert "Sun" in [r["day"] for r in s5_before["planRows"]], s5_before["planRows"]
    assert_today_matches_plan_and_studio(s5_before, "5_after_reload")
    pg.click("#todaySession .ts-row:not(.ts-next-unit) button[data-action='todayStart']")
    pg.wait_for_timeout(250)
    s5_open = pg.evaluate(READ_ALL_JS)
    assert_today_matches_plan_and_studio(s5_open, "5_after_reload_start")
    OUT["5_reload_persisted"] = {
        "plan_days": [r["day"] for r in s5_open["planRows"]],
        "today_row": s5_open["todayRow"],
        "open_studio": s5_open["openStudios"][0],
    }

    # ------------------------------------------------------------------
    # 6. Studios opened from menu show neutral "Session A" / "Session B"
    #    (EN & ES), with NO hardcoded "Monday" / "Friday".
    #    Studios opened from the plan show the slot's real day.
    # ------------------------------------------------------------------
    pg.evaluate("selectSessionStudio('mon-a')")
    pg.wait_for_timeout(150)
    m_a_en = pg.evaluate(READ_ALL_JS)["openStudios"][0]
    assert m_a_en["wk"] == "Session A" and m_a_en["time"] == "", m_a_en

    pg.evaluate("selectSessionStudio('fri-b')")
    pg.wait_for_timeout(150)
    m_b_en = pg.evaluate(READ_ALL_JS)["openStudios"][0]
    assert m_b_en["wk"] == "Session B" and m_b_en["time"] == "", m_b_en

    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(250)
    m_b_es = pg.evaluate(READ_ALL_JS)["openStudios"][0]
    assert m_b_es["wk"] == "Sesión B" and m_b_es["time"] == "", m_b_es

    pg.evaluate("selectSessionStudio('mon-b')")
    pg.wait_for_timeout(150)
    m_a_es = pg.evaluate(READ_ALL_JS)["openStudios"][0]
    assert m_a_es["wk"] == "Sesión A" and m_a_es["time"] == "", m_a_es

    # Re-open from Today's plan in ES: shows localized real day (e.g. Domingo), not Monday/Lunes.
    pg.click("#todaySession .ts-row:not(.ts-next-unit) button[data-action='todayStart']")
    pg.wait_for_timeout(200)
    p_es = pg.evaluate(READ_ALL_JS)["openStudios"][0]
    assert p_es["planSource"] == "plan" and p_es["wk"] not in ("Session A", "Session B", "Sesión A", "Sesión B"), p_es
    if TODAY == "Sun":
        assert p_es["wk"] == "Domingo", p_es

    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(250)
    OUT["6_neutral_and_plan_labels"] = {
        "menu_a_en": m_a_en["wk"],
        "menu_b_en": m_b_en["wk"],
        "menu_a_es": m_a_es["wk"],
        "menu_b_es": m_b_es["wk"],
        "plan_es": p_es["wk"],
    }

    # ------------------------------------------------------------------
    # 7. Mobile 390x844 light theme screenshot with Sunday added, no overflow.
    # ------------------------------------------------------------------
    pg.set_viewport_size({"width": 390, "height": 844})
    pg.evaluate("document.documentElement.setAttribute('data-theme','light')")
    seed(pg, base_sched, mode="full-section", log=[], offset=0)
    add_day_via_ui(pg, 0, "17:00")
    go_view(pg, "hoy")
    pg.wait_for_timeout(200)
    ov_hoy = pg.evaluate("() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})")
    assert ov_hoy["sw"] <= ov_hoy["iw"], f"Mobile 390x844 overflow on Today: {ov_hoy}"
    shot_path = os.path.join(OUT_DIR, "schedule_sync_390_light.png")
    pg.screenshot(path=shot_path, full_page=True)

    go_view(pg, "plan")
    pg.wait_for_timeout(150)
    ov_plan = pg.evaluate("() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})")
    assert ov_plan["sw"] <= ov_plan["iw"], f"Mobile 390x844 overflow on Plan: {ov_plan}"

    OUT["7_mobile_390"] = {"hoy": ov_hoy, "plan": ov_plan, "screenshot": shot_path}
    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
