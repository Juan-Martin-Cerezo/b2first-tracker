"""Phase 89: the week plan shows its real totals, not an estimate.

The summary line under "Week plan" adds the minutes of the slots
buildWeeklyPlan produced and splits them by skill. It appears only when there
is a plan, and two different plans must produce two different lines.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

SEED_BY_PART = """() => {
    D.profile = {
        examDate: null, targetGrade: 'B',
        skills: {rue: 3, w: 3, l: 3, sp: 3},
        hoursWeek: 4, days: ['mon', 'tue', 'wed', 'thu'],
        struggles: [], strugglesDeclared: [],
    };
    D.diag = null;
    D.log = [];
    D.errs = [];
    D.sessionOffset = 0;
    D.settings.schedule = [{day:1,time:'15:30'},{day:2,time:'13:00'},{day:3,time:'10:00'},{day:4,time:'18:00'}];
    D.settings.rotationMode = 'by-part';
    save();
    refreshAll();
}"""

SEED_FULL_SECTION = """() => {
    D.profile = {
        examDate: null, targetGrade: 'B',
        skills: {rue: 3, w: 3, l: 3, sp: 3},
        hoursWeek: 10, days: ['mon', 'tue', 'wed', 'thu', 'fri'],
        struggles: [], strugglesDeclared: [],
    };
    D.diag = null;
    D.log = [];
    D.errs = [];
    D.sessionOffset = 0;
    D.settings.schedule = [{day:1,time:'15:30'},{day:2,time:'13:00'},{day:3,time:'10:00'},{day:4,time:'18:00'},{day:5,time:'17:00'}];
    D.settings.rotationMode = 'full-section';
    save();
    refreshAll();
}"""

SEED_NO_PLAN = """() => {
    D.profile = null;
    D.diag = null;
    D.log = [];
    D.errs = [];
    D.sessionOffset = 0;
    D.settings.rotationMode = 'by-part';
    save();
    refreshAll();
}"""

READ_JS = """() => {
    const el = document.getElementById('wpSummary');
    const plan = buildWeeklyPlan(D);
    const bySkill = {};
    let total = 0;
    plan.slots.forEach(sl => {
        const skill = sl.type === 'ue' ? 'rue' : sl.type;
        total += Number(sl.min) || 0;
        bySkill[skill] = (bySkill[skill] || 0) + (Number(sl.min) || 0);
    });
    return {
        text: el ? el.textContent.trim() : null,
        visible: !!el && el.style.display !== 'none' && el.textContent.trim() !== '',
        needDiag: !!plan.needDiag,
        plan: {total: total, count: plan.slots.length, bySkill: bySkill},
    };
}"""


def assert_line_matches_plan(state, label="summary"):
    assert state["visible"], f"{label}: the summary line is not visible: {state}"
    text = state["text"]
    plan = state["plan"]
    assert plan["count"] > 0 and plan["total"] > 0, f"{label}: empty plan: {state}"
    assert f"{plan['total']} min" in text, (
        f"{label}: the total is not the plan total ({plan['total']}): {text!r}"
    )
    assert f"{plan['count']} sessions" in text or plan["count"] == 1, (
        f"{label}: the session count is not the plan count ({plan['count']}): {text!r}"
    )
    for skill, minutes in plan["bySkill"].items():
        assert f"{minutes} min" in text, (
            f"{label}: {skill} minutes ({minutes}) are missing from: {text!r}"
        )
    return text


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

    # 1. By-part plan: each slot is timed by its unit (8+10+40+2 = 60 min).
    pg.evaluate(SEED_BY_PART)
    pg.wait_for_timeout(300)
    a = pg.evaluate(READ_JS)
    text_a = assert_line_matches_plan(a, "by-part")
    assert a["plan"]["total"] == 60 and a["plan"]["count"] == 4, (
        f"the by-part plan is not the sum of its units: {a['plan']}"
    )
    assert "This week: 60 min across 4 sessions" in text_a, (
        f"unexpected summary line: {text_a!r}"
    )
    OUT["1_by_part"] = a

    # 2. Full-paper plan: five official papers, 75+40+80+14+75 = 284 min,
    #    split per skill from the slots themselves.
    pg.evaluate(SEED_FULL_SECTION)
    pg.wait_for_timeout(300)
    b = pg.evaluate(READ_JS)
    text_b = assert_line_matches_plan(b, "full-section")
    assert b["plan"]["total"] == 284, f"the full-paper week is not 284 min: {b['plan']}"
    assert b["plan"]["bySkill"] == {"rue": 150, "l": 40, "w": 80, "sp": 14}, (
        f"the per-skill split is wrong: {b['plan']['bySkill']}"
    )
    assert "Reading & UoE 150 min" in text_b, f"R&UoE minutes missing: {text_b!r}"
    assert "Listening 40 min" in text_b, f"Listening minutes missing: {text_b!r}"
    assert "Writing 80 min" in text_b, f"Writing minutes missing: {text_b!r}"
    assert "Speaking 14 min" in text_b, f"Speaking minutes missing: {text_b!r}"
    assert text_b != text_a, "two different plans produced the same summary line"
    OUT["2_full_section"] = b

    # 3. Spanish: the same line from the second dictionary.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    es = pg.evaluate(READ_JS)
    assert es["visible"], f"the summary disappeared in Spanish: {es}"
    assert es["text"].startswith("Esta semana: 284 min en 5 sesiones"), (
        f"the Spanish summary is missing: {es['text']!r}"
    )
    assert "Reading y UoE 150 min" in es["text"], (
        f"Spanish skill labels are missing: {es['text']!r}"
    )
    OUT["3_spanish"] = es

    # 4. No plan: the line does not show.
    pg.evaluate(SEED_NO_PLAN)
    pg.wait_for_timeout(300)
    none = pg.evaluate(READ_JS)
    assert none["needDiag"], f"the seed did not leave a plan-less week: {none}"
    assert not none["visible"] and not none["text"], (
        f"the summary shows without a plan: {none}"
    )
    OUT["4_no_plan"] = none

    # 5. Both dictionaries carry the keys the line uses.
    keys = pg.evaluate(
        """() => ['plan_week_summary','plan_week_summary_item','plan_skill_mock']
            .filter(k => !I18N.en[k] || !I18N.es[k])"""
    )
    assert keys == [], f"keys missing from a dictionary: {keys}"
    OUT["5_keys"] = keys

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
