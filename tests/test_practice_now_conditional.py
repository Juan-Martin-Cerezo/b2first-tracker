"""Phase 103: "Practise this now" belongs to rest days only.

On a session day the card is hidden entirely (no border, no gap). On a rest day
it is the main piece: three one-tap sources with their real duration. Changing
the schedule and repainting flips the visibility without a reload.
"""
import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TODAY = WD[datetime.now().weekday()]
DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
OTHER = [d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
         if d != TODAY.lower()]


def seed(pg, days):
    schedule = [{"day": DAY_NUM[d], "time": "17:00"} for d in days]
    pg.evaluate(
        """([schedule]) => {
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
            D.settings.rotationMode = 'by-part';
            D.settings.itemsPerSession = 2;
            save();
            refreshAll();
        }""",
        [schedule],
    )
    pg.wait_for_timeout(300)


READ_JS = """() => {
    const box = document.getElementById('practiceNow');
    const links = [...box.querySelectorAll('a')];
    return {
        display: getComputedStyle(box).display,
        height: Math.round(box.getBoundingClientRect().height),
        links: links.length,
        texts: links.map(a => a.innerText),
        rest: !!document.querySelector('#todaySession [data-rest]'),
        rows: document.querySelectorAll('#todaySession .ts-row').length,
    };
}"""


def set_schedule(pg, day_num):
    return pg.evaluate(
        """(day) => {
            window.__phase103 = 'kept';
            D.settings.schedule = [{day: day, time: '17:00'}];
            save();
            repaintScheduleDrivenViews();
            return window.__phase103;
        }""",
        day_num,
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
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(250)

    # 1. A session day hides it completely.
    seed(pg, [TODAY.lower(), OTHER[0]])
    session = pg.evaluate(READ_JS)
    assert not session["rest"], f"the seeded day is not a session day: {session}"
    assert session["display"] == "none", (
        f"Practise this now is shown on a session day: {session}"
    )
    assert session["height"] == 0 and session["links"] == 0, (
        f"the hidden card still takes space or keeps links: {session}"
    )
    OUT["1_session_day"] = session

    # 2. A rest day makes it the main piece: three links, each with its minutes.
    seed(pg, [OTHER[0]])
    rest = pg.evaluate(READ_JS)
    assert rest["rest"] and rest["rows"] == 0, (
        f"the rest day invented a session: {rest}"
    )
    assert rest["display"] != "none", f"Practise this now is hidden on a rest day: {rest}"
    assert rest["links"] == 3, f"the rest day shows {rest['links']} links, not 3: {rest}"
    for text in rest["texts"]:
        assert "min" in text, f"a link does not carry its duration: {text!r}"
    OUT["2_rest_day"] = rest

    # 3. Changing the schedule and repainting flips it, without a reload.
    assert set_schedule(pg, DAY_NUM[TODAY.lower()]) == "kept", "the page reloaded"
    pg.wait_for_timeout(200)
    after = pg.evaluate(READ_JS)
    assert after["display"] == "none", (
        f"the card stayed visible after the day became a session day: {after}"
    )
    assert pg.evaluate("window.__phase103") == "kept", "the page reloaded"

    assert set_schedule(pg, DAY_NUM[OTHER[0]]) == "kept", "the page reloaded"
    pg.wait_for_timeout(200)
    back = pg.evaluate(READ_JS)
    assert back["display"] != "none" and back["links"] == 3, (
        f"the card did not come back on the rest day: {back}"
    )
    OUT["3_schedule_flip"] = {"session_day": after, "rest_day": back}

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
