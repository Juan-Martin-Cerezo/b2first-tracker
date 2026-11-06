"""Phase 100 (phase 99 requirement): the session copy is honest.

A loose part is named after its part and timed from the unit table. "Full",
"whole paper" and "complete test" may only describe a session that really
carries every part of the paper, which is what full-section does.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}
DAYS = ["mon", "fri"]
BANNED = ["full", "whole paper", "complete test"]


def seed(pg, mode="by-part", per=1):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in DAYS]
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
            save();
            refreshAll();
        }""",
        [schedule, mode, per],
    )
    pg.wait_for_timeout(300)


READ_JS = """() => ({
    week: document.getElementById('wpRows').innerText,
    today: document.getElementById('todaySession').innerText,
    next: document.getElementById('nextBox').innerText,
    card: document.getElementById('rotationCard').innerText,
    preview: document.getElementById('wpQueuePreview').innerText,
    slots: buildWeeklyPlan(D).slots.map(s => ({
        type: s.type,
        parts: Array.isArray(s.parts) ? s.parts.slice() : [],
        min: s.min,
        whole: isWholePaper(s),
        title: slotTitleText(s),
    })),
    paperParts: PAPER_PARTS,
    official: {ue: 75, l: 40, w: 80, sp: 14},
})"""


def assert_no_whole_claims(state, label):
    text = " ".join((state["week"], state["today"], state["next"],
                     state["card"], state["preview"])).lower()
    for phrase in BANNED:
        assert phrase not in text, (
            f"{label}: {phrase!r} describes a partial session: {text!r}"
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
    pg.wait_for_timeout(300)

    # 1. by-part with 1, 2 and 3 units per session: never a whole-paper claim.
    seen = {}
    for per in (1, 2, 3):
        seed(pg, "by-part", per)
        state = pg.evaluate(READ_JS)
        assert_no_whole_claims(state, f"by-part per={per}")
        assert all(not row["whole"] for row in state["slots"]), (
            f"by-part per={per} claims whole papers: {state['slots']}"
        )
        seen[str(per)] = [row["title"] for row in state["slots"]]
    OUT["by_part"] = seen

    # 2. A loose part names its part and uses the table duration.
    seed(pg, "by-part", 1)
    single = pg.evaluate(READ_JS)
    titles = pg.evaluate(
        "() => planNextSessions(4).map(s => slotTitleText(s))"
    )
    assert titles[0].startswith("Reading part 1 · 8 min"), titles
    assert titles[1].startswith("Listening part 1 · 10 min"), titles
    assert titles[2].startswith("Writing essay · 40 min"), titles
    assert titles[3].startswith("Speaking part 1 · 2 min"), titles
    OUT["single_parts"] = titles

    # 3. full-section is allowed to say Full because every part is in session.
    seed(pg, "full-section", 1)
    full = pg.evaluate(READ_JS)
    assert "Full " in full["week"], f"full-section is not named: {full['week']!r}"
    for row in full["slots"]:
        assert row["whole"], f"full-section slot is not whole: {row}"
        assert row["parts"] == full["paperParts"][row["type"]], (
            f"full-section is missing parts: {row} vs {full['paperParts'][row['type']]}"
        )
        assert row["title"].startswith("Full "), row
        assert f"({full['official'][row['type']]} min)" in row["title"], row
        assert row["min"] == full["official"][row["type"]], row
    OUT["full_section"] = [row["title"] for row in full["slots"]]

    # 4. Old behaviour phrases are gone from the same screens.
    combined = " ".join(
        (single["week"], single["today"], single["next"],
         single["card"], single["preview"])
    ).lower()
    for stale in ("one item per session", "4-step core cycle",
                  "component by component", "advances one item per session"):
        assert stale not in combined, f"stale copy leaked: {stale!r} in {combined!r}"
    OUT["stale_copy"] = False

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
