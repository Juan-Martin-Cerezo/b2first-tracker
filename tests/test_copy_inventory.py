"""Phase 99: living inventory of every session-copy surface.

The suite walks Plan, Today, "What comes next", the four Today studios and the
log in every rotation mode, prints the text it saw, and fails when a partial
session is described with a completeness phrase. It is the documentation of the
sweep: each entry lists the mode, the surface and the exact phrases.

It also checks the studio duration against the row it stands for and the help
copy against the active mode, in English and in Spanish.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Phrases that assert completeness. A partial session may not use them.
COMPLETENESS = ["full", "whole paper", "complete test", "todas las partes",
                "paper completo", "prueba completa"]

SURFACES_JS = """() => {
    const t = id => (document.getElementById(id) || {}).innerText || '';
    return {
        plan: t('wpRows'),
        today: t('todaySession'),
        next: t('nextBox'),
        upcoming: t('rotationCard'),
        preview: t('wpQueuePreview'),
        summary: t('wpSummary'),
        log: t('logTable'),
        stats: t('statsTable'),
        help: t('wpRotationHelp'),
        mode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
        todayMode: (document.querySelector('#todaySession .ts-mode') || {}).textContent || '',
    };
}"""

STUDIOS_JS = """() => {
    const out = {};
    const cfg = {rue: ['mon-a', 'st1Name', 'st1Dur', 'st1Sub'],
                 l: ['fri-a', 'st3Name', 'st3Dur', 'st3Sub'],
                 w: ['mon-b', 'st2Name', 'st2Dur', 'st2Sub'],
                 sp: ['fri-b', 'st4Name', 'st4Dur', 'st4Sub']};
    Object.keys(cfg).forEach(skill => {
        const c = cfg[skill];
        const sl = studioSlotFor(skill);
        selectSessionStudio(c[0]);
        out[skill] = {
            min: sl ? sl.min : null,
            whole: studioIsWhole(sl),
            name: (document.getElementById(c[1]) || {}).textContent || '',
            dur: (document.getElementById(c[2]) || {}).textContent || '',
            sub: (document.getElementById(c[3]) || {}).textContent || '',
        };
    });
    return out;
}"""


def seed(pg, mode="by-part", per=1, custom=None, days=ALL_DAYS, offset=0):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(
        """([schedule, mode, per, custom, offset]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: schedule.map(s => s.day),
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.errs = [];
            D.log = [];
            D.sessionOffset = offset;
            D.weekOverrides = {};
            D.settings.schedule = schedule;
            D.settings.rotationMode = mode;
            D.settings.itemsPerSession = per;
            D.settings.customPlan = custom || {};
            save();
            refreshAll();
        }""",
        [schedule, mode, per, custom, offset],
    )
    pg.wait_for_timeout(300)


def collect(pg):
    state = pg.evaluate(SURFACES_JS)
    state["studios"] = pg.evaluate(STUDIOS_JS)
    return state


def all_text(state):
    parts = [state[k] for k in
             ("plan", "today", "next", "upcoming", "preview", "summary",
              "log", "stats")]
    for studio in state["studios"].values():
        parts.extend([studio["name"], studio["dur"], studio["sub"]])
    return " ".join(parts)


def assert_partial_is_honest(state, label):
    text = all_text(state).lower()
    for phrase in COMPLETENESS:
        assert phrase not in text, (
            f"{label}: a partial session claims completeness with {phrase!r}. "
            f"Text: {text!r}"
        )
    for skill, studio in state["studios"].items():
        assert not studio["whole"], f"{label}: {skill} claims a whole paper: {studio}"


def assert_studio_durations(state, label):
    for skill, studio in state["studios"].items():
        assert studio["min"] is not None, f"{label}: {skill} has no planned session"
        assert studio["dur"] == f"{studio['min']} MIN", (
            f"{label}: the {skill} studio shows {studio['dur']!r} "
            f"but its session lasts {studio['min']} min"
        )


def inventory(state, label):
    return {
        "mode": label,
        "surfaces": {k: state[k].strip()[:220] for k in
                     ("plan", "today", "next", "upcoming", "preview",
                      "summary", "help", "mode", "todayMode")},
        "studios": {k: v for k, v in state["studios"].items()},
        "log": state["log"].strip()[:160],
    }


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

    inv = {}

    # 1. by-part, 1/2/3 units, both skill pairs of the week block.
    for per in (1, 2, 3):
        for offset, pair in ((0, "rue+l"), (len(ALL_DAYS), "w+sp")):
            label = f"by-part per={per} {pair}"
            seed(pg, "by-part", per, offset=offset)
            state = collect(pg)
            assert_partial_is_honest(state, label)
            assert_studio_durations(state, label)
            inv[label] = inventory(state, label)
    OUT["by_part"] = {k: v["studios"] for k, v in inv.items()
                      if k.startswith("by-part")}

    # 1b. Start on a partial row opens its own filtered studio: the header
    #     names the part, never a whole paper.
    seed(pg, "by-part", 1)
    pg.evaluate("wpStart(0)")
    pg.wait_for_timeout(300)
    started = pg.evaluate(
        """() => ({
            badge: (document.querySelector('#resourcesList .badge') || {}).textContent || '',
            view: (document.querySelector('.view.active') || {}).id || '',
        })"""
    )
    assert "full" not in started["badge"].lower(), started
    assert "part" in started["badge"].lower(), started
    OUT["start_by_part"] = started

    # 2. The log only has the row types those sessions write.
    pg.evaluate(
        """() => {
            D.log = [
                {date: '2026-10-01', type: 'ue', part: 3, correct: 6, total: 8, min: 8},
                {date: '2026-10-02', type: 'lp', part: 2, correct: 7, total: 10, min: 10},
                {date: '2026-10-03', type: 'w', kind: 'Essay', score: 14, min: 40},
                {date: '2026-10-04', type: 'sp', part: 1, score: 4, min: 2},
            ];
            save(); refreshAll();
        }"""
    )
    pg.wait_for_timeout(300)
    logged = collect(pg)
    assert "full" not in logged["log"].lower(), logged["log"]
    assert "full" not in logged["stats"].lower(), logged["stats"]
    chart = pg.evaluate("() => document.getElementById('gPart').textContent")
    assert "full" not in chart.lower(), chart
    OUT["log"] = logged["log"].strip()[:220]
    OUT["chart_labels"] = chart.strip()[:220]

    # 3. custom, partial and whole.
    custom = {
        "Mon": {"skill": "rue", "parts": "1,3", "min": 50},
        "Tue": {"skill": "l", "parts": "2", "min": 20},
        "Wed": {"skill": "w", "parts": "", "min": 40},
        "Thu": {"skill": "sp", "parts": "2", "min": 30},
    }
    seed(pg, "custom", custom=custom, days=["mon", "tue", "wed", "thu"])
    custom_state = collect(pg)
    assert_partial_is_honest(custom_state, "custom partial")
    assert_studio_durations(custom_state, "custom partial")
    assert custom_state["studios"]["rue"]["dur"] == "50 MIN", custom_state["studios"]["rue"]
    assert "Reading parts 1, 3" in custom_state["studios"]["rue"]["name"], (
        custom_state["studios"]["rue"]
    )
    OUT["custom_partial"] = inventory(custom_state, "custom partial")

    whole_custom = {
        "Mon": {"skill": "rue", "parts": "", "min": 75},
        "Tue": {"skill": "l", "parts": "1-4", "min": 40},
        "Wed": {"skill": "w", "parts": "", "min": 40},
        "Thu": {"skill": "sp", "parts": "1-4", "min": 14},
    }
    seed(pg, "custom", custom=whole_custom, days=["mon", "tue", "wed", "thu"])
    whole_state = collect(pg)
    assert "Full R&UE" in whole_state["studios"]["rue"]["name"], whole_state["studios"]["rue"]
    assert whole_state["studios"]["rue"]["dur"] == "75 MIN", whole_state["studios"]["rue"]
    OUT["custom_whole"] = inventory(whole_state, "custom whole")

    # 4. full-section: Full is true, with the official totals.
    seed(pg, "full-section")
    full = collect(pg)
    official = {"rue": 75, "l": 40, "w": 80, "sp": 14}
    for skill, minutes in official.items():
        studio = full["studios"][skill]
        assert studio["whole"], f"full-section {skill} is not whole: {studio}"
        assert "Full" in studio["name"], studio
        assert studio["min"] == minutes and studio["dur"] == f"{minutes} MIN", studio
    assert "Full " in full["plan"], full["plan"]
    OUT["full_section"] = inventory(full, "full-section")

    # 5. Help copy never contradicts the active mode, in both languages.
    FORBIDDEN = {
        "en": {
            "by-part": ["whole paper", "complete test", "one item per session",
                        "4-step", "component by component", "advances one item"],
            "full-section": ["one exercise per session", "by part",
                             "custom plan, day by day"],
            "custom": ["whole paper", "one exercise per session", "by part"],
        },
        "es": {
            "by-part": ["paper completo", "prueba completa", "un ítem por sesión",
                        "ciclo base de 4 pasos", "componente por componente"],
            "full-section": ["un ejercicio por sesión", "por parte",
                             "plan personalizado, día por día"],
            "custom": ["paper completo", "un ejercicio por sesión", "por parte"],
        },
    }
    help_seen = {}
    for lang in ("en", "es"):
        pg.evaluate(f"setLang('{lang}')")
        pg.wait_for_timeout(250)
        for mode in ("by-part", "full-section", "custom"):
            seed(pg, mode, custom=custom if mode == "custom" else None)
            copy = " ".join(
                collect(pg)[k] for k in ("help", "mode", "todayMode")
            ).lower()
            for phrase in FORBIDDEN[lang][mode]:
                assert phrase not in copy, (
                    f"{lang}/{mode}: help contradicts the mode with {phrase!r}: {copy!r}"
                )
            help_seen[f"{lang}_{mode}"] = copy.strip()[:140]
    OUT["help"] = help_seen

    OUT["inventory"] = inv
    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
