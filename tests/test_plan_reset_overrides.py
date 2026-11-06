"""Phase 88: Reset to defaults also clears the week's manual overrides.

D.weekOverrides holds the weekly rotation picked by hand (the "Override
writing genre" select). Reset to defaults puts the rotation settings back, so
it must clear those overrides too; the confirmation dialog lists them as one
of the values that will change, in English and Spanish. After Apply no
override remains and Today falls back to the automatic genre again.

The reset is still a single undoable step: Undo brings the overrides back.
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
    D.settings.rotationMode = 'by-part';
    D.settings.customPlan = {};
    D.settings.rueCycle = [1, 2, 3, 4, 5, 6, 7];
    D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
    D.settings.lCycle = [1, 2, 3, 4];
    D.settings.spCycle = [1, 2, 3, 4];
    D.weekOverrides = {};
    SETTINGS_UNDO = null;
    delete D.settingsUndo;
    save();
    refreshAll();
}"""

# Today's automatic genre, then a stored (legacy) manual override. The control
# itself was removed in phase 100; the reset still has to clear old data.
SET_OVERRIDE_JS = """() => {
    const auto = document.getElementById('wTipo') ? document.getElementById('wTipo').value : null;
    const chosen = auto === 'Report' ? 'Review' : 'Report';
    D.weekOverrides = D.weekOverrides || {};
    D.weekOverrides.w = chosen;
    save();
    refreshAll();
    return {auto: auto, override: chosen};
}"""

STATE_JS = """() => {
    let stored = null;
    try { stored = JSON.parse(localStorage.getItem(userKey())) || null; } catch (e) {}
    return {
        overrides: JSON.parse(JSON.stringify(D.weekOverrides || {})),
        wTipo: document.getElementById('wTipo') ? document.getElementById('wTipo').value : null,
        ovW: !!document.getElementById('ovW'),
        hint: (document.querySelector('#rotationCardBody .rot-override') || {}).textContent || '',
        stored: stored ? (stored.weekOverrides || null) : null,
    };
}"""

DIALOG_JS = """() => ({
    open: document.getElementById('planResetModal').style.display !== 'none',
    rows: Array.prototype.map.call(
        document.querySelectorAll('#planResetDetail li'),
        li => ({label: li.querySelector('b').textContent, value: li.querySelector('span').textContent})
    ),
})"""


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

    # 1. A manual override is really in effect before the reset.
    picked = pg.evaluate(SET_OVERRIDE_JS)
    pg.wait_for_timeout(250)
    before = pg.evaluate(STATE_JS)
    assert before["overrides"] == {"w": picked["override"]}, (
        f"the override was not stored: {before}"
    )
    assert before["wTipo"] == picked["auto"], (
        f"the removed override still drives Today: {before}"
    )
    assert before["ovW"] is False, f"the removed select is back in the DOM: {before}"
    assert before["hint"] == "", (
        f"the rotation card still paints an override: {before}"
    )
    assert before["stored"] == {"w": picked["override"]}, (
        f"the override did not reach localStorage: {before}"
    )
    OUT["1_override_set"] = {"picked": picked, "state": before}

    # 2. The dialog says the weekly overrides will change, with their value.
    pg.click("#wpResetBtn")
    pg.wait_for_timeout(250)
    opened = pg.evaluate(DIALOG_JS)
    assert opened["open"], f"the reset dialog did not open: {opened}"
    assert [r["label"] for r in opened["rows"]] == ["Manual overrides this week"], (
        f"the dialog does not list the overrides: {opened}"
    )
    assert opened["rows"][0]["value"] == picked["override"] + " → none", (
        f"the dialog does not show the override value: {opened}"
    )
    OUT["2_dialog_lists_overrides"] = opened

    # 3. Apply clears them everywhere: state, Today and the stored document.
    pg.click("#planResetApply")
    pg.wait_for_timeout(400)
    after = pg.evaluate(STATE_JS)
    assert after["overrides"] == {}, f"the reset left overrides behind: {after}"
    assert after["wTipo"] == picked["auto"], (
        f"Today still uses the removed override: {after}"
    )
    assert after["ovW"] is False, f"the removed select is back after reset: {after}"
    assert after["hint"] == "", f"the hint still names the override: {after}"
    assert not after["stored"], f"the cleared overrides were not persisted: {after}"
    OUT["3_reset_clears"] = after

    # 4. The reset is still one undoable step: Undo restores the overrides.
    undo = pg.evaluate(
        "() => ({shown: !!SETTINGS_UNDO, overrides: SETTINGS_UNDO ? SETTINGS_UNDO.weekOverrides : null,"
        " visible: getComputedStyle(document.getElementById('wpUndoBtn')).display !== 'none'})"
    )
    assert undo["shown"], f"the reset was not undoable: {undo}"
    assert undo["overrides"] == {"w": picked["override"]}, (
        f"the undo step does not keep the overrides: {undo}"
    )
    assert undo["visible"], f"Undo is not offered after the reset: {undo}"
    pg.click("#wpUndoBtn")
    pg.wait_for_timeout(400)
    restored = pg.evaluate(STATE_JS)
    assert restored["overrides"] == {"w": picked["override"]}, (
        f"Undo did not restore the override: {restored}"
    )
    assert restored["wTipo"] == picked["auto"], (
        f"the removed override drives Today again: {restored}"
    )
    OUT["4_undo_restores"] = {"undo": undo, "state": restored}

    # 5. Spanish: same row, translated, with the Spanish "none".
    picked_es = pg.evaluate(SET_OVERRIDE_JS)
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(300)
    pg.click("#wpResetBtn")
    pg.wait_for_timeout(250)
    es = pg.evaluate(DIALOG_JS)
    assert [r["label"] for r in es["rows"]] == ["Ajustes manuales de esta semana"], (
        f"the Spanish dialog does not list the overrides: {es}"
    )
    assert es["rows"][0]["value"] == picked_es["override"] + " → ninguno", (
        f"the Spanish row is not translated: {es}"
    )
    pg.click("#planResetApply")
    pg.wait_for_timeout(400)
    assert pg.evaluate("Object.keys(D.weekOverrides || {}).length") == 0, (
        "the Spanish reset did not clear the overrides"
    )
    OUT["5_spanish"] = es

    # 6. The new key exists in both dictionaries.
    keys = pg.evaluate(
        "() => ['plan_reset_field_weekOverrides','plan_reset_none_value']"
        ".filter(k => !I18N.en[k] || !I18N.es[k])"
    )
    assert keys == [], f"keys missing from a dictionary: {keys}"
    OUT["6_i18n_complete"] = keys

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
