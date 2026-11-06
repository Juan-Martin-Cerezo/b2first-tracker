"""Phase 103: Today is one centered column that never scrolls sideways.

The card keeps one session block and names each unit once, Start is a real
44x44 target, and the column is centered at 320, 380, 768 and 1280 px. Each
width leaves a screenshot in tests/out/today_<width>.png.
"""
import json
import os
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
WIDTHS = (320, 380, 768, 1280)
OUT = {}

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TODAY = WD[datetime.now().weekday()]
DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
OTHER = [d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
         if d != TODAY.lower()]


def seed(pg, per=2):
    schedule = [{"day": DAY_NUM[TODAY.lower()], "time": "17:00"},
                {"day": DAY_NUM[OTHER[0]], "time": "15:30"}]
    pg.evaluate(
        """([schedule, per]) => {
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
            D.settings.itemsPerSession = per;
            save();
            refreshAll();
        }""",
        [schedule, per],
    )
    pg.wait_for_timeout(300)


MEASURE = """() => {
    const doc = document.documentElement;
    const card = document.getElementById('todaySession');
    const r = card.getBoundingClientRect();
    const row = card.querySelector('.ts-row:not(.ts-next-unit)');
    const start = row ? row.querySelector('button') : null;
    const sr = start ? start.getBoundingClientRect() : null;
    const text = card.innerText;
    const labels = row
        ? (row.dataset.units || '').split(',').filter(Boolean)
            .map(u => {
                const p = u.split(':');
                return queueUnitLabel({skill: p[0], value: p[1]});
            })
        : [];
    const count = needle => {
        if (!needle) return 0;
        let n = 0, i = 0;
        while ((i = text.indexOf(needle, i)) >= 0) { n++; i += needle.length; }
        return n;
    };
    return {
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        centeredAt: (r.left + r.right) / 2,
        cardWidth: Math.round(r.width),
        rows: card.querySelectorAll('.ts-row:not(.ts-next-unit)').length,
        labels: labels,
        occurrences: labels.map(count),
        time: row ? (row.dataset.time || '') : '',
        timeCount: row ? count(row.dataset.time || '') : 0,
        start: sr ? {w: Math.round(sr.width), h: Math.round(sr.height)} : null,
    };
}"""


with sync_playwright() as p:
    os.makedirs(OUT_DIR, exist_ok=True)
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
    seen = {}
    for width in WIDTHS:
        pg.set_viewport_size({"width": width, "height": 900 if width >= 768 else 720})
        pg.evaluate("window.scrollTo(0, 0)")
        pg.wait_for_timeout(220)
        state = pg.evaluate(MEASURE)

        assert state["scrollWidth"] <= state["clientWidth"] + 1, (
            f"{width}px: Today scrolls sideways: {state}"
        )
        assert len(state["labels"]) == 2, f"{width}px: no two-unit session: {state}"
        assert state["rows"] == 1, f"{width}px: {state['rows']} session blocks: {state}"
        assert state["occurrences"] == [1, 1], (
            f"{width}px: the units are repeated inside the card: {state}"
        )
        if state["time"]:
            assert state["timeCount"] == 1, (
                f"{width}px: the time is repeated: {state}"
            )
        assert state["start"] is not None, f"{width}px: Start is missing: {state}"
        assert state["start"]["w"] >= 44 and state["start"]["h"] >= 44, (
            f"{width}px: Start is {state['start']}, need 44x44"
        )
        offset = abs(state["centeredAt"] - state["clientWidth"] / 2)
        assert offset <= 8, (
            f"{width}px: the card is not centered ({offset:.1f}px off): {state}"
        )
        if state["clientWidth"] >= 600:
            assert 520 <= state["cardWidth"] <= 600, (
                f"{width}px: the column is {state['cardWidth']}px wide"
            )

        pg.screenshot(path=os.path.join(OUT_DIR, f"today_{width}.png"), full_page=True)
        seen[str(width)] = {
            "card": state["cardWidth"],
            "offset": round(offset, 2),
            "start": state["start"],
            "scrollWidth": state["scrollWidth"],
            "clientWidth": state["clientWidth"],
        }

    OUT["widths"] = seen
    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
