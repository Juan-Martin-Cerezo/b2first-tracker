"""Phase 50: the Practice screen holds up at every width.

At 320/380/768/1280 the document never scrolls sideways, every part card
keeps a readable title (the part name gets at least 200px and wraps into at
most three lines without clipping a word) and every button is a 44x44 target
inside the viewport. The cards stay grouped under their paper headings in exam
order, exactly as PARTS declares them: one group per paper, part numbers in
sequence. Each width leaves a screenshot in tests/out/practice_<width>.png.
"""
import json
import os

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
WIDTHS = (320, 380, 768, 1280)
OUT = {}

MEASURE = """() => {
    const doc = document.documentElement;
    const view = document.getElementById('v-practice');
    const list = document.getElementById('partsList');
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

    // Grouping: #partsList is a flat list of .folder headings and .step cards.
    const groups = [];
    let current = null;
    Array.from(list.children).forEach(n => {
        if (n.classList.contains('folder')) {
            current = {name: n.textContent.trim(), parts: []};
            groups.push(current);
        } else if (n.classList.contains('step')) {
            if (!current) groups.push({name: '', parts: []});
            const m = (n.querySelector('h3').textContent || '').match(/Part\\s+(\\d+)/);
            groups[groups.length - 1].parts.push(m ? +m[1] : null);
        }
    });

    const steps = Array.from(list.querySelectorAll('.step'));
    const cards = steps.map(step => {
        const h = step.querySelector('h3');
        const cs = getComputedStyle(h);
        const range = document.createRange();
        range.selectNodeContents(h.firstChild);
        const rects = Array.from(range.getClientRects());
        const tops = [];
        rects.forEach(r => {
            if (!tops.some(t => Math.abs(t - r.top) < 2)) tops.push(r.top);
        });
        return {
            box: box(step),
            name: (h.firstChild.textContent || '').trim(),
            nameWidth: h.clientWidth,
            nameScroll: h.scrollWidth,
            nameHeight: h.getBoundingClientRect().height,
            lines: tops.length,
            right: rects.length ? Math.max(...rects.map(r => r.right)) : 0,
            hRight: h.getBoundingClientRect().right,
            wordBreak: cs.wordBreak,
            whiteSpace: cs.whiteSpace,
        };
    });

    return {
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        viewportWidth: window.innerWidth,
        view: box(view),
        expectedGroups: PARTS.reduce((acc, p) => {
            if (!acc.length || acc[acc.length - 1].name !== p.g) {
                acc.push({name: p.g, parts: []});
            }
            acc[acc.length - 1].parts.push(p.n);
            return acc;
        }, []),
        groups: groups,
        cards: cards,
        buttons: Array.from(view.querySelectorAll('button')).filter(visible)
            .map(b => Object.assign(box(b), {
                text: (b.textContent || '').trim().slice(0, 40),
                sw: b.scrollWidth, cw: b.clientWidth,
            })),
        navFixedBottom: getComputedStyle(document.getElementById('sideNav')).position === 'fixed',
        nav: box(document.getElementById('sideNav')),
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
    pg.evaluate("showView('practice')")
    pg.wait_for_timeout(300)

    assert pg.evaluate("document.querySelector('.view.active').id") == "v-practice", (
        "Practice is not the active view"
    )

    seen = {}
    for width in WIDTHS:
        pg.set_viewport_size({"width": width, "height": 900 if width >= 768 else 720})
        pg.evaluate("window.scrollTo(0, 0)")
        pg.wait_for_timeout(220)
        state = pg.evaluate(MEASURE)

        # -- nothing scrolls sideways --------------------------------------
        assert state["scrollWidth"] <= state["clientWidth"] + 1, (
            f"{width}px: Practice scrolls sideways: "
            f"{state['scrollWidth']} > {state['clientWidth']}"
        )

        # -- every card is grouped under its paper heading, in PARTS order --
        assert state["groups"] == state["expectedGroups"], (
            f"{width}px: the part cards are not grouped by paper as PARTS "
            f"declares: {state['groups']} != {state['expectedGroups']}"
        )
        assert len(state["cards"]) == sum(len(g["parts"]) for g in state["groups"]), (
            f"{width}px: {len(state['cards'])} cards for the grouped parts"
        )

        # -- part names stay readable and unclipped ------------------------
        for i, card in enumerate(state["cards"]):
            assert card["name"].startswith("Part "), (
                f"{width}px: card {i} has no part name: {card}"
            )
            assert card["nameWidth"] >= 200, (
                f"{width}px: part name {card['name']!r} is only "
                f"{card['nameWidth']}px wide (need >= 200)"
            )
            assert card["nameScroll"] <= card["nameWidth"] + 1, (
                f"{width}px: part name {card['name']!r} clips its text: {card}"
            )
            assert 1 <= card["lines"] <= 3, (
                f"{width}px: part name {card['name']!r} takes {card['lines']} "
                f"lines (need 1..3): {card}"
            )
            assert card["right"] <= card["hRight"] + 1, (
                f"{width}px: part name {card['name']!r} spills out of its "
                f"heading: {card}"
            )
            assert card["wordBreak"] != "break-all", (
                f"{width}px: part name {card['name']!r} breaks words "
                f"character by character: {card}"
            )
            assert card["whiteSpace"] != "nowrap", (
                f"{width}px: part name {card['name']!r} cannot wrap: {card}"
            )
            assert card["box"]["l"] >= -1 and card["box"]["r"] <= state["viewportWidth"] + 1, (
                f"{width}px: part card {i} leaves the viewport: {card['box']}"
            )

        # -- every button is a 44x44 target inside the viewport ------------
        assert state["buttons"], f"{width}px: no buttons on Practice"
        for b in state["buttons"]:
            assert b["w"] >= 44 and b["h"] >= 44, (
                f"{width}px: button {b['text']!r} is {b['w']}x{b['h']}, "
                f"need 44x44"
            )
            assert b["l"] >= -1 and b["r"] <= state["viewportWidth"] + 1, (
                f"{width}px: button {b['text']!r} leaves the viewport: {b}"
            )
            assert b["sw"] <= b["cw"] + 1, (
                f"{width}px: button {b['text']!r} clips its text: {b}"
            )

        pg.screenshot(path=os.path.join(OUT_DIR, f"practice_{width}.png"), full_page=True)
        seen[str(width)] = {
            "scrollWidth": state["scrollWidth"],
            "groups": [{"name": g["name"], "parts": g["parts"]} for g in state["groups"]],
            "cards": len(state["cards"]),
            "nameWidths": sorted({round(c["nameWidth"]) for c in state["cards"]}),
            "maxLines": max(c["lines"] for c in state["cards"]),
            "buttons": len(state["buttons"]),
        }

    OUT["widths"] = seen
    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
