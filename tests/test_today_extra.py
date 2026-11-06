"""Phase 88: TODAY on a rest day offers an extra session that moves nothing.

The plan has no slot for today, so the TODAY card must say so and offer an
"Extra session". That entry point opens the solo logger and whatever it saves
is tagged `extra`: the rotation card keeps the same position and the planned
week and `sessionOffset` stay exactly where they were. The label is bilingual.
"""
import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TODAY = WD[datetime.now().weekday()]
OTHER_L = WD[(datetime.now().weekday() + 1) % 7].lower()
DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}

READ_JS = """() => {
    const slots = buildWeeklyPlan(D).slots.map(sl => ({
        day: sl.day,
        type: sl.type,
        parts: slotParts(sl).join(','),
        min: sl.min,
        title: slotTitleText(sl),
    }));
    const upcoming = [...document.querySelectorAll('#planUpcomingPreview .up-row .badge')]
        .map(el => el.textContent.trim());
    const btn = document.getElementById('todayExtraBtn');
    return {
        rest: !!document.querySelector('#todaySession [data-rest]'),
        extraBtn: btn ? {text: btn.textContent.trim(), visible: btn.offsetParent !== null} : null,
        todayText: document.getElementById('todaySession').innerText,
        slots: slots,
        offset: D.sessionOffset,
        rotation: {
            mode: (document.querySelector('#rotationCardBody .rot-mode') || {}).textContent || '',
            upcoming: upcoming,
        },
        solo: getComputedStyle(document.getElementById('soloModal')).display,
    };
}"""


def seed(pg):
    """Rest day (today is not among the chosen days) with a known rotation.

    One logged R&UE part 1 puts the rotation at its first item; part 2 is the
    next one, so any extra row that leaked into the count would show up as
    "2 sessions logged" and "current: Part 2".
    """
    pg.evaluate(
        """([other, otherDay]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: [other],
                struggles: [], strugglesDeclared: [],
            };
            D.settings.schedule = [{day: otherDay, time: '15:30'}];
            D.diag = null;
            D.log = [{date: today(), type: 'ue', part: 1, correct: 5, total: 8, min: 10}];
            D.errs = [];
            D.sessionOffset = 2;
            D.settings.rotationMode = 'by-part';
            D.settings.customPlan = {};
            save();
            refreshAll();
        }""",
        [OTHER_L, DAY_NUM[OTHER_L]],
    )
    pg.wait_for_timeout(250)


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.on("dialog", lambda d: d.dismiss())
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(250)

    # 1. A rest day says so and offers the extra session in English.
    seed(pg)
    before = pg.evaluate(READ_JS)
    assert before["rest"] is True, f"TODAY did not report a rest day: {before}"
    assert "rest day" in before["todayText"].lower(), (
        f"TODAY does not say 'rest day': {before['todayText']!r}"
    )
    assert before["extraBtn"] and before["extraBtn"]["visible"], (
        f"the rest day does not offer an extra session: {before}"
    )
    assert before["extraBtn"]["text"] == "Extra session", (
        f"the extra session label is not English: {before['extraBtn']}"
    )
    assert "One exercise per session." in before["rotation"]["mode"], (
        f"the card does not name the active mode: {before['rotation']}"
    )
    assert before["rotation"]["upcoming"][0] == "Writing article", (
        f"the upcoming queue ignores the logged work and the shift: {before['rotation']}"
    )
    OUT["before"] = {"offset": before["offset"], "slots": before["slots"],
                     "rotation": before["rotation"], "label": before["extraBtn"]["text"]}

    # 2. The button opens the solo logger.
    pg.click("#todayExtraBtn")
    pg.wait_for_timeout(200)
    opened = pg.evaluate(READ_JS)
    assert opened["solo"] != "none", f"the extra session did not open the solo logger: {opened}"

    # 3. Saving an extra R&UE part 2 tags the row and leaves the rotation alone.
    pg.select_option("#soloSkill", "ue")
    pg.select_option("#soloPart", "2")
    pg.fill("#soloOk", "5")
    pg.fill("#soloTot", "8")
    pg.fill("#soloMin", "10")
    pg.click("#soloModal button.btn.ok")
    pg.wait_for_timeout(400)

    assert pg.evaluate("() => getComputedStyle(document.getElementById('soloModal')).display") == "none", (
        "the solo logger stayed open after saving"
    )
    saved = pg.evaluate(
        "() => { const r = D.log.filter(e => e.extra === true); return r.length === 1 ? r[0] : r; }"
    )
    assert isinstance(saved, dict), f"the extra row is not tagged exactly once: {saved}"
    assert saved["type"] == "ue" and saved["part"] == 2, (
        f"the extra session saved the wrong row: {saved}"
    )
    OUT["saved"] = {"type": saved["type"], "part": saved["part"], "extra": saved.get("extra")}

    after = pg.evaluate(READ_JS)
    assert after["rotation"] == before["rotation"], (
        "the extra session moved the rotation:\n"
        f"before={before['rotation']}\nafter={after['rotation']}"
    )
    assert after["offset"] == before["offset"] == 2, (
        f"the extra session moved sessionOffset: {before['offset']} -> {after['offset']}"
    )
    assert after["slots"] == before["slots"], (
        "the extra session moved the planned week:\n"
        f"before={before['slots']}\nafter={after['slots']}"
    )
    OUT["after"] = {"offset": after["offset"], "slots": after["slots"],
                    "rotation": after["rotation"]}

    # 4. A planned day keeps the normal Start button and offers no extra entry.
    pg.evaluate(
        """([today, todayDay]) => {
            D.profile.days = [today];
            D.settings.schedule = [{day: todayDay, time: '15:30'}];
            save();
            refreshAll();
        }""",
        [TODAY.lower(), DAY_NUM[TODAY.lower()]],
    )
    pg.wait_for_timeout(250)
    planned = pg.evaluate(READ_JS)
    assert planned["rest"] is False, f"the chosen day is still a rest day: {planned}"
    assert planned["extraBtn"] is None, (
        f"a planned day offers an extra session: {planned['extraBtn']}"
    )
    OUT["planned_day"] = {"rest": planned["rest"], "extraBtn": planned["extraBtn"]}

    # 5. The label is translated in Spanish too.
    pg.evaluate(
        "([other, otherDay]) => { D.profile.days = [other];"
        " D.settings.schedule = [{day: otherDay, time: '15:30'}];"
        " save(); refreshAll(); }",
        [OTHER_L, DAY_NUM[OTHER_L]],
    )
    pg.wait_for_timeout(200)
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(300)
    spanish = pg.evaluate(READ_JS)
    assert spanish["extraBtn"] and spanish["extraBtn"]["text"] == "Sesión extra", (
        f"the extra session label is not Spanish: {spanish['extraBtn']}"
    )
    assert "rotación" in spanish["todayText"].lower(), (
        f"the Spanish note is not rendered: {spanish['todayText']!r}"
    )
    OUT["spanish"] = {"label": spanish["extraBtn"]["text"],
                      "text": spanish["todayText"]}

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
