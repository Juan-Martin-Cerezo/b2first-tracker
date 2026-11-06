"""Phase 101: the custom rotation mode is gone from PLAN.

The rotation selector offers only by-part and full-section, the editor that
lived under it does not exist, and any legacy value (a stored rotationMode of
"custom" or a whole customPlan) is ignored when loading and discarded on save.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
DAYS = ["mon", "tue", "wed", "thu"]


def seed(pg, mode="by-part", custom=None):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in DAYS]
    pg.evaluate(
        """([schedule, mode, custom]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: schedule.map(s => s.day),
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.log = [];
            D.errs = [];
            D.sessionOffset = 0;
            D.settings.schedule = schedule;
            D.settings.rotationMode = mode;
            D.settings.itemsPerSession = 1;
            D.settings.customPlan = custom || {};
            save();
            refreshAll();
        }""",
        [schedule, mode, custom],
    )
    pg.wait_for_timeout(250)


PLAN_JS = """() => buildWeeklyPlan(D).slots.map(s => ({
    day: s.day, type: s.type, parts: s.parts || [], min: s.min,
    units: (s.units || []).map(u => u.skill + ':' + u.value),
    title: slotTitleText(s),
}))"""


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

    # 1. The selector has exactly the two real modes.
    options = pg.evaluate(
        "() => [...document.getElementById('wpRotationMode').options].map(o => o.value)"
    )
    assert options == ["by-part", "full-section"], (
        f"the rotation selector still offers a removed mode: {options}"
    )
    assert not pg.evaluate(
        "!!document.querySelector('#wpRotationMode option[value=\\\"custom\\\"]')"
    ), "an option with value=custom is still in the selector"
    OUT["1_options"] = options

    # 2. No node of the custom editor survives.
    editor = pg.evaluate(
        """() => ({
            box: !!document.getElementById('wpCustomEditor'),
            rows: document.querySelectorAll('#weeklyPlanCard .wp-custom-row').length,
            skills: document.querySelectorAll('#weeklyPlanCard .wp-custom-skill').length,
            parts: document.querySelectorAll('#weeklyPlanCard .wp-custom-parts').length,
            mins: document.querySelectorAll('#weeklyPlanCard .wp-custom-min').length,
            errors: document.querySelectorAll('[id^="wpCustomErr-"]').length,
            text: document.getElementById('weeklyPlanCard').innerText,
        })"""
    )
    assert not editor["box"], "#wpCustomEditor still exists"
    assert not (editor["rows"] or editor["skills"] or editor["parts"] or editor["mins"]), (
        f"the custom editor still renders controls: {editor}"
    )
    assert not editor["errors"], f"custom editor errors still render: {editor}"
    assert "custom plan" not in editor["text"].lower(), (
        f"the custom plan editor copy is still painted: {editor['text']!r}"
    )
    OUT["2_editor_removed"] = True

    # 3. The mode list is exactly the two supported values.
    modes = pg.evaluate("() => ROTATION_MODES.slice()")
    assert modes == ["by-part", "full-section"], f"ROTATION_MODES is wrong: {modes}"
    OUT["3_rotation_modes"] = modes

    # 4. Any unknown value, including a stored custom, normalizes to by-part.
    normalized = pg.evaluate(
        """() => ({
            custom: normalizeRotationMode('custom'),
            unknown: normalizeRotationMode('something-else'),
            missing: normalizeRotationMode(undefined),
            byPart: normalizeRotationMode('by-part'),
            full: normalizeRotationMode('full-section'),
        })"""
    )
    assert normalized == {
        "custom": "by-part", "unknown": "by-part", "missing": "by-part",
        "byPart": "by-part", "full": "full-section",
    }, f"normalizeRotationMode does not fall back safely: {normalized}"
    OUT["4_normalize"] = normalized

    # 5. A document seeded with custom + customPlan behaves as by-part and
    #    leaves no customPlan behind when saved.
    seed(pg, "by-part")
    baseline = pg.evaluate(PLAN_JS)
    seed(pg, "custom", {"Mon": {"skill": "rue", "parts": "1,3", "min": 50},
                        "Tue": {"skill": "l", "parts": "2", "min": 20}})
    legacy = pg.evaluate(
        """() => {
            const stored = JSON.parse(localStorage.getItem(userKey())) || {};
            return {
                normalized: normalizeRotationMode(D.settings.rotationMode),
                select: document.getElementById('wpRotationMode').value,
                hasCustom: Object.prototype.hasOwnProperty.call(D.settings, 'customPlan'),
                storedHasCustom: !!stored.settings &&
                    Object.prototype.hasOwnProperty.call(stored.settings, 'customPlan'),
                plan: buildWeeklyPlan(D).slots.map(s => ({
                    day: s.day, type: s.type, parts: s.parts || [], min: s.min,
                    units: (s.units || []).map(u => u.skill + ':' + u.value),
                    title: slotTitleText(s),
                })),
            };
        }"""
    )
    assert legacy["normalized"] == "by-part", (
        f"a stored custom mode did not fall back to by-part: {legacy}"
    )
    assert legacy["select"] == "by-part", (
        f"the selector did not show by-part: {legacy}"
    )
    assert not legacy["hasCustom"], (
        f"D.settings kept customPlan after save: {legacy}"
    )
    assert not legacy["storedHasCustom"], (
        f"customPlan reached localStorage after save: {legacy}"
    )
    assert legacy["plan"] == baseline, (
        f"the legacy custom plan did not behave like by-part: "
        f"{legacy['plan']} vs {baseline}"
    )
    OUT["5_legacy_behaves_by_part"] = {
        "normalized": legacy["normalized"],
        "hasCustom": legacy["hasCustom"],
        "titles": [r["title"] for r in legacy["plan"]],
    }

    # 6. load() ignores customPlan carried by an old document.
    loaded = pg.evaluate(
        """() => {
            const key = userKey();
            const doc = JSON.parse(localStorage.getItem(key)) || {};
            doc.settings = Object.assign({}, doc.settings || {}, {
                rotationMode: 'custom',
                customPlan: {Mon: {skill: 'rue', parts: '1', min: 30}},
            });
            localStorage.setItem(key, JSON.stringify(doc));
            const old = load();
            return {
                mode: normalizeRotationMode(old.settings.rotationMode),
                hasCustom: Object.prototype.hasOwnProperty.call(old.settings, 'customPlan'),
                titles: buildWeeklyPlan(old).slots.map(s => slotTitleText(s)),
            };
        }"""
    )
    assert loaded["mode"] == "by-part", f"load() kept the removed mode: {loaded}"
    assert not loaded["hasCustom"], f"load() kept customPlan: {loaded}"
    assert loaded["titles"] == [r["title"] for r in baseline], (
        f"a legacy document produced a custom plan: {loaded}"
    )
    OUT["6_load_ignores"] = loaded

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
