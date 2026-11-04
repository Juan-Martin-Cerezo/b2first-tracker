"""Phase 87: Reset to defaults asks first, in a real accessible dialog.

Clicking Reset opens a dialog that lists, field by field, only the settings
that actually differ from the defaults (current value → default). Escape
closes it and returns focus to the button; Tab and Shift+Tab stay inside it;
Enter on the Apply button performs the reset. Both dictionaries carry the
dialog strings, in English and Spanish.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner, dismiss_onboarding

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
    D.settings.rotationMode = 'custom';
    D.settings.rueCycle = [7, 1];
    D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
    D.settings.lCycle = [1, 2, 3, 4];
    D.settings.spCycle = [1, 2, 3, 4];
    D.settings.customPlan = {Mon: {skill: 'rue', parts: '1', min: 30}};
    SETTINGS_UNDO = null;
    delete D.settingsUndo;
    save();
    refreshAll();
}"""

DIALOG_JS = """() => {
    const ov = document.getElementById('planResetModal');
    const rows = Array.prototype.map.call(
        document.querySelectorAll('#planResetDetail li'),
        li => ({label: li.querySelector('b').textContent, value: li.querySelector('span').textContent})
    );
    return {
        open: ov.style.display !== 'none',
        title: document.getElementById('planResetTitle').textContent,
        body: document.getElementById('planResetBody').textContent,
        bodyVisible: document.getElementById('planResetBody').style.display !== 'none',
        rows: rows,
        applyEnabled: !document.getElementById('planResetApply').disabled,
        active: document.activeElement ? document.activeElement.id : null,
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
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(250)

    # 1. Keyboard opening: focus the button, press Enter, the dialog appears
    #    with focus inside it and the real diff of the five changed settings.
    pg.focus("#wpResetBtn")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(200)
    opened = pg.evaluate(DIALOG_JS)
    assert opened["open"], f"Reset did not open a dialog: {opened}"
    assert opened["active"] == "planResetCancel", (
        f"focus did not move into the dialog: {opened}"
    )
    labels = [r["label"] for r in opened["rows"]]
    assert labels == [
        "Rotation", "R&UoE cycle (parts)", "Custom plan"
    ], f"the dialog listed the wrong fields: {labels}"
    values = {r["label"]: r["value"] for r in opened["rows"]}
    assert values["Rotation"] == "Custom → By part", f"rotation detail is wrong: {values}"
    assert values["R&UoE cycle (parts)"] == "7, 1 → 1, 2, 3, 4, 5, 6, 7", (
        f"cycle detail is wrong: {values}"
    )
    assert values["Custom plan"] == "1 day(s) → none", f"custom plan detail is wrong: {values}"
    assert opened["applyEnabled"], f"Apply is disabled with pending changes: {opened}"
    assert pg.evaluate("D.settings.rotationMode") == "custom", "opening the dialog already reset"
    OUT["1_open_by_keyboard"] = opened

    # 2. Escape closes it and returns focus to the Reset button.
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(200)
    closed = pg.evaluate(
        """() => ({
            open: document.getElementById('planResetModal').style.display !== 'none',
            active: document.activeElement ? document.activeElement.id : null,
            mode: D.settings.rotationMode,
        })"""
    )
    assert not closed["open"], f"Escape did not close the dialog: {closed}"
    assert closed["active"] == "wpResetBtn", f"focus did not return to Reset: {closed}"
    assert closed["mode"] == "custom", f"Escape applied the reset anyway: {closed}"
    OUT["2_escape_closes"] = closed

    # 3. Focus is trapped: Tab from the last control wraps to the first, and
    #    Shift+Tab from the first wraps to the last.
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(200)
    pg.focus("#planResetApply")
    pg.keyboard.press("Tab")
    wrapped = pg.evaluate(
        "() => ({open: document.getElementById('planResetModal').style.display !== 'none',"
        " active: document.activeElement ? document.activeElement.id : null})"
    )
    assert wrapped["open"], f"Tab escaped the dialog: {wrapped}"
    assert wrapped["active"] == "planResetCancel", f"Tab did not wrap inside the dialog: {wrapped}"
    pg.keyboard.press("Shift+Tab")
    back = pg.evaluate(
        "() => ({open: document.getElementById('planResetModal').style.display !== 'none',"
        " active: document.activeElement ? document.activeElement.id : null})"
    )
    assert back["open"] and back["active"] == "planResetApply", (
        f"Shift+Tab did not wrap inside the dialog: {back}"
    )
    OUT["3_focus_trapped"] = {"tab": wrapped, "shift_tab": back}

    # 4. Enter on Apply performs the reset, closes the dialog and leaves one
    #    undo step.
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(400)
    applied = pg.evaluate(
        """() => ({
            open: document.getElementById('planResetModal').style.display !== 'none',
            mode: D.settings.rotationMode,
            rue: D.settings.rueCycle,
            custom: D.settings.customPlan,
            undo: SETTINGS_UNDO ? SETTINGS_UNDO.rotationMode : null,
            undoVisible: getComputedStyle(document.getElementById('wpUndoBtn')).display !== 'none',
        })"""
    )
    assert not applied["open"], f"the dialog stayed open after Apply: {applied}"
    assert applied["mode"] == "by-part", f"Apply did not reset the mode: {applied}"
    assert applied["rue"] == [1, 2, 3, 4, 5, 6, 7], f"Apply did not reset the cycle: {applied}"
    assert applied["custom"] == {}, f"Apply left the custom plan: {applied}"
    assert applied["undo"] == "custom", f"the reset was not undoable: {applied}"
    assert applied["undoVisible"], f"Undo is not offered after the reset: {applied}"
    OUT["4_apply_by_keyboard"] = applied

    # 5. With nothing to change the dialog says so and Apply is disabled.
    pg.focus("#wpResetBtn")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(200)
    nochange = pg.evaluate(DIALOG_JS)
    assert nochange["open"], f"the dialog did not open with defaults: {nochange}"
    assert nochange["rows"] == [], f"the dialog invented changes: {nochange}"
    assert not nochange["bodyVisible"], f"the 'will change' line is shown with no changes: {nochange}"
    assert pg.evaluate(
        "() => document.getElementById('planResetNone').style.display !== 'none'"
    ), "the 'already at defaults' line is hidden"
    assert not nochange["applyEnabled"], f"Apply is enabled with no changes: {nochange}"
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    OUT["5_nothing_to_change"] = nochange

    # 6. Spanish: the same dialog in the second dictionary.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(300)
    pg.evaluate(
        """() => {
            D.settings.rotationMode = 'full-section';
            save();
            refreshAll();
        }"""
    )
    pg.focus("#wpResetBtn")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(200)
    es = pg.evaluate(DIALOG_JS)
    assert es["title"] == "¿Volver la rotación a los valores por defecto?", (
        f"the Spanish title is missing: {es}"
    )
    es_values = {r["label"]: r["value"] for r in es["rows"]}
    assert es_values.get("Rotación") == "Paper completo por sesión → Por parte", (
        f"the Spanish detail is not translated: {es}"
    )
    assert pg.evaluate(
        "() => [document.getElementById('planResetCancel').textContent,"
        " document.getElementById('planResetApply').textContent]"
    ) == ["Cancelar", "Reiniciar"], "the Spanish buttons are not translated"
    pg.keyboard.press("Escape")
    OUT["6_spanish"] = es

    # 7. Both dictionaries define every key the dialog asks for.
    keys = pg.evaluate(
        """() => ['plan_reset_title','plan_reset_body','plan_reset_none','plan_reset_hint',
                    'plan_reset_apply','plan_reset_none_value','plan_reset_days',
                    'plan_reset_field_rotationMode','plan_reset_field_rueCycle',
                    'plan_reset_field_wCycle','plan_reset_field_lCycle',
                    'plan_reset_field_spCycle','plan_reset_field_customPlan',
                    'plan_rotation_by_part','plan_rotation_full_section','plan_rotation_custom',
                    'plan_reset_btn','plan_undo_btn']
            .filter(k => !I18N.en[k] || !I18N.es[k])"""
    )
    assert keys == [], f"keys missing from a dictionary: {keys}"
    OUT["7_i18n_complete"] = keys

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
