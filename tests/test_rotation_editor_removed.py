"""Phase 100: the manual rotation editor is gone from PLAN.

No cycle inputs, no writing-genre override, no speaking-voice control and no
Save/Restore buttons. Their i18n keys are gone from both dictionaries too: the
cycles are product constants now.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

REMOVED_IDS = ["pRueCycle", "pWCycle", "pLCycle", "pSpCycle", "pVoice", "ovW"]
REMOVED_KEYS = [
    "plan_voice", "plan_voice_fast", "plan_voice_natural", "plan_voice_hint",
    "plan_override_genre", "plan_rotation_order",
    "plan_rue_cycle", "plan_w_cycle", "plan_l_cycle", "plan_sp_cycle",
    "plan_rotation_override", "plan_save", "plan_restore",
    "alert_plan_saved", "alert_restore_plan",
]
REMOVED_TEXT = [
    "Override writing genre",
    "Edit the order each skill cycles through",
    "R&UoE (parts 1-7, in order)",
    "Writing (types, in order)",
    "Listening (parts 1-4)",
    "Speaking (parts 1-4)",
    "Speaking voice",
    "Instant speaks the reply",
    "Natural asks Gemini",
    "Save plan",
    "Restore original plan",
    "Four Reading & UoE exercises per session",
]


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

    # 1. None of the editor nodes exist anywhere in the DOM.
    present = [
        node_id for node_id in REMOVED_IDS
        if pg.evaluate(f"!!document.getElementById('{node_id}')")
    ]
    assert not present, f"removed controls still in the DOM: {present}"
    OUT["1_removed_ids"] = REMOVED_IDS

    # 2. None of the editor copy is painted on PLAN.
    plan_text = pg.evaluate("document.getElementById('v-plan').innerText")
    lowered = plan_text.lower()
    for phrase in REMOVED_TEXT:
        assert phrase.lower() not in lowered, (
            f"removed copy still visible: {phrase!r} in {plan_text!r}"
        )
    buttons = pg.eval_on_selector_all(
        "#v-plan button", "els => els.map(e => e.innerText.trim())"
    )
    assert not any("Save plan" in b or "Restore original plan" in b for b in buttons), (
        f"the save/restore buttons survived: {buttons}"
    )
    assert "Reset to defaults" in " ".join(buttons), (
        f"Reset to defaults disappeared: {buttons}"
    )
    OUT["2_copy"] = {"plan_text": plan_text[:200], "buttons": buttons}

    # 3. The cycles are constants and ignore any old stored value.
    cycles = pg.evaluate(
        """() => {
            D.settings.rueCycle = [7, 6];
            D.settings.wCycle = ['Review'];
            D.settings.lCycle = [4];
            D.settings.spCycle = [3];
            save();
            return queueCycles();
        }"""
    )
    assert cycles == {
        "rue": [1, 2, 3, 4, 5, 6, 7],
        "w": ["Essay", "Article", "Report", "Review", "Email"],
        "l": [1, 2, 3, 4],
        "sp": [1, 2, 3, 4],
    }, f"the cycles are not constants: {cycles}"
    OUT["3_constants"] = cycles

    # 4. The removed keys are gone from both dictionaries.
    missing = pg.evaluate(
        """(keys) => keys.filter(k => !(k in I18N.en) && !(k in I18N.es))""",
        REMOVED_KEYS,
    )
    assert missing == REMOVED_KEYS, f"some removed keys are still present: {missing}"
    leaked = pg.evaluate(
        """(keys) => keys.filter(k => (k in I18N.en) || (k in I18N.es))""",
        REMOVED_KEYS,
    )
    assert not leaked, f"removed i18n keys still in a dictionary: {leaked}"
    OUT["4_keys_removed"] = REMOVED_KEYS

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
