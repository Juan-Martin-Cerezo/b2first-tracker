"""Phase 102: Today is one session card, with the information just once.

The old top banner is gone. The single card carries the day, the units and the
duration on its header, the time, the short mode line, Start and Fast-forward.
The week-block line lives in PLAN only.
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


READ_JS = """() => {
    const card = document.getElementById('todaySession');
    const rows = [...card.querySelectorAll('.ts-row:not(.ts-next-unit)')];
    const row = rows[0];
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
        while ((i = card.innerText.indexOf(needle, i)) >= 0) { n++; i += needle.length; }
        return n;
    };
    return {
        rows: rows.length,
        rowText: row ? row.innerText : '',
        labels: labels,
        occurrences: labels.map(count),
        text: card.innerText,
        nextBox: (document.getElementById('nextBox') || {}).innerText || '',
        startLabel: t('common_start'),
        fastForwardLabel: t('next_fast_forward'),
        buttons: row ? [...row.querySelectorAll('button')].map(b => b.innerText.trim()) : [],
        weekBlock: (document.getElementById('wpWeekBlock') || {}).textContent || '',
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

    seed(pg, per=2)
    state = pg.evaluate(READ_JS)

    # 1. Exactly one session block in Today, and each unit named only once.
    assert state["rows"] == 1, f"Today has {state['rows']} session blocks: {state}"
    assert len(state["labels"]) == 2, f"the session does not carry two units: {state}"
    assert state["occurrences"] == [1, 1], (
        f"the units are repeated inside the single card: {state}"
    )
    OUT["1_single_card"] = {"rows": state["rows"], "labels": state["labels"]}

    # 2. The duplicated copy is gone.
    flat = state["text"].lower()
    assert "studio is open below" not in flat, state["text"]
    assert "2 exercises" not in flat, (
        f"the bare exercise count is still painted: {state['text']!r}"
    )
    assert "exercises in one session" not in flat, (
        f"the redundant session sentence is still painted: {state['text']!r}"
    )
    assert "schedule:" not in flat, f"the schedule line is still painted: {state['text']!r}"
    assert "today (" not in flat, f"the old TODAY banner is still painted: {state['text']!r}"
    assert not state["nextBox"].strip(), (
        f"the top banner still has content: {state['nextBox']!r}"
    )
    OUT["2_duplicates"] = False

    # 3. Start and Fast-forward live inside the same card.
    assert state["startLabel"] in state["buttons"], (
        f"Start is not inside the card: {state['buttons']}"
    )
    assert state["fastForwardLabel"] in state["buttons"], (
        f"Fast-forward is not inside the card: {state['buttons']}"
    )
    OUT["3_actions"] = state["buttons"]

    # 4. The week-block line belongs to PLAN, not Today.
    assert "This week:" not in state["text"], (
        f"Today still shows the week block: {state['text']!r}"
    )
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(300)
    plan = pg.evaluate(READ_JS)
    assert "This week:" in plan["weekBlock"], (
        f"PLAN lost its week block line: {plan['weekBlock']!r}"
    )
    assert "next week:" in plan["weekBlock"], plan["weekBlock"]
    OUT["4_week_block_plan_only"] = plan["weekBlock"]

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
