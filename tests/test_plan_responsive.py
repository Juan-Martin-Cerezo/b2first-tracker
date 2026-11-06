"""Phase 49: the Plan screen holds up at every width, exactly like Today.

The page is one centered column capped at 560px. At 320 the day rows, the
selects and the buttons still fit: nothing is clipped, nothing pushes the
document sideways, every target is at least 44x44 and the bottom bar never
covers the last card. The title gets real width (>=200px at 320, >=240
otherwise) and wraps by word into at most three lines. Each width leaves a
screenshot in tests/out/plan_<width>.png.
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
                {"day": DAY_NUM[OTHER[0]], "time": "15:30"},
                {"day": DAY_NUM[OTHER[1]], "time": "10:00"}]
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
    const shell = document.querySelector('#v-plan .plan-shell');
    const nav = document.getElementById('sideNav');
    const nr = nav.getBoundingClientRect();
    const title = shell.querySelector('.page-title');
    const tcs = getComputedStyle(title);
    const lineHeight = parseFloat(tcs.lineHeight);
    const tr = title.getBoundingClientRect();
    const visible = el => {
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const b = el.getBoundingClientRect();
        return b.width > 0.5 && b.height > 0.5;
    };
    const box = el => {
        const b = el.getBoundingClientRect();
        return {l: b.left, r: b.right, t: b.top, b: b.bottom,
                w: b.width, h: b.height};
    };
    const rows = Array.from(shell.querySelectorAll('#wpRows .wp-row'));
    const cards = Array.from(shell.querySelectorAll('.card'));
    return {
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        viewportWidth: window.innerWidth,
        shell: box(shell),
        slotCount: (typeof WEEK_PLAN !== 'undefined' && WEEK_PLAN && WEEK_PLAN.slots)
            ? WEEK_PLAN.slots.length : -1,
        title: {
            cw: title.clientWidth,
            w: Math.round(tr.width),
            h: Math.round(tr.height),
            lineHeight: Math.round(lineHeight * 100) / 100,
            lines: lineHeight ? Math.round(tr.height / lineHeight) : 0,
            wordBreak: tcs.wordBreak,
            wrap: tcs.whiteSpace,
        },
        rows: rows.map(r => {
            const t = r.querySelector('.wp-title');
            const btn = r.querySelector('button');
            return {
                box: box(r),
                title: {
                    text: (t.textContent || '').trim(),
                    sw: t.scrollWidth, cw: t.clientWidth,
                    w: Math.round(t.getBoundingClientRect().width),
                },
                button: btn ? Object.assign(box(btn), {
                    sw: btn.scrollWidth, cw: btn.clientWidth,
                }) : null,
            };
        }),
        selects: Array.from(shell.querySelectorAll('select')).filter(visible)
            .map(s => Object.assign(box(s), {
                sw: s.scrollWidth, cw: s.clientWidth,
                id: s.id || s.className,
            })),
        buttons: Array.from(shell.querySelectorAll('button')).filter(visible)
            .map(b => Object.assign(box(b), {
                sw: b.scrollWidth, cw: b.clientWidth,
                text: (b.textContent || '').trim().slice(0, 40),
            })),
        navFixedBottom: getComputedStyle(nav).position === 'fixed',
        nav: {top: nr.top, bottom: nr.bottom},
        lastCard: cards.length ? box(cards[cards.length - 1]) : null,
        navItems: Array.from(nav.querySelectorAll('button[data-view], #navMoreBtn'))
            .filter(visible)
            .map(el => {
                const b = el.getBoundingClientRect();
                return {view: el.dataset.view || 'more',
                        left: b.left, right: b.right};
            }),
    };
}"""


