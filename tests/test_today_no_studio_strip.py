"""Phase 103: Today has no studio strip any more.

The five buttons that duplicated the plan (Mon A, Fri A, Mon B, Fri B and Mock
Exam) are gone from the markup, their CSS is gone, and the studios stay closed
until the session's own Start opens the one it belongs to.
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


def seed(pg):
    schedule = [{"day": DAY_NUM[TODAY.lower()], "time": "17:00"},
                {"day": DAY_NUM[OTHER[0]], "time": "15:30"}]
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


STRIP_JS = """() => {
    const ids = ['sessionNav', 'navBtnMonA', 'navBtnFriA', 'navBtnMonB',
                 'navBtnFriB', 'navLblMonA', 'navDurMonA'];
    const today = document.getElementById('v-hoy');
    const visible = id => {
        const el = document.getElementById(id);
        return !!el && el.offsetParent !== null;
    };
    return {
        present: ids.filter(id => !!document.getElementById(id)),
        navButtons: today.querySelectorAll('.session-nav-btn').length,
        dataSes: today.querySelectorAll('[data-ses]').length,
        pillTags: document.querySelectorAll('.pill-tag').length,
        navClass: document.querySelectorAll('.session-nav').length,
        text: today.innerText,
        studios: ['studioMonA', 'studioMonB', 'studioFriA', 'studioFriB']
            .filter(visible),
        groups: ['sesA', 'sesB', 'sesFull']
            .filter(id => {
                const el = document.getElementById(id);
                return !!el && getComputedStyle(el).display !== 'none';
            }),
    };
}"""


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

    seed(pg)
    state = pg.evaluate(STRIP_JS)

    assert state["present"] == [], (
        f"the studio strip is still in the DOM: {state['present']}"
    )
    assert state["navButtons"] == 0, f"studio nav buttons inside Today: {state}"
    assert state["dataSes"] == 0, f"studio selectors inside Today: {state}"
    assert state["navClass"] == 0, f".session-nav still in the page: {state}"
    assert state["pillTags"] == 0, f".pill-tag still in the page: {state}"
    assert "mock exam" not in state["text"].lower(), (
        f"Today still names the mock exam: {state['text']!r}"
    )
    assert state["studios"] == [], (
        f"a studio is open before Start: {state['studios']}"
    )
    assert state["groups"] == [], (
        f"a studio group is open before Start: {state['groups']}"
    )
    OUT["resting_state"] = {
        "nav_buttons": state["navButtons"],
        "data_ses": state["dataSes"],
        "open_studios": state["studios"],
        "open_groups": state["groups"],
    }

    # Start is still the door to the session's studio.
    pg.click("#todaySession .ts-row:not(.ts-next-unit) button")
    pg.wait_for_timeout(300)
    opened = pg.evaluate(STRIP_JS)
    assert len(opened["studios"]) == 1, (
        f"Start did not open exactly one studio: {opened['studios']}"
    )
    assert len(opened["groups"]) == 1, (
        f"Start did not open exactly one studio group: {opened['groups']}"
    )
    OUT["after_start"] = {"studios": opened["studios"], "groups": opened["groups"]}

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
