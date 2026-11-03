"""Tests of the one-screen onboarding (phase 47).

The setup is a single card with three questions, everything preselected:
exam date, target grade and days + minutes. Both footer actions write the
same D.profile and set onboarded.

It boots its own server with DATA_DIR in a temporary directory (pattern
from test_sync.py): it never touches data/.
"""

import json
import os
import sys
import tempfile
import threading
import urllib.request

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S

_tmp = tempfile.mkdtemp(prefix="b2onboard-")
S.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.PORT = 0
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

    # 1. First visit: one screen, no step counter and no progress bar.
    pg.wait_for_selector("#onboardingOverlay", state="visible", timeout=5000)
    res1 = pg.evaluate(
        """() => ({
        visible: document.getElementById('onboardingOverlay').style.display === 'flex',
        hasStep: !!document.getElementById('obStepCount'),
        hasProgress: !!document.getElementById('obProgressFill'),
        title: document.getElementById('obTitle').textContent.trim(),
        start: document.getElementById('obStartBtn').textContent.trim(),
        skip: document.getElementById('obSkipBtn').textContent.trim(),
    })"""
    )
    assert res1["visible"] and not res1["hasStep"] and not res1["hasProgress"], res1
    assert res1["title"], "One-screen onboarding has no title"

    # 2. Preselected: grade B, Mon/Wed/Sat, 45 minutes.
    res2 = pg.evaluate(
        """() => ({
        grade: (document.querySelector("input[name='obGrade']:checked") || {}).value,
        days: [...document.querySelectorAll('.chip-btn[data-day][aria-pressed="true"]')].map(b => b.dataset.day),
        minutes: document.getElementById('obMinutes').value,
        radios: document.querySelectorAll("input[name='obGrade']").length,
    })"""
    )
    assert res2["grade"] == "B", f"grade is not B by default: {res2}"
    assert res2["days"] == ["mon", "wed", "sat"], f"days are not Mon/Wed/Sat: {res2}"
    assert res2["minutes"] == "45", f"minutes are not 45: {res2}"
    assert res2["radios"] == 3, f"expected A/B/C radios: {res2}"
    out["1_one_screen"] = res1
    out["2_preselected"] = res2

    # 3. Start studying writes the same D.profile shape and derived hoursWeek.
    pg.fill("#obExamDate", "2027-06-12")
    pg.click("input[name='obGrade'][value='A']")
    pg.click("#obStartBtn")
    pg.wait_for_timeout(250)
    res3 = pg.evaluate(
        """() => {
        const p = D.profile || {};
        return {
            onboarded: D.onboarded === true,
            examDate: p.examDate, examDateUnknown: p.examDateUnknown,
            targetGrade: p.targetGrade, days: p.days, hoursWeek: p.hoursWeek,
            minutes: p.minutes, skills: p.skills, struggles: p.struggles,
            declaredAt: typeof p.declaredAt === 'string' && p.declaredAt.length > 0,
            open: document.getElementById('onboardingOverlay').style.display === 'flex',
        };
    }"""
    )
    assert res3["onboarded"] is True and res3["open"] is False, f"not closed/onboarded: {res3}"
    assert res3["examDate"] == "2027-06-12" and res3["examDateUnknown"] is False, res3
    assert res3["targetGrade"] == "A", res3
    assert res3["days"] == ["mon", "wed", "sat"], res3
    assert res3["hoursWeek"] == 2.25, f"hoursWeek not days×minutes/60: {res3}"
    assert res3["skills"] == {"rue": 3, "w": 3, "l": 3, "sp": 3}, res3
    assert res3["struggles"] == [], res3
    assert res3["declaredAt"] is True, res3
    out["3_start"] = res3

    # 4. Reload: the setup does not come back.
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(500)
    res4 = pg.evaluate(
        "() => ({vis: document.getElementById('onboardingOverlay').style.display, onboarded: D.onboarded === true})"
    )
    assert res4["vis"] != "flex" and res4["onboarded"] is True, res4
    out["4_reload"] = "OK: no wizard after reload"

    # 5. "I don't know yet" + Skip for now still writes the profile and onboarded.
    pg.evaluate(
        """() => { delete D.profile; D.onboarded = false; save(); showOnboarding(); }"""
    )
    pg.click("#obDateUnknown")
    pg.click("#obSkipBtn")
    pg.wait_for_timeout(200)
    res5 = pg.evaluate(
        """() => ({
        onboarded: D.onboarded === true,
        open: document.getElementById('onboardingOverlay').style.display === 'flex',
        profile: D.profile && {examDate: D.profile.examDate, unknown: D.profile.examDateUnknown,
            grade: D.profile.targetGrade, days: D.profile.days, hoursWeek: D.profile.hoursWeek},
    })"""
    )
    assert res5["onboarded"] is True and res5["open"] is False, res5
    assert res5["profile"]["unknown"] is True and res5["profile"]["examDate"] is None, res5
    out["5_skip"] = res5

    # 6. Edit my intake reopens prefilled; Escape behaves like Skip.
    pg.evaluate(
        """() => {
        D.onboarded = true;
        D.profile = {examDate: '2027-06-12', targetGrade: 'A', days: ['mon','fri'], minutes: 30,
            hoursWeek: 2, skills: {rue:3,w:3,l:3,sp:3}, struggles: [], declaredAt: '2026-10-30T00:00:00Z'};
        save(); refreshAll(); showView('plan');
    }"""
    )
    pg.click("button:has-text('Edit my intake')")
    pg.wait_for_timeout(150)
    res6 = pg.evaluate(
        """() => ({
        open: document.getElementById('onboardingOverlay').style.display === 'flex',
        date: document.getElementById('obExamDate').value,
        grade: (document.querySelector("input[name='obGrade']:checked") || {}).value,
        minutes: document.getElementById('obMinutes').value,
        days: [...document.querySelectorAll('.chip-btn[data-day][aria-pressed="true"]')].map(b => b.dataset.day),
    })"""
    )
    assert res6["open"] is True and res6["date"] == "2027-06-12", res6
    assert res6["grade"] == "A" and res6["minutes"] == "30", res6
    assert res6["days"] == ["mon", "fri"], res6
    out["6_edit_intake"] = res6
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('onboardingOverlay').style.display") != "flex"
    assert pg.evaluate("D.onboarded === true")

    # 7. The tour is reachable from the account menu (not from Plan's header).
    assert pg.evaluate("!document.querySelector('#v-plan #tourReplayBtn')")
    pg.evaluate("openUserModal()")
    pg.wait_for_timeout(100)
    pg.click("#tourReplayBtn")
    pg.wait_for_timeout(200)
    res7 = pg.evaluate(
        "() => ({visible: document.getElementById('tourCard').style.display === 'block'})"
    )
    assert res7["visible"] is True, f"tour did not open from the account menu: {res7}"
    pg.evaluate("endTour()")
    out["7_tour_account"] = res7

    # 8. hoursWeek feeds the plan builder; 2 days × 60 min -> 2 hours -> 3 slots.
    res8 = pg.evaluate(
        """() => {
        D.profile = {examDate: null, targetGrade: 'B', days: ['mon','fri'], minutes: 60,
            hoursWeek: 2, skills: {rue:3,w:3,l:3,sp:3}, struggles: [], declaredAt: '2026-10-30T00:00:00Z'};
        D.diag = null; D.log = []; D.errs = [];
        return buildWeeklyPlan(D).slots.length;
    }"""
    )
    assert res8 == 3, f"2 hours a week should build 3 slots: {res8}"
    out["8_hoursweek"] = res8

    # 9. No JS errors across the run.
    assert errs == [], f"JS errors: {errs}"
    out["9_errors"] = errs

    pg.evaluate(
        "localStorage.removeItem('b2first_tracker_v1_owner'); localStorage.removeItem('b2first_user');"
    )
    b.close()

srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=2))
