"""Weekly summary: planned vs real minutes per skill over the last 4 weeks.

Both series are read back from D.log. A row contributes its own plan tag (or
the session table for the unit it stands for) to the planned side and its `min`
to the real side; the four ISO weeks (current + previous three) are averaged as
weekly totals. With fewer than two weeks of history the card says "Not enough
data yet" instead of inventing an average from a single week.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"

SEED = """(rows) => {
    D.log = rows.map((r, i) => Object.assign({created_at: Date.now() - i}, r));
    D.log.sort((a, b) => (b.date || '').localeCompare(a.date || '')
        || ((b.created_at || 0) - (a.created_at || 0)));
    save();
    refreshAll();
}"""

# Dates are built with the app's own helpers, so the seed always lands in the
# current ISO week and the three before it.
ONE_WEEK = """() => {
    const d = n => _addDaysKey(dayKey(new Date()), -n);
    return [
        {type: 'ue', part: 1, date: d(0), min: 6, unit: {skill: 'rue', value: 1, min: 8}},
        {type: 'lp', part: 1, date: d(0), min: 10, unit: {skill: 'l', value: 1, min: 10}},
        {type: 'w', kind: 'Essay', date: d(0), min: 20, unit: {skill: 'w', value: 'Essay', min: 40}},
        {type: 'sp', part: 1, date: d(0), min: 3, unit: {skill: 'sp', value: 1, min: 4}},
    ];
}"""

FOUR_WEEKS = """() => {
    const d = n => _addDaysKey(dayKey(new Date()), -n);
    const offsets = [0, 7, 14, 21];
    const rows = [];
    // Reading: five units in total, two of them in the current week. If the
    // card averaged sessions instead of weekly totals this would be 8, not 10.
    rows.push({type: 'ue', part: 1, date: d(0), min: 6,
        unit: {skill: 'rue', value: 1, min: 8}});
    rows.push({type: 'ue', part: 2, date: d(0), min: 6,
        unit: {skill: 'rue', value: 2, min: 8}});
    rows.push({type: 'ue', part: 3, date: d(7), min: 6,
        unit: {skill: 'rue', value: 3, min: 8}});
    rows.push({type: 'ue', part: 4, date: d(14), min: 6,
        unit: {skill: 'rue', value: 4, min: 8}});
    rows.push({type: 'ue', part: 5, date: d(21), min: 6,
        unit: {skill: 'rue', value: 5, min: 8}});
    // One unit of each other skill per week.
    offsets.forEach((o, i) => {
        rows.push({type: 'lp', part: i + 1, date: d(o), min: 10,
            unit: {skill: 'l', value: i + 1, min: 10}});
        const kind = ['Essay', 'Article', 'Report', 'Review'][i];
        rows.push({type: 'w', kind: kind, date: d(o), min: 20,
            unit: {skill: 'w', value: kind, min: 40}});
        rows.push({type: 'sp', part: i + 1, date: d(o), min: 3,
            unit: {skill: 'sp', value: i + 1, min: 4}});
    });
    // Older than the window: it must not move any average.
    rows.push({type: 'ue', part: 6, date: d(35), min: 999,
        unit: {skill: 'rue', value: 6, min: 999}});
    return rows;
}"""

READ = """() => {
    const body = document.getElementById('weekSummaryBody');
    const rows = [...body.querySelectorAll('.ws-row')].map(el => ({
        skill: el.dataset.skill,
        planned: Number(el.dataset.planned),
        real: Number(el.dataset.real),
        text: el.textContent.trim(),
    }));
    const empty = body.querySelector('#weekSummaryEmpty');
    const title = document.querySelector('#weekSummaryCard .metrics-title');
    return {
        rows: rows,
        empty: empty ? empty.textContent.trim() : null,
        title: title ? title.textContent.trim() : '',
        summary: weeklySummary(D.log),
    };
}"""


def seed(pg, rows_js):
    pg.evaluate(SEED, pg.evaluate(rows_js))
    pg.wait_for_timeout(250)
    return pg.evaluate(READ)


def by_skill(state):
    return {r["skill"]: (r["planned"], r["real"]) for r in state["rows"]}


def by_skill_text(state, skill):
    for row in state["rows"]:
        if row["skill"] == skill:
            return row["text"]
    return ""


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    pg.click("nav button[data-view='prog']")
    pg.wait_for_timeout(250)

    # 0. Empty history: no rows, honest message.
    empty = seed(pg, "() => []")
    assert empty["rows"] == [], f"rows on an empty log: {empty}"
    assert empty["empty"] and "Not enough data yet" in empty["empty"], (
        f"empty log does not say there is not enough data: {empty}"
    )
    assert empty["summary"]["weeks"] == 0 and not empty["summary"]["enough"], empty
    out_empty = empty

    # 1. A single week is below the two-week threshold.
    one = seed(pg, ONE_WEEK)
    assert one["rows"] == [], f"one week produced averages: {one}"
    assert one["empty"] and "Not enough data yet" in one["empty"], (
        f"one week is not reported as too little history: {one}"
    )
    assert one["summary"]["weeks"] == 1, one["summary"]

    # 2. Four weeks: weekly totals averaged over the weeks that have history.
    four = seed(pg, FOUR_WEEKS)
    assert four["empty"] is None, f"four weeks still says not enough: {four}"
    assert four["summary"]["weeks"] == 4 and four["summary"]["enough"], four["summary"]
    got = by_skill(four)
    assert got == {
        "rue": (10, 8),   # 5 units × 8 / 4 weeks; 5 × 6 = 30 / 4 = 7.5 → 8
        "l": (10, 10),    # 4 × 10 / 4
        "w": (40, 20),    # 4 × 40 / 4; 4 × 20 / 4
        "sp": (4, 3),     # 4 × 4 / 4; 4 × 3 / 4
    }, f"the per-skill averages are wrong: {got}"
    # The Reading number proves weekly totals, not per-session averages (that
    # would be 8), and that the 35-day-old row is outside the window (999).
    assert got["rue"][0] == 10, got
    for row in four["rows"]:
        assert "min planned" in row["text"] and "min practised" in row["text"], row
    assert "10 min planned, 8 min practised" in by_skill_text(four, "rue"), four
    assert four["title"] == "Last 4 weeks", four["title"]
    out_four = four

    # 3. Spanish reads from the second dictionary.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    es = pg.evaluate(READ)
    assert es["title"] == "Últimas 4 semanas", es["title"]
    assert es["rows"], f"the summary disappeared in Spanish: {es}"
    assert all("min planificados" in r["text"] and "min practicados" in r["text"]
               for r in es["rows"]), es["rows"]
    assert by_skill(es) == got, f"Spanish changed the numbers: {by_skill(es)}"
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    # 4. Both dictionaries carry the keys the card uses.
    missing = pg.evaluate(
        """() => ['week_summary_title','week_summary_sub','week_summary_item',
                  'week_summary_not_enough'].filter(k => !I18N.en[k] || !I18N.es[k])"""
    )
    assert missing == [], f"keys missing from a dictionary: {missing}"

    assert page_errors == [], f"page errors: {page_errors}"
    out = {
        "0_empty": {"rows": out_empty["rows"], "empty": out_empty["empty"]},
        "1_one_week": {"rows": one["rows"], "weeks": one["summary"]["weeks"]},
        "2_four_weeks": by_skill(out_four),
        "3_spanish": by_skill(es),
        "errors": page_errors,
    }
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
