"""Phase 88: the custom plan editor is usable with a keyboard and a screen reader.

Every select and field carries an aria-label with its day, every control is at
least 44x44 px, Tab walks the rows in the visual order (skill, parts, minutes
for Mon, then Tue...), and parts outside the paper's range show an inline
error instead of being dropped silently. Both dictionaries carry the strings.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

SEED_JS = """() => {
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
    D.settings.rotationMode = 'custom';
    D.settings.customPlan = {
        Mon: {skill: 'rue', parts: '1,3', min: 50},
        Tue: {skill: 'l', parts: '1-4', min: 40},
        Wed: {skill: 'sp', parts: '2', min: 30},
        Thu: {skill: 'rue', parts: '', min: 45},
    };
    CUSTOM_PLAN_DRAFT = {};
    save();
    refreshAll();
}"""

CONTROLS_JS = """() => {
    const rows = Array.prototype.map.call(
        document.querySelectorAll('#wpCustomEditor .wp-custom-row'),
        row => {
            const box = el => {
                const r = el.getBoundingClientRect();
                return {w: Math.round(r.width), h: Math.round(r.height)};
            };
            const fields = ['.wp-custom-skill', '.wp-custom-parts', '.wp-custom-min'];
            return {
                day: row.dataset.day,
                fields: fields.map(sel => {
                    const el = row.querySelector(sel);
                    return {
                        cls: sel.slice(1),
                        label: el.getAttribute('aria-label'),
                        w: box(el).w,
                        h: box(el).h,
                        disabled: !!el.disabled,
                    };
                }),
                error: row.querySelector('.wp-custom-err') ? {
                    id: row.querySelector('.wp-custom-err').id,
                    text: row.querySelector('.wp-custom-err').textContent,
                    role: row.querySelector('.wp-custom-err').getAttribute('role'),
                } : null,
                partsInvalid: row.querySelector('.wp-custom-parts').getAttribute('aria-invalid'),
                describedBy: row.querySelector('.wp-custom-parts').getAttribute('aria-describedby'),
                partsValue: row.querySelector('.wp-custom-parts').value,
            };
        }
    );
    return rows;
}"""


def row_by_day(rows, day):
    return next(r for r in rows if r["day"] == day)


def focused(pg):
    return pg.evaluate(
        """() => {
            const el = document.activeElement;
            const row = el && el.closest ? el.closest('.wp-custom-row') : null;
            return {day: row ? row.dataset.day : null, cls: el ? el.className : null};
        }"""
    )


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
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(250)

    # 1. Every control has an aria-label naming its field and day, and the
    #    small inputs are still at least 44x44 px.
    rows = pg.evaluate(CONTROLS_JS)
    assert [r["day"] for r in rows] == ["Mon", "Tue", "Wed", "Thu"], (
        f"the editor did not render one row per chosen day: {[r['day'] for r in rows]}"
    )
    long_days = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday"}
    expected_words = {"wp-custom-skill": "Skill", "wp-custom-parts": "Parts", "wp-custom-min": "Minutes"}
    for row in rows:
        for f in row["fields"]:
            label = f["label"] or ""
            assert label, f"{row['day']} {f['cls']} has no aria-label: {row}"
            assert long_days[row["day"]] in label, (
                f"{row['day']} {f['cls']} label does not name the day: {label!r}"
            )
            assert expected_words[f["cls"]] in label, (
                f"{row['day']} {f['cls']} label does not name the field: {label!r}"
            )
            assert f["w"] >= 44 and f["h"] >= 44, (
                f"{row['day']} {f['cls']} hit area is {f['w']}x{f['h']}, under 44x44"
            )
    OUT["1_labels_and_targets"] = rows

    # 2. Tab order is the visual one: skill -> parts -> minutes, row by row.
    pg.focus("#wpCustomEditor .wp-custom-row .wp-custom-skill")
    assert focused(pg) == {"day": "Mon", "cls": "wp-custom-skill"}, (
        f"focus did not start on the first skill: {focused(pg)}"
    )
    order = [focused(pg)]
    for _ in range(11):
        pg.keyboard.press("Tab")
        order.append(focused(pg))
    expected = []
    for day in ("Mon", "Tue", "Wed", "Thu"):
        for cls in ("wp-custom-skill", "wp-custom-parts", "wp-custom-min"):
            expected.append({"day": day, "cls": cls})
    assert order == expected, f"tab order is not logical: {order}"
    OUT["2_tab_order"] = order

    # 3. A part outside the paper's range shows an inline, announced error and
    #    that day falls back instead of being saved with a broken list.
    pg.fill("#wpCustomEditor .wp-custom-row[data-day='Mon'] .wp-custom-parts", "9")
    pg.dispatch_event(
        "#wpCustomEditor .wp-custom-row[data-day='Mon'] .wp-custom-parts", "change"
    )
    pg.wait_for_timeout(300)
    bad = row_by_day(pg.evaluate(CONTROLS_JS), "Mon")
    assert bad["error"], f"an out-of-range part was accepted silently: {bad}"
    assert bad["error"]["role"] == "alert", f"the inline error is not announced: {bad}"
    assert "1" in bad["error"]["text"] and "7" in bad["error"]["text"], (
        f"the error does not name the valid range: {bad['error']['text']!r}"
    )
    assert bad["partsInvalid"] == "true", f"the field is not marked invalid: {bad}"
    assert bad["describedBy"] == bad["error"]["id"], (
        f"the field does not point at its error: {bad}"
    )
    assert bad["partsValue"] == "9", f"the typed value was thrown away: {bad}"
    stored = pg.evaluate("() => D.settings.customPlan")
    assert "Mon" not in stored, f"an invalid day was saved anyway: {stored}"
    OUT["3_inline_error"] = {"row": bad, "stored": stored}

    # 4. Fixing the value clears the error and saves the day again.
    pg.fill("#wpCustomEditor .wp-custom-row[data-day='Mon'] .wp-custom-parts", "1,3")
    pg.dispatch_event(
        "#wpCustomEditor .wp-custom-row[data-day='Mon'] .wp-custom-parts", "change"
    )
    pg.wait_for_timeout(300)
    fixed = row_by_day(pg.evaluate(CONTROLS_JS), "Mon")
    assert fixed["error"] is None, f"the inline error survived a valid value: {fixed}"
    assert fixed["partsInvalid"] == "false", f"the field is still marked invalid: {fixed}"
    assert pg.evaluate("() => D.settings.customPlan.Mon.parts") == [1, 3], (
        "the fixed day was not saved"
    )
    assert pg.evaluate("() => CUSTOM_PLAN_DRAFT.Mon === undefined"), (
        "the draft survived after the value became valid"
    )
    OUT["4_error_clears"] = fixed

    # 5. Dates/ranges out of bounds are caught too, not just single numbers.
    pg.fill("#wpCustomEditor .wp-custom-row[data-day='Thu'] .wp-custom-parts", "5-9")
    pg.dispatch_event(
        "#wpCustomEditor .wp-custom-row[data-day='Thu'] .wp-custom-parts", "change"
    )
    pg.wait_for_timeout(300)
    rng = row_by_day(pg.evaluate(CONTROLS_JS), "Thu")
    assert rng["error"] and rng["error"]["role"] == "alert", (
        f"an out-of-range range was accepted: {rng}"
    )
    OUT["5_range_error"] = rng

    # 6. Spanish: the same strings come from the second dictionary.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    es = pg.evaluate(CONTROLS_JS)
    mon = row_by_day(es, "Mon")
    assert mon["fields"][1]["label"] == "Partes para Lunes", (
        f"the Spanish aria-label is missing: {mon['fields'][1]['label']!r}"
    )
    thu = row_by_day(es, "Thu")
    assert thu["error"] and "entre 1 y 7" in thu["error"]["text"], (
        f"the Spanish inline error is missing: {thu}"
    )
    keys = pg.evaluate(
        """() => ['plan_custom_skill','plan_custom_parts','plan_custom_min',
                    'plan_custom_parts_error']
            .filter(k => !I18N.en[k] || !I18N.es[k])"""
    )
    assert keys == [], f"keys missing from a dictionary: {keys}"
    OUT["6_spanish"] = {"label": mon["fields"][1]["label"], "error": thu["error"], "keys": keys}

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