def title_min(width):
    return 200 if width == 320 else 240


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
    pg.evaluate("showView('plan')")
    pg.wait_for_timeout(300)

    seed(pg)
    seen = {}
    for width in WIDTHS:
        pg.set_viewport_size({"width": width, "height": 900 if width >= 768 else 720})
        pg.evaluate("window.scrollTo(0, 0)")
        pg.wait_for_timeout(220)
        state = pg.evaluate(MEASURE)

        # -- document does not scroll sideways ------------------------------
        assert state["scrollWidth"] <= state["clientWidth"] + 1, (
            f"{width}px: Plan scrolls sideways: {state}"
        )

        # -- one centered column, capped like Today -------------------------
        shell = state["shell"]
        offset = abs((shell["l"] + shell["r"]) / 2 - state["clientWidth"] / 2)
        assert offset <= 8, (
            f"{width}px: the Plan column is not centered ({offset:.1f}px off): {state}"
        )
        if state["clientWidth"] >= 600:
            assert 520 <= shell["w"] <= 600, (
                f"{width}px: the Plan column is {shell['w']}px wide, not the "
                f"560px column Today uses: {state}"
            )

        # -- title gets real width and wraps by word, not by character ------
        t = state["title"]
        assert t["cw"] >= title_min(width), (
            f"{width}px: the title block is only {t['cw']}px wide "
            f"(need >= {title_min(width)}): {state}"
        )
        assert t["lines"] <= 3, (
            f"{width}px: the title takes {t['lines']} lines: {state}"
        )
        assert t["h"] <= 3 * t["lineHeight"] + 4, (
            f"{width}px: the title is {t['h']}px tall for line-height "
            f"{t['lineHeight']}: {state}"
        )
        assert t["wordBreak"] != "break-all", (
            f"{width}px: the title breaks words character by character: {state}"
        )
        assert t["wrap"] != "break-spaces", (
            f"{width}px: the title keeps break-spaces: {state}"
        )

        # -- the day rows exist, fit in the column and keep their text ------
        rows = state["rows"]
        assert state["slotCount"] >= 2, f"{width}px: no plan slots: {state}"
        assert len(rows) == state["slotCount"], (
            f"{width}px: {len(rows)} day rows for {state['slotCount']} slots: {state}"
        )
        for i, row in enumerate(rows):
            b = row["box"]
            assert b["l"] >= shell["l"] - 1 and b["r"] <= shell["r"] + 1, (
                f"{width}px: day row {i} leaves the column: {row} / {shell}"
            )
            assert row["title"]["text"], f"{width}px: day row {i} has no title: {row}"
            assert row["title"]["sw"] <= row["title"]["cw"] + 1, (
                f"{width}px: day row {i} clips its title "
                f"(scrollWidth {row['title']['sw']} > clientWidth "
                f"{row['title']['cw']}): {row}"
            )
            btn = row["button"]
            assert btn is not None, f"{width}px: day row {i} has no Start: {row}"
            assert btn["w"] >= 44 and btn["h"] >= 44, (
                f"{width}px: day row {i} Start is {btn['w']}x{btn['h']}, need 44x44"
            )
            assert btn["l"] >= shell["l"] - 1 and btn["r"] <= shell["r"] + 1, (
                f"{width}px: day row {i} Start leaves the column: {btn} / {shell}"
            )

        # -- selects stay inside the column --------------------------------
        assert state["selects"], f"{width}px: no selects on PLAN: {state}"
        for sel in state["selects"]:
            assert sel["w"] >= 44, (
                f"{width}px: select {sel['id']} is {sel['w']}px wide: {sel}"
            )
            assert sel["l"] >= shell["l"] - 1 and sel["r"] <= shell["r"] + 1, (
                f"{width}px: select {sel['id']} overflows the column: {sel} / {shell}"
            )
            assert sel["r"] <= state["viewportWidth"] + 1, (
                f"{width}px: select {sel['id']} overflows the viewport: {sel}"
            )

        # -- every button is reachable and keeps its text whole -------------
        assert state["buttons"], f"{width}px: no buttons on PLAN: {state}"
        for b in state["buttons"]:
            assert b["w"] >= 44 and b["h"] >= 44, (
                f"{width}px: button {b['text']!r} is {b['w']}x{b['h']}, need 44x44"
            )
            assert b["l"] >= shell["l"] - 1 and b["r"] <= shell["r"] + 1, (
                f"{width}px: button {b['text']!r} leaves the column: {b} / {shell}"
            )
            assert b["sw"] <= b["cw"] + 1, (
                f"{width}px: button {b['text']!r} clips its text "
                f"(scrollWidth {b['sw']} > clientWidth {b['cw']}): {b}"
            )

        # -- bottom bar items stay inside the viewport ----------------------
        assert state["navItems"], f"{width}px: no nav items: {state}"
        for item in state["navItems"]:
            assert item["right"] <= state["viewportWidth"] + 1, (
                f"{width}px: nav item {item['view']} overflows right: {state}"
            )
            assert item["left"] >= -1, (
                f"{width}px: nav item {item['view']} overflows left: {state}"
            )

        # -- nothing hides under the bar: last card vs nav ------------------
        assert state["lastCard"] is not None, f"{width}px: Plan has no cards: {state}"
        if state["navFixedBottom"]:
            pg.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            pg.wait_for_timeout(200)
            bottom = pg.evaluate(MEASURE)
            assert bottom["lastCard"]["b"] <= bottom["nav"]["top"] + 1, (
                f"{width}px: the last Plan card is hidden under the bottom bar "
                f"(card {bottom['lastCard']['b']} > nav {bottom['nav']['top']}): "
                f"{bottom['lastCard']} / {bottom['nav']}"
            )
        else:
            assert shell["t"] >= state["nav"]["bottom"] - 1, (
                f"{width}px: the Plan column slides under the top bar "
                f"(shell {shell['t']} < nav {state['nav']['bottom']}): {state}"
            )

        pg.screenshot(path=os.path.join(OUT_DIR, f"plan_{width}.png"), full_page=True)
        seen[str(width)] = {
            "shell": {"width": round(shell["w"]), "offset": round(offset, 2)},
            "title": {"clientWidth": t["cw"], "lines": t["lines"],
                      "height": t["h"]},
            "rows": len(rows),
            "selects": [{"id": s["id"], "w": round(s["w"])} for s in state["selects"]],
            "buttons": len(state["buttons"]),
            "navFixedBottom": state["navFixedBottom"],
            "scrollWidth": state["scrollWidth"],
            "clientWidth": state["clientWidth"],
        }

    OUT["widths"] = seen
    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
