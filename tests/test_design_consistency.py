"""Phase 120: Design system consistency across Today, Exam, Progress, and Plan.

Verifies at 320, 768, and 1280 px across the four tabs (Today, Exam, Progress, Plan):
1. All four tabs use the same computed font-size and font-weight for headings of the same level (h1, h2, h3).
2. All visible <button> elements have height in {44, 48, 52} px, and at most 3 distinct button heights per tab.
3. Computed paddings and gaps of cards and card containers are multiples of 4 px.
4. Zero horizontal scroll in any tab or width.
5. Primary text contrast >= 4.5:1 in both light and dark themes.
6. Screenshots saved to tests/out/design_<tab>_<width>.png.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from helpers import isolated_server, login_owner

OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WIDTHS = (320, 768, 1280)
TABS = (
    ("hoy", "today"),
    ("exam", "exam"),
    ("prog", "progress"),
    ("plan", "plan"),
)

SEED_JS = """
() => {
    const wd = new Date().getDay();
    const nextWd = (wd + 3) % 7;
    D.profile = {
        examDate: null,
        targetGrade: 'B',
        skills: {rue: 3, w: 3, l: 3, sp: 3},
        hoursWeek: 4,
        days: [wd, nextWd],
        struggles: [],
        strugglesDeclared: [],
    };
    D.diag = null;
    D.sessionOffset = 0;
    D.weekOverrides = {};
    D.settings.rotationMode = 'by-part';
    D.settings.itemsPerSession = 2;
    D.settings.schedule = [{day: wd, time: '15:30'}, {day: nextWd, time: '13:00'}];
    D.settings.sessions = D.settings.schedule.slice();
    D.log = [
        {id: 'r1', date: '2026-04-01', created_at: 1000, type: 'ue', part: 1, correct: 6, total: 8, min: 8},
        {id: 'r2', date: '2026-04-02', created_at: 2000, type: 'ue', part: 2, correct: 7, total: 8, min: 8},
        {id: 'r3', date: '2026-04-03', created_at: 3000, type: 'lp', part: 1, correct: 6, total: 8, min: 10},
        {id: 'r4', date: '2026-04-04', created_at: 4000, type: 'w', kind: 'Essay', score: 15, total: 20, min: 35}
    ];
    D.errs = [
        {id: 'e1', date: '2026-04-02', code: 'L-GAP', desc: 'Missed collocation', fix: 'Review unit 2'},
        {id: 'e2', date: '2026-04-03', code: 'G-ERR', desc: 'Wrong tense', fix: 'Check past perfect'}
    ];
    const sorted = getSessionDays();
    const todayKey = PLAN_DAY_ORDER[(wd + 6) % 7];
    const todayIdx = sorted.findIndex(d => d.key === todayKey);
    D.sessionOffset = todayIdx > 0 ? -todayIdx : 0;
    save();
    refreshAll();
}
"""

MEASURE_TAB_JS = """
(viewId) => {
    const doc = document.documentElement;
    const root = document.getElementById('v-' + viewId);
    const isVisible = el => {
        let cur = el;
        while (cur && cur !== doc) {
            const cs = getComputedStyle(cur);
            if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
            cur = cur.parentElement;
        }
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    // 1. Headings (h1, h2, h3)
    const headings = {};
    for (const tag of ['h1', 'h2', 'h3']) {
        const els = Array.from(root.querySelectorAll(tag)).filter(isVisible);
        headings[tag] = els.map(el => {
            const cs = getComputedStyle(el);
            return {
                text: (el.innerText || '').trim().slice(0, 40),
                fontSize: Math.round(parseFloat(cs.fontSize) * 100) / 100,
                fontWeight: String(cs.fontWeight),
                marginBottom: Math.round(parseFloat(cs.marginBottom) || 0),
            };
        });
    }

    // 2. Visible buttons inside tab
    const buttons = Array.from(root.querySelectorAll('button')).filter(isVisible).map(b => {
        const r = b.getBoundingClientRect();
        return {
            text: (b.innerText || b.getAttribute('aria-label') || '').trim().slice(0, 40),
            cls: b.className,
            h: Math.round(r.height),
            w: Math.round(r.width),
        };
    });

    // 3. Cards and card containers paddings & gaps
    const cardEls = Array.from(root.querySelectorAll('.card, .stat-card, .exam-card')).filter(isVisible);
    const cards = cardEls.map(c => {
        const cs = getComputedStyle(c);
        return {
            cls: c.className,
            id: c.id || '',
            padTop: Math.round(parseFloat(cs.paddingTop) || 0),
            padRight: Math.round(parseFloat(cs.paddingRight) || 0),
            padBottom: Math.round(parseFloat(cs.paddingBottom) || 0),
            padLeft: Math.round(parseFloat(cs.paddingLeft) || 0),
            marginBottom: Math.round(parseFloat(cs.marginBottom) || 0),
            rowGap: Math.round(parseFloat(cs.rowGap) || 0),
            colGap: Math.round(parseFloat(cs.columnGap) || 0),
        };
    });

    const containerEls = Array.from(
        root.querySelectorAll('.grid-12, .stat-grid, .exam-select-grid, .today-shell, .today-grid, .plan-shell, #wpRows')
    ).filter(isVisible);
    const containers = containerEls.map(c => {
        const cs = getComputedStyle(c);
        return {
            cls: c.className || c.id,
            rowGap: Math.round(parseFloat(cs.rowGap) || 0),
            colGap: Math.round(parseFloat(cs.columnGap) || 0),
        };
    });

    // 4. Plan specific: uniform .wp-row heights and select == secondary button height (48)
    let planCheck = null;
    if (viewId === 'plan') {
        const wpRows = Array.from(root.querySelectorAll('#wpRows .wp-row')).filter(isVisible);
        const selects = Array.from(root.querySelectorAll('select')).filter(isVisible);
        planCheck = {
            rowHeights: wpRows.map(r => Math.round(r.getBoundingClientRect().height)),
            selectHeights: selects.map(s => Math.round(s.getBoundingClientRect().height)),
        };
    }

    // 5. Exam specific: tabular-nums and right-aligned duration & parts on paper cards
    let examCheck = null;
    if (viewId === 'exam') {
        const paperCards = Array.from(root.querySelectorAll('#examSelectGrid .exam-card')).filter(isVisible);
        examCheck = paperCards.map(c => {
            const cr = c.getBoundingClientRect();
            const minEl = c.querySelector('.exam-card-min');
            const mr = minEl ? minEl.getBoundingClientRect() : null;
            const mcs = minEl ? getComputedStyle(minEl) : null;
            return {
                paper: c.dataset.paper,
                minText: minEl ? minEl.innerText.trim() : '',
                tabularNums: mcs ? mcs.fontVariantNumeric.includes('tabular-nums') : false,
                alignedRight: mr ? (mr.left > cr.left + cr.width * 0.35) : false,
            };
        });
    }

    // 6. Progress specific: consistent chart margins
    let progCheck = null;
    if (viewId === 'prog') {
        const chartIds = ['gEvol', 'gPart', 'gErr', 'gCons'];
        progCheck = chartIds.map(id => {
            const chartBox = document.getElementById(id);
            const card = chartBox ? chartBox.closest('.card') : null;
            const h2 = card ? card.querySelector('h2') : null;
            const sub = card ? card.querySelector('.sub') : null;
            const h2R = h2 ? h2.getBoundingClientRect() : null;
            const subR = sub ? sub.getBoundingClientRect() : null;
            const boxR = chartBox ? chartBox.getBoundingClientRect() : null;
            return {
                id,
                titleToSub: (h2R && subR) ? Math.round(subR.top - h2R.bottom) : null,
                subToChart: (subR && boxR) ? Math.round(boxR.top - subR.bottom) : null,
            };
        });
    }

    return {
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        headings,
        buttons,
        cards,
        containers,
        planCheck,
        examCheck,
        progCheck,
    };
}
"""

CONTRAST_TAB_JS = """
(viewId) => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d');
    const toRgb = color => {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 1, 1);
        const d = ctx.getImageData(0, 0, 1, 1).data;
        return [d[0], d[1], d[2], d[3] / 255];
    };
    const lum = ([r, g, b]) => {
        const f = v => {
            const s = v / 255;
            return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
        };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const ratio = (c1, c2) => {
        const l1 = lum(c1), l2 = lum(c2);
        return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    };
    const effBg = el => {
        let cur = el;
        while (cur && cur !== document.documentElement) {
            const bg = getComputedStyle(cur).backgroundColor;
            const rgba = toRgb(bg);
            if (rgba[3] > 0.05) return rgba;
            cur = cur.parentElement;
        }
        return toRgb(getComputedStyle(document.body).backgroundColor);
    };

    const root = document.getElementById('v-' + viewId);
    const selectors = [
        '.page-title',
        '.card h2',
        '.card h3',
        '.ts-title',
        '.ts-duration',
        '.exam-card-title',
        '.stat-card-val',
        '.metric-row',
        '.wp-title',
    ];
    const results = {};
    for (const sel of selectors) {
        const el = root.querySelector(sel);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) continue;
        const fg = toRgb(getComputedStyle(el).color);
        const bg = effBg(el);
        results[sel] = Math.round(ratio(fg, bg) * 100) / 100;
    }
    return results;
}
"""


def main():
    url = isolated_server() + "/"
    report = {"widths": {}, "contrast": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url + "app", wait_until="networkidle")
        login_owner(page, url)
        page.evaluate("setLang('en')")
        page.wait_for_timeout(200)
        page.evaluate(SEED_JS)
        page.wait_for_timeout(250)

        for vw in WIDTHS:
            vh = 900 if vw >= 768 else 720
            page.set_viewport_size({"width": vw, "height": vh})
            page.wait_for_timeout(150)
            report["widths"][str(vw)] = {}

            heading_by_level = {"h1": {}, "h2": {}, "h3": {}}

            for view_id, alias in TABS:
                page.evaluate(f"showView('{view_id}')")
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(200)

                m = page.evaluate(MEASURE_TAB_JS, view_id)
                report["widths"][str(vw)][view_id] = m

                # 1. Zero horizontal scroll
                assert m["scrollWidth"] <= m["clientWidth"], (
                    f"{vw}px {view_id}: horizontal scroll {m['scrollWidth']} > {m['clientWidth']}"
                )

                # 2. Collect heading sizes/weights per level
                for level in ("h1", "h2", "h3"):
                    items = m["headings"][level]
                    if not items:
                        continue
                    sizes = {(it["fontSize"], it["fontWeight"]) for it in items}
                    assert len(sizes) == 1, (
                        f"{vw}px {view_id}: inconsistent {level} styles within tab: {items}"
                    )
                    heading_by_level[level][view_id] = next(iter(sizes))

                # 3. Visible buttons have height in {44, 48, 52} and <= 3 distinct heights
                btn_heights = set()
                for b in m["buttons"]:
                    assert b["h"] in (44, 48, 52), (
                        f"{vw}px {view_id}: button {b['text']!r} ({b['cls']}) has height {b['h']} not in {{44, 48, 52}}"
                    )
                    btn_heights.add(b["h"])
                assert len(btn_heights) <= 3, (
                    f"{vw}px {view_id}: more than 3 button heights: {btn_heights}"
                )

                # 4. Card paddings and gaps are multiples of 4
                assert m["cards"], f"{vw}px {view_id}: no visible cards found"
                for c in m["cards"]:
                    for side in ("padTop", "padRight", "padBottom", "padLeft", "marginBottom", "rowGap", "colGap"):
                        val = c[side]
                        assert val % 4 == 0, (
                            f"{vw}px {view_id}: card ({c['id'] or c['cls']}) {side}={val} not a multiple of 4"
                        )
                for cont in m["containers"]:
                    assert cont["rowGap"] % 4 == 0 and cont["colGap"] % 4 == 0, (
                        f"{vw}px {view_id}: container {cont['cls']} gaps ({cont['rowGap']}, {cont['colGap']}) not multiples of 4"
                    )

                # 5. Tab-specific design checks
                if view_id == "exam":
                    assert len(m["examCheck"]) == 4, f"{vw}px exam: expected 4 paper cards"
                    for ec in m["examCheck"]:
                        assert ec["tabularNums"], f"{vw}px exam: {ec['paper']} missing tabular-nums"
                        assert ec["alignedRight"], f"{vw}px exam: {ec['paper']} duration/parts not right-aligned"
                        assert "parts" in ec["minText"] and "min" in ec["minText"], (
                            f"{vw}px exam: {ec['paper']} badge missing parts or min: {ec['minText']!r}"
                        )

                if view_id == "prog":
                    title_gaps = {ch["titleToSub"] for ch in m["progCheck"]}
                    sub_gaps = {ch["subToChart"] for ch in m["progCheck"]}
                    assert len(title_gaps) == 1, f"{vw}px prog: inconsistent title->sub gaps across charts: {m['progCheck']}"
                    assert len(sub_gaps) == 1, f"{vw}px prog: inconsistent sub->chart gaps across charts: {m['progCheck']}"

                if view_id == "plan":
                    rh = m["planCheck"]["rowHeights"]
                    sh = m["planCheck"]["selectHeights"]
                    assert len(rh) >= 2, f"{vw}px plan: expected >= 2 day rows, got {rh}"
                    assert max(rh) - min(rh) <= 1, f"{vw}px plan: day rows do not have uniform height: {rh}"
                    for h in sh:
                        assert h == 48, f"{vw}px plan: select height {h} != 48 (secondary button height)"

                # 6. Screenshots
                shot_primary = OUT_DIR / f"design_{view_id}_{vw}.png"
                page.screenshot(path=str(shot_primary), full_page=False)
                assert shot_primary.exists() and shot_primary.stat().st_size > 1000
                if alias != view_id:
                    shot_alias = OUT_DIR / f"design_{alias}_{vw}.png"
                    shot_alias.write_bytes(shot_primary.read_bytes())

            # Verify cross-tab heading consistency at this width
            for level, by_tab in heading_by_level.items():
                distinct = set(by_tab.values())
                assert len(distinct) == 1, (
                    f"{vw}px: {level} (font-size, font-weight) differs across tabs: {by_tab}"
                )

        # Contrast >= 4.5:1 in light and dark themes across all 4 tabs
        page.set_viewport_size({"width": 1280, "height": 900})
        for theme in ("light", "dark"):
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            page.wait_for_timeout(100)
            report["contrast"][theme] = {}
            for view_id, _ in TABS:
                page.evaluate(f"showView('{view_id}')")
                page.wait_for_timeout(100)
                ratios = page.evaluate(CONTRAST_TAB_JS, view_id)
                report["contrast"][theme][view_id] = ratios
                for sel, r in ratios.items():
                    assert r >= 4.5, f"{theme} {view_id} {sel}: contrast {r} < 4.5"

        assert not errors, f"page errors: {errors}"
        browser.close()

    print(json.dumps(report, indent=2))
    print("DESIGN_CONSISTENCY_OK")


if __name__ == "__main__":
    main()
