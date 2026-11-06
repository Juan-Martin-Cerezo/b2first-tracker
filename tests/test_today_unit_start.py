"""Phase 99: Start on TODAY opens exactly the plan unit, not the skill in general.

Today renders one row of buildWeeklyPlan(D), built from queue units (skill +
exercise + minutes). Its Start must open that row's session studio with the
unit already selected and the plan's minutes in place, and the row saved from
there must keep both, so D.log says what the plan asked for — not just what the
user happened to type.

The four skills are covered, plus the backlog's own example (Reading part 3,
8 min). The offset that puts a skill on TODAY is found with the app's own
rotation queue, and the expected exercise is read from the rendered row, so the
suite never mirrors the planner in Python.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

ALL_DAYS = [
    {"day": 1, "time": "15:30"},  # Mon
    {"day": 2, "time": "13:00"},  # Tue
    {"day": 3, "time": "10:00"},  # Wed
    {"day": 4, "time": "18:00"},  # Thu
    {"day": 5, "time": "17:00"},  # Fri
    {"day": 6, "time": "11:00"},  # Sat
    {"day": 0, "time": "09:00"},  # Sun
]

# plan skill -> (log type, studio card, part control)
SKILLS = {
    "rue": ("ue", "studioMonA", "uePart"),
    "l": ("lp", "studioFriA", "lPart"),
    "w": ("w", "studioMonB", "wTipo"),
    "sp": ("sp", "studioFriB", "spPart"),
}

# The offset scan asks the app's own queue which exercise TODAY gets with each
# sessionOffset, and keeps the first hit per skill (plus Reading part 3).
SCAN_JS = """() => {
    const today = planTodayLabel().toLowerCase();
    const keys = getSessionDays().map(d => d.key);
    const out = {};
    for (let offset = 0; offset < 60; offset++) {
        const slots = rotationQueueSessions(keys, 1, offset, keys.length, D.settings);
        const mine = slots.find(sl => sl.day === today);
        if (!mine || !mine.units || !mine.units.length) continue;
        const u = mine.units[0];
        const hit = {
            offset: offset,
            skill: u.skill,
            value: u.value,
            min: Number(mine.min),
            type: mine.type,
        };
        if (!out[u.skill]) out[u.skill] = hit;
        if (u.skill === 'rue' && u.value === 3 && !out.reading3) out.reading3 = hit;
    }
    return out;
}"""

ROW_JS = """() => {
    const row = document.querySelector('#todaySession .ts-row:not(.ts-next-unit)');
    if (!row) return null;
    const units = (row.dataset.units || '').split(',').filter(Boolean);
    return {
        type: row.dataset.type,
        units: units,
        min: Number(row.dataset.min),
        title: ((row.querySelector('.ts-title') || {}).textContent || '').trim(),
    };
}"""

STUDIO_JS = """() => {
    const vis = id => {
        const el = document.getElementById(id);
        return !!el && getComputedStyle(el).display !== 'none';
    };
    const val = id => {
        const el = document.getElementById(id);
        return el ? String(el.value) : null;
    };
    return {
        view: (document.querySelector('.view.active') || {}).id || '',
        solo: getComputedStyle(document.getElementById('soloModal')).display,
        studios: {
            rue: vis('studioMonA'), l: vis('studioFriA'),
            w: vis('studioMonB'), sp: vis('studioFriB'),
        },
        uePart: val('uePart'), ueTotal: val('ueTotal'), ueMin: val('ueMin'),
        lPart: val('lPart'), lMin: val('lMin'),
        wTipo: val('wTipo'), wMin: val('wMin'),
        spPart: val('spPart'),
        unitTag: typeof PLAN_UNIT_START === 'undefined' ? null : PLAN_UNIT_START,
    };
}"""


def seed(pg, offset):
    pg.evaluate(
        """([schedule, offset]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 6, days: [0, 1, 2, 3, 4, 5, 6],
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.log = [];
            D.errs = [];
            D.sessionOffset = offset;
            D.settings.schedule = schedule;
            D.settings.rotationMode = 'by-part';
            D.settings.itemsPerSession = 1;
            save();
            refreshAll();
        }""",
        [ALL_DAYS, offset],
    )
    pg.wait_for_timeout(220)


def save_unit(pg, skill):
    """Save through the studio whose unit was just opened."""
    if skill == "rue":
        state = pg.evaluate(
            """() => {
                document.getElementById('ueOk').value = 5;
                saveUE();
                return D.log[0];
            }"""
        )
    elif skill == "l":
        state = pg.evaluate(
            """() => {
                document.getElementById('lOk').value = 5;
                saveL();
                return D.log[0];
            }"""
        )
    elif skill == "w":
        state = pg.evaluate(
            """() => {
                document.getElementById('wScore').value = 14;
                saveW();
                return D.log[0];
            }"""
        )
    else:
        state = pg.evaluate("() => { saveSP(); return D.log[0]; }")
    return state


def check_case(pg, label, expected):
    skill = expected["skill"]
    log_type, card, part_ctl = SKILLS[skill]

    row = pg.evaluate(ROW_JS)
    assert row is not None, f"{label}: TODAY has no session row"
    assert row["type"] == expected["type"], (
        f"{label}: TODAY shows {row['type']} instead of {expected['type']}: {row}"
    )
    assert row["units"] == [f"{skill}:{expected['value']}"], (
        f"{label}: TODAY does not show the plan unit: {row}"
    )
    assert row["min"] == expected["min"], (
        f"{label}: TODAY row lasts {row['min']} min, the plan says {expected['min']}"
    )

    pg.click("#todaySession .ts-row:not(.ts-next-unit) button")
    pg.wait_for_timeout(250)
    studio = pg.evaluate(STUDIO_JS)

    assert studio["view"] == "v-hoy", (
        f"{label}: Start left TODAY for {studio['view']}, a generic skill surface"
    )
    assert studio["solo"] == "none", f"{label}: Start opened the generic solo modal"
    assert studio["studios"][skill] is True, (
        f"{label}: the {skill} session studio is not the one on screen: {studio['studios']}"
    )
    assert studio["unitTag"] == {
        "skill": skill,
        "value": expected["value"],
        "min": expected["min"],
    }, f"{label}: Start did not arm the exact plan unit: {studio['unitTag']}"

    part = str(expected["value"])
    if skill in ("rue", "l"):
        assert studio[part_ctl] == part, (
            f"{label}: the studio opens part {studio[part_ctl]} instead of {part}"
        )
        minutes = studio["ueMin"] if skill == "rue" else studio["lMin"]
        assert minutes == str(expected["min"]), (
            f"{label}: the studio has {minutes} min instead of the planned {expected['min']}"
        )
    elif skill == "w":
        assert studio["wTipo"] == part, (
            f"{label}: the studio opens {studio['wTipo']} instead of {part}"
        )
        assert studio["wMin"] == str(expected["min"]), (
            f"{label}: the writing studio has {studio['wMin']} min instead of {expected['min']}"
        )
    else:
        assert studio["spPart"] == part, (
            f"{label}: the speaking studio opens part {studio['spPart']} instead of {part}"
        )

    saved = save_unit(pg, skill)
    assert saved["type"] == log_type, (
        f"{label}: the row saved as {saved.get('type')} instead of {log_type}: {saved}"
    )
    assert saved.get("unit") == {
        "skill": skill,
        "value": expected["value"],
        "min": expected["min"],
    }, f"{label}: the row does not keep the plan unit and its minutes: {saved}"
    if skill != "sp":
        assert saved.get("min") == expected["min"], (
            f"{label}: the row does not keep the planned minutes: {saved}"
        )

    after = pg.evaluate(
        "() => typeof PLAN_UNIT_START === 'undefined' ? null : PLAN_UNIT_START"
    )
    assert after is None, f"{label}: the unit stayed armed after saving: {after}"
    return {"label": label, "row": row, "studio": studio, "saved": saved}


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(250)

    seed(pg, 0)
    plan = pg.evaluate(SCAN_JS)
    for skill in SKILLS:
        assert skill in plan, f"no offset puts {skill} on TODAY: {plan}"
    assert "reading3" in plan, f"no offset gives Today Reading part 3: {plan}"
    OUT["1_scan"] = plan

    cases = [plan[s] for s in ("rue", "l", "w", "sp")] + [plan["reading3"]]
    seen = []
    for i, expected in enumerate(cases):
        seed(pg, expected["offset"])
        label = f"2.{i + 1} {expected['skill']} {expected['value']}"
        seen.append(check_case(pg, label, expected))
        OUT[label] = seen[-1]

    # The backlog's example, asserted as named copy: Reading part 3 · 8 min.
    r3 = OUT["2.5 rue 3"]
    assert "Reading part 3" in r3["row"]["title"], r3["row"]
    assert r3["studio"]["uePart"] == "3" and r3["studio"]["ueMin"] == "8", r3["studio"]
    assert r3["studio"]["ueTotal"] == "8", (
        f"part 3 was opened with the wrong question count: {r3['studio']}"
    )
    assert r3["row"]["min"] == 8, r3["row"]

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
