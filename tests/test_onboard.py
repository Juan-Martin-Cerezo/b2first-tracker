"""Tests of the onboarding intake wizard (5 steps) and its outputs:

- the wizard (dialog, focus trap, Back/Continue, Esc) and D.profile
- the weekly plan (the rotation queue driven by the schedule and the log:
  one session per scheduled day, one skill per session, position from the log)
- Today's exam countdown using profile.examDate
- "Edit my intake" / "Replay the app tour" in Plan -> Settings
- the 7-step feature tour, skipping invisible targets
- empty states; errores_js empty across the whole run

It boots its own server with DATA_DIR in a temporary directory (pattern
from test_sync.py): it never touches data/ and sync only writes there.
"""

import json
import os
import sys
import tempfile
import threading
import urllib.request

from playwright.sync_api import sync_playwright

# Import the server with data in a temporary directory (never touch the real one)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S

_tmp = tempfile.mkdtemp(prefix="b2onboard-")
S.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
# Ephemeral port: a fixed one may be taken by a stale process
S.PORT = 0
# The multi-user server migrates on first boot: create the owner and its folder
if not os.path.exists(S.USERS_FILE):
    S.migrate_legacy()

srv = S.ThreadingHTTPServer(("127.0.0.1", S.PORT), S.H)
S.PORT = srv.server_address[1]
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()

URL = f"http://127.0.0.1:{S.PORT}/"


