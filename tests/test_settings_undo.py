"""Phase 86: one-step undo and reset for the rotation settings.

Changing the mode stores the previous rotation state and shows a discreet
Undo for the life of the page; Undo restores the whole previous state and
repaints. Reset to defaults puts rotationMode and the four cycles back. The
undo never survives a reload.
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
    D.settings.rueCycle = [1, 2, 3, 4, 5, 6, 7];
    D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
    D.settings.lCycle = [1, 2, 3, 4];
    D.settings.spCycle = [1, 2, 3, 4];
    SETTINGS_UNDO = null;
    delete D.settingsUndo;
    save();
    refreshAll();
}"""

SIG_JS = """() => ({
    mode: D.settings.rotationMode,
    sig: buildWeeklyPlan(D).slots.map(s => slotTitleText(s)).join(' | '),
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
    baseline = pg.evaluate(SIG_JS)
    assert baseline["mode"] == "by-part"

    # 1. Changing the mode stores the previous state and shows Undo.
    pg.select_option("#wpRotationMode", "full-section")
    pg.wait_for_timeout(400)
    changed = pg.evaluate(
        """() => ({
            mode: D.settings.rotationMode,
            undo: SETTINGS_UNDO ? JSON.parse(JSON.stringify(SETTINGS_UNDO)) : null,
            visible: getComputedStyle(document.getElementById('wpUndoBtn')).display !== 'none',
        })"""
    )
    assert changed["mode"] == "full-section", f"the mode change did not stick: {changed}"
    assert changed["undo"] and changed["undo"]["rotationMode"] == "by-part", (
        f"the previous state was not stored: {changed}"
    )
    assert changed["visible"], "the Undo control is not visible"
    OUT["1_change_stores_undo"] = changed

    # 2. Undo restores the previous mode and the previous plan.
    pg.click("#wpUndoBtn")
    pg.wait_for_timeout(400)
    undone = pg.evaluate(
        """() => ({
            mode: D.settings.rotationMode,
            sig: buildWeeklyPlan(D).slots.map(s => slotTitleText(s)).join(' | '),
            undo: SETTINGS_UNDO,
            visible: getComputedStyle(document.getElementById('wpUndoBtn')).display !== 'none',
        })"""
    )
    assert undone["mode"] == baseline["mode"], f"Undo did not restore the mode: {undone}"
    assert undone["sig"] == baseline["sig"], f"Undo did not restore the plan: {undone}"
    assert undone["undo"] is None, f"Undo kept a second step: {undone}"
    assert not undone["visible"], "Undo is still visible after being used"
    OUT["2_undo_restores"] = undone

    # 2b. The manual cycle editor is gone: there is no input to edit.
    assert pg.evaluate("!!document.getElementById('pRueCycle')") is False, (
        "the removable cycle editor is still in the DOM"
    )
    OUT["2b_no_cycle_editor"] = True

    # 3. Reset to defaults returns the rotation settings and repaints the plan.
    pg.evaluate(
        """() => {
            D.settings.rotationMode = 'full-section';
            D.settings.rueCycle = [7, 1];
            D.settings.wCycle = ['Article'];
            D.settings.lCycle = [4];
            D.settings.spCycle = [3];
            save();
            refreshAll();
        }"""
    )
    pg.wait_for_timeout(250)
    pg.evaluate("window.confirm = () => true")
    pg.click("#wpResetBtn")
    pg.wait_for_timeout(200)
    # Reset now goes through the accessible confirmation dialog (phase 87).
    assert pg.is_visible("#planResetModal"), "the reset confirmation did not open"
    pg.click("#planResetApply")
    pg.wait_for_timeout(400)
    reset = pg.evaluate(
        """() => ({
            rotationMode: D.settings.rotationMode,
            rueCycle: D.settings.rueCycle,
            wCycle: D.settings.wCycle,
            lCycle: D.settings.lCycle,
            spCycle: D.settings.spCycle,
            rows: document.querySelectorAll('#wpRows .wp-row').length,
            slots: buildWeeklyPlan(D).slots.length,
        })"""
    )
    assert reset["rotationMode"] == "by-part", f"reset left rotationMode: {reset}"
    assert reset["rueCycle"] == [1, 2, 3, 4, 5, 6, 7], f"reset left rueCycle: {reset}"
    assert reset["wCycle"] == ["Essay", "Article", "Report", "Review", "Email"], f"reset left wCycle: {reset}"
    assert reset["lCycle"] == [1, 2, 3, 4], f"reset left lCycle: {reset}"
    assert reset["spCycle"] == [1, 2, 3, 4], f"reset left spCycle: {reset}"
    assert reset["rows"] == reset["slots"], f"reset did not repaint the plan: {reset}"
    OUT["3_reset_defaults"] = reset

    # 4. The undo is not persisted: after a reload the accepted value stays
    #    and there is nothing to undo.
    pg.evaluate("onRotationModeChange('full-section')")
    pg.wait_for_timeout(700)
    assert pg.evaluate("D.settings.rotationMode") == "full-section"
    pg.reload(wait_until="networkidle")
    dismiss_onboarding(pg)
    pg.wait_for_timeout(400)
    after_reload = pg.evaluate(
        """() => ({
            mode: D.settings.rotationMode,
            undo: typeof SETTINGS_UNDO === 'undefined' ? 'undefined' : SETTINGS_UNDO,
            button: !!document.getElementById('wpUndoBtn') &&
                getComputedStyle(document.getElementById('wpUndoBtn')).display !== 'none',
        })"""
    )
    assert after_reload["mode"] == "full-section", f"the accepted mode was lost on reload: {after_reload}"
    assert after_reload["undo"] is None, f"the undo leaked into the reload: {after_reload}"
    assert not after_reload["button"], f"Undo is offered after a reload: {after_reload}"
    OUT["4_undo_not_persisted"] = after_reload

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
