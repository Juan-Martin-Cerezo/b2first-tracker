"""Acceptance tests for Edit my intake: days, per-day times, rotation mode,
and itemsPerSession, verified against rendered UI and buildWeeklyPlan(D).
"""
import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
OUT = {}

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TODAY_KEY = DAY_KEYS[datetime.now().weekday()]
TODAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][datetime.now().weekday()]


def open_edit_intake_plan_step(pg):
    """Open Edit my intake from Plan view and walk to step 3/3 (plan step)."""
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(150)
    pg.click("button:has-text('Edit my intake')")
    pg.wait_for_selector("#onboardingOverlay", state="visible", timeout=3000)
    if not pg.input_value("#obExamDate"):
        pg.fill("#obExamDate", "2027-06-12")
    pg.click("#obNextBtn")  # 1 -> 2
    pg.wait_for_timeout(100)
    pg.click("#obNextBtn")  # 2 -> 3 (plan)
    pg.wait_for_selector("#obAcceptBtn", state="visible", timeout=3000)


def select_days(pg, target_days):
    """Toggle day chips so exactly target_days are active."""
    pg.evaluate(
        """(target) => {
            document.querySelectorAll('.chip-btn[data-day]').forEach(b => {
                const want = target.includes(b.dataset.day);
                if ((b.getAttribute('aria-pressed') === 'true') !== want) b.click();
            });
        }""",
        target_days,
    )
    pg.wait_for_timeout(100)


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))

    pg.goto(URL + "app", wait_until="networkidle")
    login_user(pg, URL, "intake-schedule-user", "intake-schedule-pass-9")
    pg.evaluate(
        """() => {
            setLang('en');
            D.profile = {
                examDate: '2027-06-12', targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 6, days: ['mon', 'fri'],
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.log = [];
            D.errs = [];
            D.sessionOffset = 0;
            D.settings.schedule = [{day: 1, time: '15:30'}, {day: 5, time: '13:00'}];
            D.settings.sessions = D.settings.schedule;
            D.settings.rotationMode = 'by-part';
            D.settings.itemsPerSession = 1;
            save();
            refreshAll();
        }"""
    )
    pg.wait_for_timeout(250)

    # 1. Edit intake: Mon + Wed, times 07:15 and 19:45, By part.
    #    Also check preserving typed hours when toggling another day on/off.
    open_edit_intake_plan_step(pg)
    select_days(pg, ["mon", "wed"])
    pg.fill("#obTime_mon", "07:15")
    pg.fill("#obTime_wed", "19:45")
    pg.click(".chip-btn[data-day='fri']")  # add fri
    pg.wait_for_timeout(100)
    row_order = pg.eval_on_selector_all(
        "#obDayTimes .ob-time-row", "els => els.map(e => e.dataset.day)"
    )
    assert row_order == ["mon", "wed", "fri"], f"Expected mon->sun order, got {row_order}"
    assert pg.input_value("#obTime_mon") == "07:15", "Lost Mon time when adding Fri"
    assert pg.input_value("#obTime_wed") == "19:45", "Lost Wed time when adding Fri"
    assert pg.input_value("#obTime_fri") != "", "Default time for Fri was empty"
    pg.click(".chip-btn[data-day='fri']")  # remove fri
    pg.wait_for_timeout(100)
    assert pg.input_value("#obTime_mon") == "07:15", "Lost Mon time when removing Fri"
    assert pg.input_value("#obTime_wed") == "19:45", "Lost Wed time when removing Fri"

    pg.click("input[name='obRotationMode'][value='by-part']")
    pg.click(".chip-btn[data-items='1']")
    pg.wait_for_timeout(100)
    preview_1 = pg.inner_text("#obPlanPreview")
    assert "07:15" in preview_1 and "19:45" in preview_1, f"Live preview missing times: {preview_1}"

    pg.click("#obAcceptBtn")
    pg.wait_for_timeout(250)

    res1 = pg.evaluate(
        """() => {
            const plan = buildWeeklyPlan(D);
            return {
                open: document.getElementById('onboardingOverlay').style.display,
                schedule: D.settings.schedule,
                sessions: D.settings.sessions,
                slotDays: plan.slots.map(s => s.day),
                slotTimes: plan.slots.map(s => s.time),
                wpTimes: [...document.querySelectorAll('#wpRows .wp-when')].map(e => e.textContent.trim()),
                upTimes: [...document.querySelectorAll('#planUpcomingPreview .up-row')].map(e => e.dataset.time),
            };
        }"""
    )
    assert res1["open"] == "none", f"Wizard stayed open: {res1}"
    assert res1["schedule"] == [{"day": 1, "time": "07:15"}, {"day": 3, "time": "19:45"}], res1
    assert res1["sessions"] == res1["schedule"], res1
    assert res1["slotDays"] == ["Mon", "Wed"], res1
    assert res1["slotTimes"] == ["07:15", "19:45"], res1
    assert res1["wpTimes"] == ["07:15", "19:45"], res1
    assert res1["upTimes"][:2] == ["07:15", "19:45"], res1
    OUT["1_mon_wed_by_part"] = res1

    # 2. Full mocks (full-section): 4 days -> Full R&UE 75, Full Listening 40, Full Writing 80, Full Speaking 14
    open_edit_intake_plan_step(pg)
    select_days(pg, ["mon", "tue", "wed", "thu"])
    pg.click("input[name='obRotationMode'][value='full-section']")
    pg.wait_for_timeout(150)

    items_hidden = pg.evaluate(
        "() => getComputedStyle(document.getElementById('obItemsField')).display === 'none'"
    )
    assert items_hidden, "itemsPerSession field should be hidden in full-section mode"

    full_preview_text = pg.inner_text("#obPlanPreview")
    full_summary_text = pg.inner_text("#obPlanSummary")
    for expected in ("Full R&UE", "75 min", "Full Listening", "40 min", "Full Writing", "80 min", "Full Speaking", "14 min"):
        assert expected in full_preview_text, f"Missing {expected!r} in live preview: {full_preview_text}"
    assert "209" in full_summary_text, f"Summary total did not sum FULL_SECTION (209): {full_summary_text}"

    pg.click("#obAcceptBtn")
    pg.wait_for_timeout(250)

    res2 = pg.evaluate(
        """() => {
            const plan = buildWeeklyPlan(D);
            const expectedTotal = FULL_SECTION.reduce((a, x) => a + x[1], 0);
            const slotTotal = plan.slots.reduce((a, s) => a + s.min, 0);
            return {
                mode: D.settings.rotationMode,
                slots: plan.slots.map(s => ({day: s.day, type: s.type, min: s.min, label: slotLabel(s)})),
                expectedTotal,
                slotTotal,
                wpText: document.getElementById('wpRows').innerText,
                upcomingText: document.getElementById('planUpcomingPreview').innerText,
            };
        }"""
    )
    assert res2["mode"] == "full-section", res2
    assert [(s["label"], s["min"]) for s in res2["slots"]] == [
        ("Full R&UE", 75),
        ("Full Listening", 40),
        ("Full Writing", 80),
        ("Full Speaking", 14),
    ], res2
    assert res2["slotTotal"] == res2["expectedTotal"], res2
    assert "Full R&UE" in res2["wpText"] and "Full Speaking" in res2["wpText"], res2["wpText"]
    OUT["2_full_mocks"] = res2

    # 5. full-section reflected in Plan <select> and planModeLine() in EN and ES
    res5_en = pg.evaluate(
        """() => ({
            selectVal: document.getElementById('wpRotationMode').value,
            modeLine: planModeLine(),
            rotCard: document.querySelector('#rotationCardBody .rot-mode').textContent.trim(),
        })"""
    )
    assert res5_en["selectVal"] == "full-section", res5_en
    assert res5_en["modeLine"] == res5_en["rotCard"] and "whole paper" in res5_en["modeLine"].lower(), res5_en

    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(150)
    res5_es = pg.evaluate(
        """() => ({
            selectVal: document.getElementById('wpRotationMode').value,
            modeLine: planModeLine(),
            rotCard: document.querySelector('#rotationCardBody .rot-mode').textContent.trim(),
        })"""
    )
    assert res5_es["selectVal"] == "full-section", res5_es
    assert res5_es["modeLine"] == res5_es["rotCard"] and "paper completo" in res5_es["modeLine"].lower(), res5_es
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(150)
    OUT["5_select_and_mode_line"] = {"en": res5_en, "es": res5_es}

    # Check Today view reflects full-section and chosen time when today is scheduled
    open_edit_intake_plan_step(pg)
    select_days(pg, [TODAY_KEY])
    pg.fill(f"#obTime_{TODAY_KEY}", "08:45")
    pg.click("#obAcceptBtn")
    pg.wait_for_timeout(200)
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(200)
    today_full = pg.evaluate(
        """() => ({
            title: (document.querySelector('#todaySession .ts-title') || {}).innerText || '',
            dur: (document.querySelector('#todaySession .ts-duration') || {}).innerText || '',
            when: (document.querySelector('#todaySession .ts-when') || {}).innerText || '',
        })"""
    )
    assert "Full R&UE" in today_full["title"], today_full
    assert "75 min" in today_full["dur"], today_full
    assert today_full["when"].strip() == "08:45", today_full
    OUT["today_full_sync"] = today_full

    # 4a. Reopen Edit my intake while full-section is saved -> preloaded (not reverted to default)
    open_edit_intake_plan_step(pg)
    reopen_full = pg.evaluate(
        """() => ({
            checkedMode: (document.querySelector("input[name='obRotationMode']:checked") || {}).value,
            activeDays: [...document.querySelectorAll('.chip-btn[data-day][aria-pressed="true"]')].map(b => b.dataset.day),
            timeVal: document.querySelector('#obDayTimes input[type="time"]').value,
        })"""
    )
    assert reopen_full["checkedMode"] == "full-section", reopen_full
    assert reopen_full["activeDays"] == [TODAY_KEY], reopen_full
    assert reopen_full["timeVal"] == "08:45", reopen_full

    # 3. itemsPerSession=3 with by-part -> a session contains 3 units of the same skill
    select_days(pg, ["mon", "fri"])
    pg.fill("#obTime_mon", "09:10")
    pg.fill("#obTime_fri", "18:20")
    pg.click("input[name='obRotationMode'][value='by-part']")
    pg.wait_for_timeout(100)
    pg.click(".chip-btn[data-items='3']")
    pg.wait_for_timeout(150)

    preview_3 = pg.inner_text("#obPlanPreview")
    assert "Reading part 1" in preview_3 and "Reading part 3" in preview_3, preview_3
    pg.click("#obAcceptBtn")
    pg.wait_for_timeout(250)

    res3 = pg.evaluate(
        """() => {
            const plan = buildWeeklyPlan(D);
            const firstUnits = plan.slots[0].units || [];
            return {
                mode: D.settings.rotationMode,
                itemsPerSession: D.settings.itemsPerSession,
                wpItems: document.getElementById('wpItemsPerSession').value,
                unitCount: firstUnits.length,
                unitSkills: [...new Set(firstUnits.map(u => u.skill))],
                slot0Min: plan.slots[0].min,
            };
        }"""
    )
    assert res3["mode"] == "by-part", res3
    assert res3["itemsPerSession"] == 3 and res3["wpItems"] == "3", res3
    assert res3["unitCount"] == 3, res3
    assert len(res3["unitSkills"]) == 1, f"Units mixed skills: {res3}"
    assert res3["slot0Min"] == 24, res3
    OUT["3_items_per_session_3"] = res3

    # 4b. Reopen Edit my intake -> days, times, mode, and itemsPerSession=3 are prefilled
    open_edit_intake_plan_step(pg)
    reopen_3 = pg.evaluate(
        """() => ({
            activeDays: [...document.querySelectorAll('.chip-btn[data-day][aria-pressed="true"]')].map(b => b.dataset.day),
            monTime: document.getElementById('obTime_mon').value,
            friTime: document.getElementById('obTime_fri').value,
            checkedMode: (document.querySelector("input[name='obRotationMode']:checked") || {}).value,
            activeItems: document.querySelector('.chip-btn[data-items][aria-pressed="true"]').dataset.items,
        })"""
    )
    assert reopen_3 == {
        "activeDays": ["mon", "fri"],
        "monTime": "09:10",
        "friTime": "18:20",
        "checkedMode": "by-part",
        "activeItems": "3",
    }, f"Reopened Edit intake did not preserve saved values: {reopen_3}"
    OUT["4_reopen_prefilled"] = reopen_3

    # 6. Soft warning on duplicate time (non-blocking) + empty time blocks with role="alert"
    pg.fill("#obTime_fri", "09:10")
    pg.wait_for_timeout(100)
    warn_vis = pg.is_visible("#obTimeWarn")
    assert warn_vis, "Soft duplicate-time warning did not appear"

    pg.fill("#obTime_mon", "")
    pg.wait_for_timeout(100)
    pg.click("#obAcceptBtn")
    pg.wait_for_timeout(150)

    res6 = pg.evaluate(
        """() => {
            const err = document.getElementById('obError');
            return {
                stillOpen: document.getElementById('onboardingOverlay').style.display === 'flex',
                role: err ? err.getAttribute('role') : null,
                errorText: err ? err.textContent.trim() : '',
                schedule: D.settings.schedule,
            };
        }"""
    )
    assert res6["stillOpen"] is True, f"Accepted despite empty time: {res6}"
    assert res6["role"] == "alert", res6
    assert len(res6["errorText"]) > 0, "Empty error text on invalid time"
    assert res6["schedule"] == [{"day": 1, "time": "09:10"}, {"day": 5, "time": "18:20"}], (
        f"Invalid submit mutated schedule: {res6}"
    )
    OUT["6_empty_time_blocked"] = res6

    assert page_errors == [], f"JS errors: {page_errors}"
    OUT["js_errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=2))
