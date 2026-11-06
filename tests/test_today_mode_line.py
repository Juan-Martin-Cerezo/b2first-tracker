"""Phase 102: Today's mode line describes the session shown, not the queue.

A Listening day says "2 Listening exercises", a Reading day says
"2 Reading exercises", and full-section names the paper done today.
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


def seed(pg, mode="by-part", per=2, offset=0):
    schedule = [{"day": DAY_NUM[TODAY.lower()], "time": "17:00"},
                {"day": DAY_NUM[OTHER[0]], "time": "15:30"}]
    pg.evaluate(
        """([schedule, mode, per, offset]) => {
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
            save();
            refreshAll();
        }""",
        [schedule, mode, per, offset],
    )
    pg.wait_for_timeout(250)


READ_JS = """() => {
    const row = document.querySelector('#todaySession .ts-row:not(.ts-next-unit)');
    return {
        type: row ? row.dataset.type : null,
        units: row ? (row.dataset.units || '').split(',').filter(Boolean) : [],
        mode: (document.querySelector('#todaySession .ts-mode') || {}).textContent || '',
    };
}"""


def settle_type(pg, mode, wanted, per=2):
    """Rotate the shift until today's planned session is `wanted`."""
    for offset in range(0, 10):
        seed(pg, mode=mode, per=per, offset=offset)
        state = pg.evaluate(READ_JS)
        if state["type"] == wanted:
            return state
    raise AssertionError(f"could not put {wanted} on Today in {mode}")


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    # 1. A Listening day with two units.
    listening = settle_type(pg, "by-part", "l")
    assert len(listening["units"]) == 2, f"the day does not carry two units: {listening}"
    assert listening["mode"] == "2 Listening exercises", (
        f"the mode line does not describe today's Listening session: {listening['mode']!r}"
    )
    assert "Reading" not in listening["mode"], listening["mode"]
    OUT["1_listening"] = listening["mode"]

    # 2. A Reading day says Reading, never Listening.
    reading = settle_type(pg, "by-part", "ue")
    assert len(reading["units"]) == 2, f"the day does not carry two units: {reading}"
    assert reading["mode"] == "2 Reading exercises", (
        f"the mode line does not describe today's Reading session: {reading['mode']!r}"
    )
    assert "Listening" not in reading["mode"], reading["mode"]
    OUT["2_reading"] = reading["mode"]

    # 3. full-section names the paper that is done today, not another one.
    full = settle_type(pg, "full-section", "l", per=1)
    assert full["mode"] == "Today: Full Listening", (
        f"full-section does not name today's paper: {full['mode']!r}"
    )
    for other in ("R&UE", "Writing", "Speaking"):
        assert other not in full["mode"], full["mode"]
    OUT["3_full_listening"] = full["mode"]

    full_rue = settle_type(pg, "full-section", "ue", per=1)
    assert full_rue["mode"] == "Today: Full R&UE", (
        f"full-section does not name today's paper: {full_rue['mode']!r}"
    )
    assert "Listening" not in full_rue["mode"], full_rue["mode"]
    OUT["4_full_rue"] = full_rue["mode"]

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
