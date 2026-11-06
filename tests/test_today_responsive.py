"""Phase 106: Today is readable at every width, not just non-scrolling.

The card keeps one session block and names each unit once. On top of that the
title must get real width (>=200px at 320, >=240 otherwise) and wrap by word
into at most three lines, the action buttons must not clip their text, the
bottom bar must stay inside the viewport and the session card must not slide
under it. Each width leaves a screenshot in tests/out/today_<width>.png.
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
    const nav = document.getElementById('sideNav');
    const nr = nav.getBoundingClientRect();
    const row = card.querySelector('.ts-row:not(.ts-next-unit)');
    const buttons = row ? Array.from(row.querySelectorAll('button')) : [];
    const start = buttons[0] || null;
    const fast = buttons[1] || null;
    const sr = start ? start.getBoundingClientRect() : null;
    const title = row ? row.querySelector('.ts-title') : null;
    const tcs = title ? getComputedStyle(title) : null;
    const tr = title ? title.getBoundingClientRect() : null;
    const lineHeight = tcs ? parseFloat(tcs.lineHeight) : 0;
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
    const visibleTextEls = root => Array.from(root.querySelectorAll('*')).filter(el => {
        const own = Array.from(el.childNodes).some(
            n => n.nodeType === 3 && n.textContent.trim());
        if (!own) return false;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const b = el.getBoundingClientRect();
        if (b.width < 1 || b.height < 1) return false;
        // clipped labels (icon-only nav) are not visible text
        if (cs.position === 'absolute' && b.width <= 1) return false;
        return true;
    });
    const narrow = [];
    for (const root of [document.getElementById('v-hoy'), nav]) {
        for (const el of visibleTextEls(root)) {
            if (el.clientWidth < 40) {
                narrow.push({tag: el.tagName, cls: el.className,
                             w: el.clientWidth,
                             text: (el.textContent || '').trim().slice(0, 40)});
            }
        }
    }
    const navItems = Array.from(nav.querySelectorAll('button[data-view], #navMoreBtn'))
        .filter(el => getComputedStyle(el).display !== 'none')
        .map(el => {
            const b = el.getBoundingClientRect();
            return {view: el.dataset.view || 'more',
                    left: b.left, right: b.right,
                    w: Math.round(b.width)};
        });
    const box = el => el ? {
        cw: el.clientWidth, sw: el.scrollWidth,
        w: Math.round(el.getBoundingClientRect().width),
    } : null;
    return {
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        viewportWidth: window.innerWidth,
        centeredAt: (r.left + r.right) / 2,
        cardWidth: Math.round(r.width),
        cardBottom: r.bottom,
        navTop: nr.top,
        navFixedBottom: getComputedStyle(nav).position === 'fixed',
        rows: card.querySelectorAll('.ts-row:not(.ts-next-unit)').length,
        labels: labels,
        occurrences: labels.map(count),
        time: row ? (row.dataset.time || '') : '',
        timeCount: row ? count(row.dataset.time || '') : 0,
        start: sr ? {w: Math.round(sr.width), h: Math.round(sr.height)} : null,
        title: title ? {
            cw: title.clientWidth,
            w: Math.round(tr.width),
            h: Math.round(tr.height),
            lineHeight: Math.round(lineHeight * 100) / 100,
            lines: lineHeight ? Math.round(tr.height / lineHeight) : 0,
            wrap: tcs.whiteSpace,
            wordBreak: tcs.wordBreak,
            overflowWrap: tcs.overflowWrap,
        } : null,
        startBox: box(start),
        fastBox: box(fast),
        navItems: navItems,
        narrowText: narrow,
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
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(250)

    seed(pg)
    seen = {}
    for width in WIDTHS:
        pg.set_viewport_size({"width": width, "height": 900 if width >= 768 else 720})
        pg.evaluate("window.scrollTo(0, 0)")
        pg.wait_for_timeout(220)
        state = pg.evaluate(MEASURE)

        # -- document does not scroll sideways ------------------------------
        assert state["scrollWidth"] <= state["clientWidth"] + 1, (
            f"{width}px: Today scrolls sideways: {state}"
        )
        # -- one session block, each unit and the time named once ------------
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

        # -- centered column -------------------------------------------------
        offset = abs(state["centeredAt"] - state["clientWidth"] / 2)
        assert offset <= 8, (
            f"{width}px: the card is not centered ({offset:.1f}px off): {state}"
        )
        if state["clientWidth"] >= 600:
            assert 520 <= state["cardWidth"] <= 600, (
                f"{width}px: the column is {state['cardWidth']}px wide"
            )

        # -- title gets real width and wraps by word, not by character ------
        t = state["title"]
        assert t is not None, f"{width}px: no session title: {state}"
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

        # -- action buttons keep their text whole ---------------------------
        for name in ("startBox", "fastBox"):
            b = state[name]
            assert b is not None, f"{width}px: {name} button missing: {state}"
            assert b["sw"] <= b["cw"] + 1, (
                f"{width}px: {name} text is clipped "
                f"(scrollWidth {b['sw']} > clientWidth {b['cw']}): {state}"
            )

        # -- no visible text block is crushed below 40px -------------------
        assert state["narrowText"] == [], (
            f"{width}px: visible text blocks under 40px: {state['narrowText']}"
        )

        # -- bottom bar items stay inside the viewport ---------------------
        assert state["navItems"], f"{width}px: no nav items: {state}"
        for item in state["navItems"]:
            assert item["right"] <= state["viewportWidth"] + 1, (
                f"{width}px: nav item {item['view']} overflows right: {state}"
            )
            assert item["left"] >= -1, (
                f"{width}px: nav item {item['view']} overflows left: {state}"
            )

        # -- the card never slides under a fixed bottom bar ----------------
        if state["navFixedBottom"]:
            assert state["cardBottom"] <= state["navTop"] + 1, (
                f"{width}px: the session card overlaps the bottom bar "
                f"(card {state['cardBottom']} > nav {state['navTop']}): {state}"
            )

        pg.screenshot(path=os.path.join(OUT_DIR, f"today_{width}.png"), full_page=True)
        seen[str(width)] = {
            "card": state["cardWidth"],
            "offset": round(offset, 2),
            "start": state["start"],
            "title": {
                "clientWidth": state["title"]["cw"],
                "lines": state["title"]["lines"],
                "height": state["title"]["h"],
            },
            "startBox": state["startBox"],
            "fastBox": state["fastBox"],
            "nav": [{"view": i["view"], "w": i["w"]} for i in state["navItems"]],
            "scrollWidth": state["scrollWidth"],
            "clientWidth": state["clientWidth"],
        }

    OUT["widths"] = seen
    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
