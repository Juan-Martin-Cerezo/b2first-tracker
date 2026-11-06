"""Phase 98: the word "Full" only appears when all the parts are in session.

Plan, Today and "What comes next" are checked in both rotation modes.
A single exercise is named after its part ("Reading part 3"), and full-section
is the only mode allowed to call a paper whole, because it really runs every
part with the official total.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

READ_JS = """() => ({
    rows: buildWeeklyPlan(D).slots.map(s => ({
        type: s.type,
        parts: Array.isArray(s.parts) ? s.parts.slice() : [],
        min: s.min,
        title: slotTitleText(s),
        whole: isWholePaper(s),
    })),
    planTitles: [...document.querySelectorAll('#wpRows .wp-title')].map(e => e.textContent),
    todayText: (document.getElementById('todaySession') || {}).innerText || '',
    nextText: (document.getElementById('nextBox') || {}).innerText || '',
    upcoming: [...document.querySelectorAll('#planUpcomingPreview .up-row .badge')]
        .map(e => e.textContent),
    paperParts: PAPER_PARTS,
    official: {ue: 75, l: 40, w: 80, sp: 14},
})"""


def seed(pg, mode="by-part", per=1):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in ALL_DAYS]
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


def assert_partial_labels(state, label):
    for row in state["rows"]:
        if not row["whole"]:
            assert "Full" not in row["title"], (
                f"{label}: a partial session is called Full: {row}"
            )
    for field in ("planTitles", "todayText", "nextText", "upcoming"):
        text = state[field]
        if isinstance(text, list):
            text = " · ".join(text)
        assert "Full" not in text, (
            f"{label}: 'Full' leaked into {field} on partial sessions: {text!r}"
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
    pg.wait_for_timeout(250)

    # 1. by-part with one exercise per session: no "Full" anywhere.
    seed(pg, "by-part", per=1)
    by_part = pg.evaluate(READ_JS)
    assert_partial_labels(by_part, "by-part")
    assert all(not r["whole"] for r in by_part["rows"]), (
        f"by-part wrongly claims whole papers: {by_part['rows']}"
    )
    assert all(r["title"].startswith(("Reading part", "Listening part", "Writing ", "Speaking part"))
               for r in by_part["rows"]), by_part["rows"]
    OUT["1_by_part"] = by_part

    # 2. itemsPerSession=1 is the explicit phase requirement: still no "Full".
    assert all("Full" not in r["title"] for r in by_part["rows"]), by_part["rows"]

    # 3. full-section: every row is the whole paper, says "Full" and carries
    #    the official total with every part present.
    seed(pg, "full-section", per=1)
    full = pg.evaluate(READ_JS)
    for row in full["rows"]:
        assert row["whole"], f"full-section slot is not the whole paper: {row}"
        assert row["parts"] == full["paperParts"][row["type"]], (
            f"full-section is missing parts: {row} vs {full['paperParts'][row['type']]}"
        )
        assert row["title"].startswith("Full "), f"full-section is not named Full: {row}"
        assert f"({full['official'][row['type']]} min)" in row["title"], (
            f"full-section does not show the official total: {row}"
        )
        assert row["min"] == full["official"][row["type"]], (
            f"full-section duration is not the official one: {row}"
        )
    assert "Full " in full["todayText"] or "Full " in full["nextText"], (
        "Today does not name the whole paper: "
        f"{full['todayText']!r} / {full['nextText']!r}"
    )
    OUT["4_full_section"] = full

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
