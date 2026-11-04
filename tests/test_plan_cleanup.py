"""Phase 84: the PLAN screen is reduced to what it should show.

The exam-timer card and the thresholds card are gone, so the app always uses the
SETTINGS_DEFAULT durations. The progression matrix is the only place where the
stage gates live, and the provider card moved to the settings panel opened by
the header gear.
"""
import json
import os

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

REMOVED_IDS = [
    "pUeMin", "pListenMin", "pPlanMin", "pWriteMin", "pRevMin",
    "pSp1Sec", "pSp2Sec", "pWMin", "pWMax", "pStreakFreeze", "pWeekGoal",
    "pE0w", "pE0u", "pE0l", "pE1w", "pE1wm", "pE1u", "pE1l",
    "pE2r", "pE2rm", "pE2w", "pE2l", "pE2ln",
]

out = {}
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
    pg.wait_for_timeout(300)

    # 1. The timer and threshold inputs do not exist anywhere in the DOM.
    present = [
        node_id for node_id in REMOVED_IDS
        if pg.evaluate(f"!!document.getElementById('{node_id}')")
    ]
    assert not present, f"removed inputs still in the DOM: {present}"
    out["1_removed_inputs"] = REMOVED_IDS

    # 2. PLAN no longer mentions the timer or threshold cards.
    plan_text = pg.evaluate("document.getElementById('v-plan').innerText")
    assert "Exam Timers" not in plan_text, "PLAN still shows Exam Timers"
    assert "Thresholds" not in plan_text, "PLAN still shows Thresholds"
    out["2_plan_text"] = plan_text[:160]

    # 3. Exam durations read the defaults without touching any input.
    defaults = pg.evaluate(
        """() => ({
            listening_exam: EX_DUR.l,
            listening_timer: SETTINGS_DEFAULT.listenMin,
            speaking_p2: SETTINGS_DEFAULT.sp1Sec,
            speaking_p34: SETTINGS_DEFAULT.sp2Sec,
        })"""
    )
    assert defaults == {
        "listening_exam": 40 * 60,
        "listening_timer": 40,
        "speaking_p2": 60,
        "speaking_p34": 180,
    }, f"durations are not the defaults: {defaults}"
    pg.evaluate("applyTimers()")
    assert pg.inner_text("#lTimer").strip() == "40:00", "Listening timer is not 40 min"
    out["3_defaults"] = defaults

    # 4. The progression matrix: three stages x four skills, every cell covers
    #    all the parts of its skill.
    pg.evaluate("showView('prog')")
    pg.wait_for_timeout(400)
    header = pg.eval_on_selector_all(
        "#gates thead th", "els => els.map(e => e.innerText.trim().toLowerCase())"
    )
    assert header == ["stage", "r&ue", "listening", "writing", "speaking"], (
        f"matrix header is wrong: {header}"
    )
    rows = pg.eval_on_selector_all(
        "#gates tbody tr",
        """rows => rows.map(r => ({
            stage: r.querySelector('th').innerText.trim(),
            cells: [...r.querySelectorAll('td')].map(td => td.innerText.trim()),
            status: (r.querySelector('.gate-status') || {}).innerText || '',
        }))""",
    )
    assert len(rows) == 3, f"matrix does not have three stages: {rows}"
    for row in rows:
        assert len(row["cells"]) == 4, f"stage row is not skill-wide: {row}"
        assert row["status"].lower() in ("achieved", "pending"), f"bad stage status: {row}"
        for cell in row["cells"]:
            assert ("1–7" in cell) or ("each part" in cell), (
                f"cell does not cover all the parts: {cell!r}"
            )
    assert all("pending" in row["status"].lower() for row in rows), (
        "an empty user should not have an achieved stage"
    )
    assert pg.eval_on_selector_all("#gates input", "els => els.length") == 0, (
        "the matrix still has inputs"
    )
    pg.locator("#gates").screenshot(path=os.path.join(OUT, "progression_matrix.png"))
    out["4_matrix"] = rows

    # 5. The provider card lives in the settings panel, never in PLAN.
    assert pg.evaluate(
        "document.getElementById('settingsModal').contains(document.getElementById('byoCard'))"
    ), "#byoCard is not inside the settings panel"
    assert not pg.evaluate(
        "document.getElementById('v-plan').contains(document.getElementById('byoCard'))"
    ), "#byoCard is still inside #v-plan"
    assert not pg.evaluate("!!document.querySelector('#v-plan #byoCard')"), (
        "#byoCard still matches inside #v-plan"
    )
    lowered = plan_text.lower()
    assert "provider" not in lowered, "PLAN still mentions the provider"
    assert "api key" not in lowered, "PLAN still mentions the API key"
    out["5_provider_in_settings"] = True

    # 6. DOM order inside #v-plan: countdown, week plan, schedules, language,
    #    subscription, what comes next. Nothing sits between week plan and
    #    schedules.
    order = pg.evaluate(
        """() => {
        const ids = ['examCountdown', 'weeklyPlanCard', 'schedulesCard',
                     'languageCard', 'planStatusCard', 'rotationCard'];
        const els = ids.map(id => document.getElementById(id));
        const v = document.getElementById('v-plan');
        return {
            ids,
            missing: ids.filter((id, i) => !els[i] || !v.contains(els[i])),
            chained: els.every((el, i) => i === 0 || (els[i - 1] && els[i - 1].nextElementSibling === el)),
            week_next: document.getElementById('weeklyPlanCard').nextElementSibling
                ? document.getElementById('weeklyPlanCard').nextElementSibling.id : null,
        };
        }"""
    )
    assert not order["missing"], f"PLAN cards missing: {order}"
    assert order["chained"], f"PLAN cards are not in the required order: {order}"
    assert order["week_next"] == "schedulesCard", (
        f"something sits between week plan and schedules: {order}"
    )
    out["6_order"] = order

    # 7. The Week plan card now owns the rotation mode: a selector above the
    #    day rows, the one-line help and both escape hatches.
    rotation = pg.evaluate(
        """() => {
        const card = document.getElementById('weeklyPlanCard');
        const mode = document.getElementById('wpRotationMode');
        const rows = document.getElementById('wpRows');
        const children = [...card.children];
        return {
            mode: mode ? mode.value : null,
            options: mode ? [...mode.options].map(o => o.value) : [],
            help: (document.getElementById('wpRotationHelp') || {}).textContent || '',
            reset: !!document.getElementById('wpResetBtn'),
            undo: !!document.getElementById('wpUndoBtn'),
            above_rows: children.indexOf(document.getElementById('wpRotationControls')) <
                children.indexOf(rows),
        };
        }"""
    )
    assert rotation["mode"] == "by-part", f"default rotation mode is not by-part: {rotation}"
    assert rotation["options"] == ["by-part", "full-section", "custom"], (
        f"rotation modes are wrong: {rotation}"
    )
    assert rotation["help"].strip(), f"the mode has no one-line help: {rotation}"
    assert rotation["reset"] and rotation["undo"], f"escape hatches missing: {rotation}"
    assert rotation["above_rows"], f"the mode selector is not above the day rows: {rotation}"
    out["7_rotation_mode"] = rotation

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
