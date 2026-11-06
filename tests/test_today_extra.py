"""Phase 103: a rest day is honest and minimal — no invented session.

The plan has no slot for today, so TODAY shows the day and one short rest
message, and the main piece of the screen is "Practise this now". The old
"Extra session" button and the next-session line are gone: nothing on TODAY
pretends there is a session today, and nothing moves the rotation.
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
    const card = document.getElementById('todaySession');
    const box = document.getElementById('practiceNow');
    return {
        rest: !!card.querySelector('[data-rest]'),
        dayTitle: ((card.querySelector('h2') || {}).textContent || '').trim(),
        rows: card.querySelectorAll('.ts-row').length,
        todayText: card.innerText,
        extraBtn: !!document.getElementById('todayExtraBtn'),
        practice: {
            display: getComputedStyle(box).display,
            links: box.querySelectorAll('a').length,
        },
        slots: buildWeeklyPlan(D).slots.map(sl => ({
            day: sl.day, type: sl.type, min: sl.min, title: slotTitleText(sl),
        })),
        offset: D.sessionOffset,
    };
}"""


def seed(pg, days):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(
        """([schedule]) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: schedule.map(s => s.day),
                struggles: [], strugglesDeclared: [],
            };
            D.settings.schedule = schedule;
            D.diag = null;
            D.log = [];
            D.errs = [];
            D.sessionOffset = 2;
            D.settings.rotationMode = 'by-part';
            save();
            refreshAll();
        }""",
        [schedule],
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

    # 1. A rest day says so, names the day and offers no session.
    seed(pg, [OTHER_L])
    before = pg.evaluate(READ_JS)
    assert before["rest"] is True, f"TODAY did not report a rest day: {before}"
    assert "rest day" in before["todayText"].lower(), (
        f"TODAY does not say 'rest day': {before['todayText']!r}"
    )
    assert before["dayTitle"] and before["dayTitle"] != "Today's session", (
        f"the rest day does not name the day: {before['dayTitle']!r}"
    )
    assert before["rows"] == 0, f"the rest day invented a session: {before}"
    assert before["extraBtn"] is False, (
        f"the rest day still offers an extra session: {before}"
    )
    assert "next session" not in before["todayText"].lower(), (
        f"the next-session line is still painted: {before['todayText']!r}"
    )
    assert before["practice"]["display"] != "none", (
        f"the rest day does not lead with practice: {before['practice']}"
    )
    assert before["practice"]["links"] == 3, (
        f"practise this now shows {before['practice']['links']} links: {before}"
    )
    OUT["1_rest_day"] = {"title": before["dayTitle"], "text": before["todayText"],
                         "practice": before["practice"]}

    # 2. Nothing moved: refreshing keeps the plan and the shift where they were.
    pg.evaluate("refreshAll()")
    pg.wait_for_timeout(200)
    after = pg.evaluate(READ_JS)
    assert after["slots"] == before["slots"], (
        f"the rest day changed the plan:\nbefore={before['slots']}\nafter={after['slots']}"
    )
    assert after["offset"] == before["offset"] == 2, (
        f"the rest day moved sessionOffset: {before['offset']} -> {after['offset']}"
    )
    OUT["2_plan_untouched"] = {"offset": after["offset"], "slots": after["slots"]}

    # 3. A planned day keeps the normal card and offers no extra entry.
    seed(pg, [TODAY.lower()])
    planned = pg.evaluate(READ_JS)
    assert planned["rest"] is False, f"the chosen day is still a rest day: {planned}"
    assert planned["rows"] == 1, f"the planned day has no session card: {planned}"
    assert planned["extraBtn"] is False, f"a planned day offers an extra session: {planned}"
    assert planned["practice"]["display"] == "none", (
        f"a session day still shows Practise this now: {planned['practice']}"
    )
    OUT["3_planned_day"] = {"rest": planned["rest"], "rows": planned["rows"],
                            "practice": planned["practice"]}

    # 4. The rest-day copy is translated too.
    seed(pg, [OTHER_L])
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    spanish = pg.evaluate(READ_JS)
    assert "descanso" in spanish["todayText"].lower(), (
        f"the Spanish rest message is not rendered: {spanish['todayText']!r}"
    )
    assert "rest day" not in spanish["todayText"].lower(), (
        f"the English rest message survived the switch: {spanish['todayText']!r}"
    )
    OUT["4_spanish"] = {"title": spanish["dayTitle"], "text": spanish["todayText"]}

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
