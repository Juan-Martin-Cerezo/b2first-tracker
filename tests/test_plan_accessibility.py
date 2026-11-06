"""Phase 100: the Plan screen works with a keyboard and names its targets.

1. The week plan container is an aria-live region, so a repaint is announced
   instead of silently replacing the rows.
2. Every day row is its own keyboard stop (`tabindex="0"`, `role="group"`,
   `aria-label` naming the day and the unit) and paints a visible focus ring.
3. Each row's Start button carries an `aria-label` that names the unit it
   starts, in both dictionaries, instead of the bare word "Start".
4. Every visible button of the week plan and the session schedules measures at
   least 44x44 px.

Run:  uv run --with playwright python test_plan_accessibility.py
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

READ_ROWS = """() => {
    const box = document.getElementById('wpRows');
    const rows = Array.from(box.querySelectorAll('.wp-row'));
    return {
        live: box.getAttribute('aria-live'),
        rows: rows.map((r, i) => {
            const b = r.querySelector('.wp-start');
            const br = b.getBoundingClientRect();
            const slot = WEEK_PLAN.slots[i];
            return {
                tabindex: r.getAttribute('tabindex'),
                role: r.getAttribute('role'),
                rowLabel: (r.getAttribute('aria-label') || '').trim(),
                title: (r.querySelector('.wp-title') || {textContent: ''}).textContent.trim(),
                startLabel: (b.getAttribute('aria-label') || '').trim(),
                startText: b.textContent.trim(),
                expectedStart: t('plan_start_aria', {unit: slotTitleText(slot)}),
                expectedRow: t('plan_row_aria', {
                    day: planDayFull(slot.day), unit: slotTitleText(slot)}),
                w: br.width, h: br.height,
            };
        }),
        smallTargets: Array.from(document.querySelectorAll(
                '#weeklyPlanCard button, #schedulesCard button'))
            .filter(el => {
                const r = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                return r.width > 0 && r.height > 0 &&
                    cs.visibility !== 'hidden' && cs.display !== 'none';
            })
            .map(el => {
                const r = el.getBoundingClientRect();
                return {text: el.textContent.trim().slice(0, 24),
                        w: r.width, h: r.height};
            })
            .filter(x => x.w < 43.5 || x.h < 43.5),
    };
}"""


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
    pg.evaluate(SEED_BY_PART)
    pg.wait_for_timeout(300)

    state = pg.evaluate(READ_ROWS)
    assert state["live"] == "polite", (
        f"the week plan is not an aria-live region: {state['live']!r}")
    assert len(state["rows"]) == 4, f"expected four day rows: {state}"
    OUT["1_live_and_rows"] = {"live": state["live"], "rows": len(state["rows"])}

    # 2. Day rows: keyboard stops, named, and their Start names the unit.
    for i, row in enumerate(state["rows"]):
        assert row["tabindex"] == "0", f"row {i} is not a keyboard stop: {row}"
        assert row["role"] == "group", f"row {i} has no group role: {row}"
        assert row["rowLabel"] == row["expectedRow"], (
            f"row {i} label does not name its day and unit: {row}")
        assert row["rowLabel"] != "", f"row {i} has no label: {row}"
        assert row["startLabel"] == row["expectedStart"], (
            f"row {i} Start label does not name the unit: {row}")
        assert row["startLabel"].startswith("Start "), (
            f"row {i} Start label is not in English: {row}")
        assert row["startLabel"] != row["startText"], (
            f"row {i} Start label is just the visible word: {row}")
        assert row["w"] >= 43.5 and row["h"] >= 43.5, (
            f"row {i} Start is under 44x44: {row}")
    OUT["2_rows"] = [
        {"title": r["title"], "rowLabel": r["rowLabel"],
         "startLabel": r["startLabel"]} for r in state["rows"]
    ]

    # 3. Keyboard: from the control before the rows, Tab lands on the first
    # row (a real keyboard stop, with a visible ring), then on its Start.
    pg.focus("#wpItemsPerSession")
    pg.keyboard.press("Tab")
    focused = pg.evaluate("""() => {
        const el = document.activeElement;
        const cs = getComputedStyle(el);
        return {
            isRow: el.classList.contains('wp-row'),
            first: el === document.querySelector('#wpRows .wp-row'),
            label: el.getAttribute('aria-label') || '',
            outline: cs.outlineStyle,
            outlineWidth: parseFloat(cs.outlineWidth) || 0,
        };
    }""")
    assert focused["isRow"] and focused["first"], (
        f"Tab did not land on the first day row: {focused}")
    assert focused["outline"] != "none" and focused["outlineWidth"] > 0, (
        f"the focused day row paints no visible ring: {focused}")
    OUT["3_tab"] = focused

    pg.keyboard.press("Tab")
    assert pg.evaluate(
        "document.activeElement.classList.contains('wp-start')"), (
        "Tab from the row did not reach its Start button")

    # 4. Spanish: the same labels come from the second dictionary.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    es = pg.evaluate(READ_ROWS)
    assert len(es["rows"]) == 4, f"the rows vanished in Spanish: {es}"
    for i, row in enumerate(es["rows"]):
        assert row["startLabel"] == row["expectedStart"], (
            f"row {i} Start label is not localised: {row}")
        assert row["startLabel"].startswith("Empezar "), (
            f"row {i} Start label stayed in English: {row}")
        assert row["rowLabel"] == row["expectedRow"], (
            f"row {i} row label is not localised: {row}")
    assert es["rows"][0]["startLabel"] != state["rows"][0]["startLabel"], (
        "Spanish and English produced the same Start label")
    OUT["4_spanish"] = es["rows"][0]["startLabel"]

    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(300)

    # 5. Targets: nothing interactive in the plan rows or the schedules is
    # under 44x44 px.
    final = pg.evaluate(READ_ROWS)
    assert final["smallTargets"] == [], (
        f"targets under 44x44 on the Plan screen: {final['smallTargets']}")
    OUT["5_targets_ok"] = True

    # 6. Both dictionaries carry the keys the labels use.
    keys = pg.evaluate(
        """() => ['plan_start_aria', 'plan_row_aria']
            .filter(k => !I18N.en[k] || !I18N.es[k])"""
    )
    assert keys == [], f"keys missing from a dictionary: {keys}"

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
