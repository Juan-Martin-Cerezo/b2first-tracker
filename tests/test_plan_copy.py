"""Phase 97: Plan, Today and "What comes next" describe the real plan.

No screen may claim a behaviour the app does not have ("4-step core cycle",
"component by component", "advances one item per session", "continuous
rotation"). With itemsPerSession=2 the preview shows two units of the same
skill, and full-section says "a whole paper per session".
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

BANNED = {
    "en": [
        "4-step core cycle",
        "component by component",
        "advances one item per session",
        "continuous rotation",
    ],
    "es": [
        "ciclo base de 4 pasos",
        "componente por componente",
        "avanza un ítem por sesión",
        "rotación continua",
    ],
}

READ_JS = """() => ({
    planText: document.getElementById('v-plan').innerText,
    todayText: document.getElementById('todaySession').innerText,
    cardText: document.getElementById('rotationCard').innerText,
    mode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
    todayMode: (document.querySelector('#todaySession .ts-mode') || {}).textContent || '',
    preview: document.getElementById('wpQueuePreview').textContent,
    upcoming: [...document.querySelectorAll('#planUpcomingPreview .up-row')].map(r => ({
        day: r.dataset.day,
        label: (r.querySelector('.badge') || {}).textContent || '',
    })),
})"""


def seed(pg, mode="by-part", per=1, days=None):
    days = days or ALL_DAYS
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(
        """([schedule, mode, per]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: schedule.map(s => s.day),
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.errs = [];
            D.log = [];
            D.sessionOffset = 0;
            D.weekOverrides = {};
            D.settings.schedule = schedule;
            D.settings.rotationMode = mode;
            D.settings.itemsPerSession = per;
            D.settings.rueCycle = [1, 2, 3, 4, 5, 6, 7];
            D.settings.lCycle = [1, 2, 3, 4];
            D.settings.spCycle = [1, 2, 3, 4];
            D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
            save();
            refreshAll();
        }""",
        [schedule, mode, per],
    )
    pg.wait_for_timeout(300)


def assert_no_bad_copy(state, lang):
    for banned in BANNED[lang]:
        for field in ("planText", "todayText", "cardText"):
            assert banned not in state[field].lower(), (
                f"{lang}: forbidden copy {banned!r} in {field}: {state[field]!r}"
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
    pg.wait_for_timeout(300)

    # 1. by-part with two exercises: the preview and Today show the same skill.
    seed(pg, "by-part", per=2)
    state = pg.evaluate(READ_JS)
    assert "Reading part 1 · Reading part 2" in state["preview"], (
        f"the preview did not group the session: {state['preview']!r}"
    )
    assert "two" in state["mode"].lower() and "Reading" in state["mode"], (
        f"the mode line is wrong: {state['mode']!r}"
    )
    assert "two" in state["todayMode"].lower() and "Reading" in state["todayMode"], (
        f"Today does not name the active mode: {state['todayMode']!r}"
    )
    assert state["upcoming"][0]["label"] == "Reading part 1", state["upcoming"]
    assert state["upcoming"][1]["label"] == "Reading part 2", state["upcoming"]
    assert_no_bad_copy(state, "en")
    OUT["by_part_per2"] = {
        "mode": state["mode"], "today_mode": state["todayMode"],
        "preview": state["preview"],
    }

    # 2. The same copy is honest in Spanish.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    spanish = pg.evaluate(READ_JS)
    assert_no_bad_copy(spanish, "es")
    assert "dos" in spanish["mode"].lower(), spanish["mode"]
    OUT["es"] = {"mode": spanish["mode"]}

    # 3. full-section: a whole paper per session, whole papers in the queue.
    pg.evaluate("setLang('en')")
    seed(pg, "full-section", per=1)
    full = pg.evaluate(READ_JS)
    assert "whole paper per session" in full["mode"].lower(), full["mode"]
    labels = [r["label"] for r in full["upcoming"]]
    assert labels[:4] == [
        "Full R&UE (75 min)",
        "Full Listening (40 min)",
        "Full Writing (80 min)",
        "Full Speaking (14 min)",
    ], f"full-section is not showing whole papers: {labels}"
    assert_no_bad_copy(full, "en")
    OUT["full_section"] = {"mode": full["mode"], "labels": labels[:4]}

    # 4. The removed custom mode is not offered or painted.
    removed = pg.evaluate(
        """() => ({
            options: [...document.getElementById('wpRotationMode').options].map(o => o.value),
            mode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
        })"""
    )
    assert removed["options"] == ["by-part", "full-section"], removed
    assert "custom plan" not in removed["mode"].lower(), removed
    OUT["4_no_custom"] = removed

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
