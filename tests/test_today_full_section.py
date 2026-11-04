"""Phase 87: Start on TODAY opens the whole paper in full-section mode.

In `full-section` each planned session is one complete paper, so its Start
button must open that paper's own session — the exam countdown with the
official duration for R&UE/Writing/Listening, and the four-part speaking
session for Speaking — instead of the loose-part filter. Saving from those
sessions must land in D.log with the matching type (`rue`, `fw`, `l`, `sp`).

The four papers are exercised one by one by rotating `sessionOffset` so that
each paper is the one TODAY shows.
"""
import json
from datetime import datetime

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TODAY_INDEX = datetime.now().weekday()  # Mon=0 … Sun=6

# slot type -> (paper select, official duration in seconds, log type)
WRITTEN = {
    "ue": ("rue", 75 * 60, "rue"),
    "l": ("l", 40 * 60, "l"),
    "w": ("w", 80 * 60, "fw"),
}
PAPERS = ["ue", "l", "w", "sp"]


def seed(pg, offset):
    pg.evaluate(
        """(offset) => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 4, days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
                struggles: [], strugglesDeclared: [],
            };
            D.diag = null;
            D.log = [];
            D.errs = [];
            D.sessionOffset = offset;
            D.settings.rotationMode = 'full-section';
            D.settings.customPlan = {};
            save();
            refreshAll();
        }""",
        offset,
    )
    pg.wait_for_timeout(250)


def offset_for(paper_type):
    """Offset that puts `paper_type` on today's slot.

    The seven-day plan is rotated as a whole; slot i starts at type
    (i + offset) % 7 and the four papers cycle, so j = paper index works.
    """
    j = PAPERS.index(paper_type)
    return (j - TODAY_INDEX) % 7


def today_row(pg):
    return pg.evaluate(
        """() => {
            const row = document.querySelector('#todaySession .ts-row');
            if (!row) return null;
            return {type: row.dataset.type, min: Number(row.dataset.min),
                    title: (row.querySelector('.ts-title') || {}).textContent || ''};
        }"""
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

    for paper in PAPERS:
        offset = offset_for(paper)
        seed(pg, offset)
        row = today_row(pg)
        assert row is not None, f"TODAY has no session for {paper} (offset {offset})"
        assert row["type"] == paper, (
            f"offset {offset} put {row['type']} on TODAY instead of {paper}: {row}"
        )

        pg.click("#todaySession .ts-row button")
        pg.wait_for_timeout(300)

        if paper == "sp":
            pg.wait_for_function(
                "() => SP_EXAM.full && SP_EXAM.session && SP_EXAM.screen === 'brief'",
                timeout=15000,
            )
            state = pg.evaluate(
                """() => ({
                    full: !!SP_EXAM.full,
                    screen: SP_EXAM.screen,
                    parts: (SP_EXAM.session.plan.parts || []).map(x => x.part),
                    overlay: getComputedStyle(document.getElementById('spxOverlay')).display,
                    solo: getComputedStyle(document.getElementById('soloModal')).display,
                })"""
            )
            assert state["full"] is True, f"Speaking did not start the full paper: {state}"
            assert state["parts"] == [1, 2, 3, 4], (
                f"Speaking started a subset of the paper: {state}"
            )
            assert state["overlay"] != "none", f"the speaking overlay is not open: {state}"
            assert state["solo"] == "none", f"the per-part modal opened instead: {state}"

            saved = pg.evaluate(
                """() => saveSP({
                    bands: {grammar_vocabulary: 5, discourse_management: 5,
                            pronunciation: null, interactive_communication: 5},
                    part: 2, duration_s: 120, full: true, parts: []
                })"""
            )
            assert saved["type"] == "sp", f"the full speaking session did not log `sp`: {saved}"
            assert saved.get("full") is True and saved.get("parts") == [1, 2, 3, 4], (
                f"the full speaking row is not one whole paper: {saved}"
            )
            OUT[paper] = {"row": row, "session": state, "log": saved}

            pg.evaluate("() => { SP_EXAM.close(); }")
            pg.wait_for_timeout(200)
            continue

        expected_paper, official, log_type = WRITTEN[paper]
        state = pg.evaluate(
            """() => ({
                exPaper: exPaper,
                exLeft: exLeft,
                running: !!exIv,
                view: (document.querySelector('.view.active') || {}).id || '',
                timer: (document.getElementById('exTimer') || {}).textContent || '',
                solo: getComputedStyle(document.getElementById('soloModal')).display,
            })"""
        )
        assert state["exPaper"] == expected_paper, (
            f"Start for {paper} opened the wrong paper: {state}"
        )
        assert abs(state["exLeft"] - official) <= 2, (
            f"{paper} did not start its official timer ({official}s): {state}"
        )
        assert state["running"] is True, f"{paper} did not start the countdown: {state}"
        assert state["view"] == "v-exam", f"{paper} did not open the exam view: {state}"
        assert state["solo"] == "none", f"{paper} opened the per-part modal: {state}"

        # Save through the session's own form and check the log type. The
        # register is hidden until the countdown ends, so its fields are set
        # directly rather than clicked.
        if paper == "w":
            fields = {"exW1": "14", "exW2": "12", "exMin": "70"}
        elif paper == "l":
            fields = {"exOk": "22", "exP2": "1", "exMin": "70"}
        else:
            fields = {"exOk": "40", "exMin": "70"}
        pg.evaluate(
            """(fields) => {
                Object.keys(fields).forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.value = fields[id];
                });
                exSave();
            }""",
            fields,
        )
        pg.wait_for_timeout(150)
        saved = pg.evaluate("() => D.log[0]")
        assert saved["type"] == log_type, (
            f"{paper} saved as `{saved.get('type')}` instead of `{log_type}`: {saved}"
        )
        OUT[paper] = {"row": row, "session": state, "log": {"type": saved["type"]}}

        # A click on Today must not leave the previous countdown running.
        pg.evaluate("() => { exResetUser(); }")
        pg.click("nav button[data-view='hoy']")
        pg.wait_for_timeout(200)

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
