"""Phase 98: sessions are timed by their units, never by a global slotMin.

The unit table has to close with the official B2 First totals (R&UE 75,
Listening 40 including transfer, Writing 80, Speaking 14), a loose part keeps
its own duration, and a session is exactly the sum of the units it contains.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}

TABLE_JS = """() => ({
    rue: UNIT_MIN.rue,
    l: UNIT_MIN.l,
    w: UNIT_MIN.w,
    sp: UNIT_MIN.sp,
})"""


def seed(pg, days, per=1):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
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
            D.settings.schedule = schedule;
            D.settings.rotationMode = 'by-part';
            D.settings.itemsPerSession = per;
            D.settings.rueCycle = [1, 2, 3, 4, 5, 6, 7];
            D.settings.lCycle = [1, 2, 3, 4];
            D.settings.spCycle = [1, 2, 3, 4];
            D.settings.wCycle = ['Essay', 'Article', 'Report', 'Review', 'Email'];
            save();
            refreshAll();
        }""",
        [schedule, per],
    )
    pg.wait_for_timeout(250)


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    # 1. The four papers close with the official totals.
    table = pg.evaluate(TABLE_JS)
    # Writing has two exam tasks: the essay (Part 1) and one Part 2 genre.
    # The genre keys all describe that same second slot.
    sums = {
        "rue": sum(table["rue"].values()),
        "l": sum(table["l"].values()),
        "w": table["w"]["Essay"] + table["w"]["Article"],
        "sp": sum(table["sp"].values()),
    }
    assert abs(sums["rue"] - 75) <= 1, f"R&UE does not add up to 75: {table['rue']} = {sums['rue']}"
    assert abs(sums["l"] - 40) <= 1, f"Listening does not add up to 40: {table['l']} = {sums['l']}"
    assert abs(sums["w"] - 80) <= 1, f"Writing does not add up to 80: {table['w']} = {sums['w']}"
    assert abs(sums["sp"] - 14) <= 1, f"Speaking does not add up to 14: {table['sp']} = {sums['sp']}"

    # 2. No loose part is absurd. R&UE, Listening and Speaking parts stay within
    #    2..25 min. Writing is the documented exception: its two official tasks
    #    are 40 min each, which is the only way two parts can add up to 80.
    for skill in ("rue", "l", "sp"):
        for part, minutes in table[skill].items():
            assert 2 <= minutes <= 25, (
                f"{skill} part {part} is outside 2..25 min: {minutes}"
            )
    for genre, minutes in table["w"].items():
        assert minutes == 40, f"Writing {genre} is not a 40-min official task: {minutes}"
    OUT["1_table"] = {"sums": sums, "table": table}

    # 3. One-part sessions last exactly what the table says (never 45).
    seed(pg, ("mon", "fri"), per=1)
    singles = pg.evaluate(
        """() => rotationQueueSessions(['mon', 'fri'], 1, 0, 4).map(s => ({
            unit: queueUnitLabel(s.units[0]),
            skill: s.units[0].skill,
            value: s.units[0].value,
            min: s.min,
        }))"""
    )
    assert [s["min"] for s in singles] == [8, 10, 40, 2], (
        f"loose-part durations are not the table's: {singles}"
    )
    for s in singles:
        expected = table[s["skill"]].get(str(s["value"])) if s["skill"] != "w" else table["w"][s["value"]]
        assert s["min"] == expected, f"{s['unit']} does not match the table: {s} vs {expected}"
        assert s["min"] != 45, f"{s['unit']} fell back to the old 45-min default: {s}"
    OUT["3_single_part"] = singles

    # 4. A two-part session is exactly the sum of those two units.
    pairs = pg.evaluate(
        """() => rotationQueueSessions(['mon', 'fri'], 2, 0, 4).map(s => ({
            units: s.units.map(queueUnitLabel),
            expected: s.units.reduce((total, u) =>
                total + (u.skill === 'w' ? UNIT_MIN.w[u.value] : UNIT_MIN[u.skill][u.value]), 0),
            min: s.min,
        }))"""
    )
    for s in pairs:
        assert s["min"] == s["expected"], f"the pair is not the exact sum: {s}"
    assert [s["min"] for s in pairs] == [16, 20, 80, 6], (
        f"two-part durations are wrong: {pairs}"
    )
    OUT["4_two_parts"] = pairs

    # 5. The weekly summary total is the sum of the visible plan rows.
    seed(pg, ("mon", "tue", "wed", "thu"), per=1)
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(250)
    summary = pg.evaluate(
        """() => {
            const rows = [...document.querySelectorAll('#wpRows .wp-row')]
                .map(r => Number(r.dataset.min) || 0);
            return {
                rows: rows,
                rowTotal: rows.reduce((a, b) => a + b, 0),
                text: (document.getElementById('wpSummary') || {}).textContent || '',
            };
        }"""
    )
    assert summary["rowTotal"] == 60, f"the visible rows do not add up: {summary['rows']}"
    assert f"{summary['rowTotal']} min" in summary["text"], (
        f"the summary does not match the rows: {summary}"
    )
    OUT["5_summary"] = summary

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