def login_owner():
    req = urllib.request.Request(
        URL + "api/login",
        data=json.dumps({"name": "Owner", "password": "b2first"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


out = {}
user = login_owner()

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    pg.goto(URL + "app", wait_until="networkidle")
    pg.evaluate("u => localStorage.setItem('b2first_user', JSON.stringify(u))", user)
    pg.reload(wait_until="networkidle")

    # 1. First visit -> wizard visible at step 1/5
    pg.wait_for_selector("#onboardingOverlay", state="visible", timeout=5000)
    res1 = pg.evaluate(
        """() => ({
        visible: document.getElementById('onboardingOverlay').style.display === 'flex',
        step: document.getElementById('obStepCount').textContent.trim()
    })"""
    )
    assert res1["visible"] is True, f"Wizard not visible on first visit: {res1}"
    assert res1["step"] == "1/5", f"Expected step 1/5, got {res1}"
    out["1_primera_visita"] = f"OK: wizard visible, step {res1['step']}"

    # 2. Initial focus is inside the dialog
    res2 = pg.evaluate(
        "() => !!document.getElementById('obDialog').contains(document.activeElement)"
    )
    assert res2 is True, "Initial focus is not inside #obDialog"
    out["2_foco_inicial"] = "OK: focus inside #obDialog"

    # 3. Continue advances to 2/5; Back returns to 1/5 (step 1 requires a date)
    pg.fill("#obExamDate", "2027-06-12")
    pg.click("#obNextBtn")
    pg.wait_for_timeout(100)
    step_a = pg.text_content("#obStepCount").strip()
    pg.click("#obBackBtn")
    pg.wait_for_timeout(100)
    step_b = pg.text_content("#obStepCount").strip()
    assert step_a == "2/5", f"Continue did not advance: {step_a}"
    assert step_b == "1/5", f"Back did not return: {step_b}"
    out["3_continue_back"] = "OK: Continue -> 2/5, Back -> 1/5"

    # 4. Complete the 5 steps -> D.profile with all the fields + onboarded
    pg.fill("#obExamDate", "2027-06-12")
    pg.click("input[name='obGrade'][value='A']")
    pg.click("#obNextBtn")  # 1 -> 2 (skills)
    pg.click(".ob-rate-btn[data-skill='w'][data-val='2']")
    pg.click("#obNextBtn")  # 2 -> 3 (diagnostic step)
    # The diagnostic is not part of this test; seed a result and continue.
    pg.evaluate(
        """() => {
        D.diag = {date: today(), correct: 8, total: 12,
                  byPart: {1:{ok:2,n:2},2:{ok:1,n:2},3:{ok:2,n:2},4:{ok:1,n:2},
                           5:{ok:1,n:1},6:{ok:0,n:1},7:{ok:1,n:2}},
                  weakest: [6, 4, 7]};
        obRender();
    }"""
    )
    pg.click("#obStepBody .btn.ok")  # -> plan step
    pg.wait_for_timeout(150)
    assert pg.text_content("#obStepCount").strip() == "4/5", "Did not reach the plan step"
    # Choose 6 h/week and mon/wed/sat with the real chips.
    pg.click(".chip-btn[data-hours='6']")
    pg.evaluate(
        """() => {
        const target = ['mon','wed','sat'];
        document.querySelectorAll('.chip-btn[data-day]').forEach(b => {
            const want = target.includes(b.dataset.day);
            if ((b.getAttribute('aria-pressed') === 'true') !== want) b.click();
        });
    }"""
    )
    preview_rows = pg.eval_on_selector_all(
        "#obPlanPreview .ob-preview-row", "els => els.length"
    )
    assert preview_rows == 3, (
        f"Plan preview has {preview_rows} rows, expected one per chosen day (3)"
    )
    pg.click("#obAcceptBtn")
    pg.wait_for_timeout(200)
    assert pg.text_content("#obStepCount").strip() == "5/5", "Did not reach the account plan step"
    pg.click("#obNextBtn")
    pg.wait_for_timeout(350)
    # Continuing from step 5/5 starts the guided tour; finishing it marks the intake done.
    assert pg.evaluate("TOUR.active === true"), "Continuing past account plan did not start the tour"
    pg.evaluate("endTour()")
    # Let the save that carries onboarded=true reach the server before reload.
    pg.wait_for_timeout(900)
    res4 = pg.evaluate(
        """() => {
        const p = D.profile || {};
        return {
            onboarded: D.onboarded === true,
            examDate: p.examDate, targetGrade: p.targetGrade, skills: p.skills,
            hoursWeek: p.hoursWeek, days: p.days, struggles: p.struggles,
            declaredAt: typeof p.declaredAt === 'string' && p.declaredAt.length > 0
        };
    }"""
    )
    assert res4["onboarded"] is True, f"Not onboarded: {res4}"
    assert res4["examDate"] == "2027-06-12", f"Bad examDate: {res4}"
    assert res4["targetGrade"] == "A", f"Bad targetGrade: {res4}"
    assert res4["skills"] == {"rue": 3, "w": 2, "l": 3, "sp": 3}, f"Bad skills: {res4}"
    assert res4["hoursWeek"] == 6, f"Bad hoursWeek: {res4}"
    assert sorted(res4["days"]) == sorted(["mon", "wed", "sat"]), f"Bad days: {res4}"
    assert res4["struggles"] == [], f"Bad struggles: {res4}"
    assert res4["declaredAt"] is True, f"Bad declaredAt: {res4}"
    out["4_perfil_completo"] = f"OK: D.profile={res4}"

    # 5. Reload -> wizard does NOT appear
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(500)
    res5 = pg.evaluate(
        """() => ({
        vis: document.getElementById('onboardingOverlay').style.display,
        onboarded: D.onboarded === true, profile: !!D.profile
    })"""
    )
    assert res5["vis"] != "flex", f"Wizard reappeared after reload: {res5}"
    assert res5["onboarded"] is True and res5["profile"] is True, f"Lost state: {res5}"
    out["5_reload_sin_wizard"] = "OK: wizard hidden after reload"

    # 6. Esc does not cancel the mandatory setup
    pg.evaluate(
        """() => {
        delete D.profile;
        D.onboarded = false;
        D.onboardStep = 1;
        save();
        showOnboarding();
    }"""
    )
    pg.wait_for_timeout(100)
    pg.keyboard.press("Escape")
    res6 = pg.evaluate(
        """() => ({
        open: document.getElementById('onboardingOverlay').style.display === 'flex',
        onboarded: D.onboarded === true,
        profile: D.profile || null
    })"""
    )
    assert res6["open"] is True, f"Esc closed the mandatory wizard: {res6}"
    assert res6["onboarded"] is False, f"Esc marked the intake done: {res6}"
    assert res6["profile"] is None, f"Esc created an incoherent profile: {res6}"
    pg.evaluate("obClose()")
    out["6_esc"] = "OK: Esc ignored, intake still pending"

    # 7. The slot count is the number of scheduled days, not hoursWeek.
    res7 = pg.evaluate(
        """() => {
        const mk = h => ({examDate: null, targetGrade: 'B', skills: {rue:3,w:3,l:3,sp:3},
            hoursWeek: h, days: ['mon','wed','sat'], struggles: [], strugglesDeclared: [],
            declaredAt: '2026-10-30T00:00:00Z'});
        D.diag = null; D.log = []; D.errs = [];
        D.profile = mk(2);
        const n2 = buildWeeklyPlan(D).slots.length;
        D.profile = mk(10);
        const n10 = buildWeeklyPlan(D).slots.length;
        return {n2, n10};
    }"""
    )
    assert res7 == {"n2": 3, "n10": 3}, f"Slot count did not follow the schedule: {res7}"
    out["7_slots_por_dias"] = f"OK: {res7}"

    # 8. The schedule's days are the only days with slots.
    res8 = pg.evaluate(
        """() => {
        D.profile.days = ['mon','fri'];
        D.profile.hoursWeek = 6;
        D.profile.skills = {rue:2,w:3,l:4,sp:5};
        D.settings.schedule = [{day:1,time:'15:30'},{day:5,time:'13:00'}];
        return buildWeeklyPlan(D).slots.map(s => s.day);
    }"""
    )
    assert res8, "No slots for days test"
    assert set(res8) <= {"Mon", "Fri"}, f"Slots outside chosen days: {res8}"
    assert "Mon" in res8 and "Fri" in res8, f"Chosen days missing: {res8}"
    out["8_dias_elegidos"] = f"OK: days={res8}"

    # 9. The week comes from the rotation queue: two days with no log ask for
    #    Reading part 1 and Listening part 1; two logged units move the same
    #    days to Writing and Speaking.
    res9 = pg.evaluate(
        """() => {
        const skills = () => buildWeeklyPlan(D).slots.map(s => s.units[0].skill);
        D.log = [];
        const empty = skills();
        D.log = [
            {date: '2026-10-01', type: 'ue', part: 1, min: 8},
            {date: '2026-10-02', type: 'lp', part: 1, min: 10}
        ];
        const moved = skills();
        D.log = [];
        return {empty, moved};
    }"""
    )
    assert res9 == {"empty": ["rue", "l"], "moved": ["w", "sp"]}, (
        f"The week is not the queue at the logged position: {res9}"
    )
    out["9_cola_por_posicion"] = f"OK: {res9}"

    # 10. The intake ratings and declared struggles do not add or reorder
    #     sessions: the week is still one session per scheduled day.
    res10 = pg.evaluate(
        """() => {
        const skills = () => buildWeeklyPlan(D).slots.map(s => s.units[0].skill);
        const before = skills();
        D.profile.skills = {rue: 1, w: 5, l: 1, sp: 5};
        D.profile.struggles = ['G-ERR'];
        D.profile.strugglesDeclared = ['Grammar accuracy'];
        const after = skills();
        return {before, after};
    }"""
    )
    assert res10["after"] == res10["before"], f"Intake reordered the week: {res10}"
    assert len(res10["after"]) == 2, f"Intake changed the session count: {res10}"
    out["10_intake_sin_efecto"] = f"OK: {res10}"

    # 11. Today countdown uses profile.examDate (+ chip when missing)
    pg.evaluate(
        """() => {
        D.profile = {examDate: '2027-06-12', targetGrade: 'A', skills: {rue:3,w:2,l:3,sp:2},
            hoursWeek: 6, days: ['mon','wed','sat'], struggles: [], strugglesDeclared: [],
            declaredAt: '2026-10-30T12:00:00Z'};
        D.examDates = [];
        save(); refreshAll();
    }"""
    )
    res11 = pg.evaluate(
        """() => ({
        display: document.getElementById('examCountdown').style.display,
        text: document.getElementById('examCountdown').textContent
    })"""
    )
    assert res11["display"] == "none", f"Countdown did not accept profile.examDate: {res11}"
    res11b = pg.evaluate(
        """() => {
        D.profile.examDate = null; D.examDates = [];
        save(); refreshAll();
        return document.getElementById('examCountdown').textContent;
    }"""
    )
    assert "Set your exam date" in res11b, f"Missing chip: {res11b}"
    out["11_countdown_perfil"] = "OK: card hides with profile.examDate + shows 'Set your exam date' without one"

    # 12. "Edit my intake" reopens with the current values prefilled (2 inputs)
    pg.evaluate(
        """() => {
        D.profile.examDate = '2027-06-12'; D.profile.targetGrade = 'A';
        save(); refreshAll();
    }"""
    )
    pg.click("nav button[data-view='plan']")
    pg.click("button:has-text('Edit my intake')")
    pg.wait_for_timeout(150)
    res12 = pg.evaluate(
        """() => ({
        open: document.getElementById('onboardingOverlay').style.display === 'flex',
        date: document.getElementById('obExamDate').value,
        grade: (document.querySelector("input[name='obGrade']:checked") || {}).value,
        step: document.getElementById('obStepCount').textContent.trim()
    })"""
    )
    assert res12["open"] is True, f"Edit my intake did not open: {res12}"
    assert res12["date"] == "2027-06-12", f"Exam date not prefilled: {res12}"
    assert res12["grade"] == "A", f"Target grade not prefilled: {res12}"
    out["12_edit_my_intake"] = f"OK: prefilled date={res12['date']} grade={res12['grade']} (step {res12['step']})"

    # 13. "Replay the app tour" relaunches the coach marks (no reload)
    pg.evaluate("obClose()")
    pg.click("#tourReplayBtn")
    pg.wait_for_timeout(250)
    res13 = pg.evaluate(
        """() => ({
        visible: document.getElementById('tourCard').style.display === 'block',
        title: document.getElementById('tourTitle').textContent,
        count: document.getElementById('tourCount').textContent.trim()
    })"""
    )
    assert res13["visible"] is True, f"Tour did not relaunch: {res13}"
    assert res13["title"].strip(), f"Coach mark without title: {res13}"
    assert res13["count"] == "1/7", f"Tour did not start at 1/7: {res13}"
    out["13_walkthrough_again"] = f"OK: tour relaunched ({res13['title']})"

    # 14. A coach mark whose target is not visible is skipped
    pg.evaluate(
        """() => {
        document.getElementById('streakTopPill').style.display = 'none';
        TOUR.i = TOUR_STEPS.length - 1;
        tourShow();
    }"""
    )
    pg.wait_for_timeout(300)
    res14 = pg.evaluate(
        """() => ({
        card: document.getElementById('tourCard').style.display,
        active: TOUR.active === true
    })"""
    )
    assert res14["card"] == "none" and res14["active"] is False, f"Invisible step not skipped: {res14}"
    pg.evaluate("document.getElementById('streakTopPill').style.display = ''")
    out["14_saltea_invisible"] = "OK: hidden target skipped, tour ended"

    # Empty states travel intact (Today / Charts / Errors)
    res_e = pg.evaluate(
        """() => {
        D.log = []; D.errs = []; save(); refreshAll();
        return {
            today: document.getElementById('recentList').textContent,
            charts: document.getElementById('progChartsEmpty').textContent,
            errors: document.getElementById('errList').textContent
        };
    }"""
    )
    assert "Your first session takes 15 seconds" in res_e["today"], res_e["today"]
    assert "Your charts unlock after your first session" in res_e["charts"], res_e["charts"]
    assert "Tag a miss after a practice test" in res_e["errors"], res_e["errors"]
    out["empty_states"] = "OK: Today / Charts / Errors copy"

    # 15. No JS errors across the whole run
    assert errs == [], f"JS errors: {errs}"
    out["15_errores_js"] = errs

    pg.evaluate(
        "localStorage.removeItem('b2first_tracker_v1_owner'); localStorage.removeItem('b2first_user');"
    )
    b.close()

srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=2))
