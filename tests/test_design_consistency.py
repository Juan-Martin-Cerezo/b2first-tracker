"""Phase 120 + 122: Design system consistency across all eight tabs.

Verifies at 320, 768, and 1280 px across all eight tabs
(Today, Exam, Progress, Plan, Practice, Resources, Errors, Writing):
1. All eight tabs use the same computed font-size and font-weight for headings of the same level (h1, h2, h3).
2. All visible <button> elements have height in {44, 48, 52} px, and at most 3 distinct button heights per tab.
3. Computed paddings and gaps of cards and card containers are multiples of 4 px.
4. Zero horizontal scroll on documentElement in any tab or width; internal horizontal scroll is only
   admitted inside an explicit .table-wrap container (Errors legend table at 320 px).
5. Tab-specific layout & typography invariants for Today, Exam, Progress, Plan, Practice, Resources, Errors, and Writing.
6. Text contrast >= 4.5:1 in both light and dark themes (including danger error message in Writing).
7. Screenshots saved to tests/out/design_<tab>_<width>.png for all eight tabs.
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
    ("practice", "practice"),
    ("resources", "resources"),
    ("err", "errors"),
    ("ia", "writing"),
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
        {id: 'e1', date: '2026-04-02', code: 'L-GAP', desc: 'Missed collocation in Part 1', fix: 'Review unit 2'},
        {id: 'e2', date: '2026-04-03', code: 'G-ERR', desc: 'Wrong tense after wish', fix: 'Check past perfect'}
    ];
    MATERIALS = [
        {
            folder: '01-Examenes-Oficiales',
            name: 'b2-first-RUE 2022.pdf',
            rel: '01-Examenes-Oficiales/b2-first-RUE 2022.pdf',
            href: '/mat/01-Examenes-Oficiales/b2-first-RUE%202022.pdf',
            ext: 'PDF',
            size: 1458176
        },
        {
            folder: '01-Examenes-Oficiales',
            name: 'b2-first-Listening 2022.pdf',
            rel: '01-Examenes-Oficiales/b2-first-Listening 2022.pdf',
            href: '/mat/01-Examenes-Oficiales/b2-first-Listening%202022.pdf',
            ext: 'PDF',
            size: 982016
        },
        {
            folder: '01-Examenes-Oficiales',
            name: 'listening-audio-file v2.mp3',
            rel: '01-Examenes-Oficiales/listening-audio-file v2.mp3',
            href: '/mat/01-Examenes-Oficiales/listening-audio-file%20v2.mp3',
            ext: 'AUDIO',
            size: 18452000
        }
    ];
    buildMatIndex();
    const sorted = getSessionDays();
    const todayKey = PLAN_DAY_ORDER[(wd + 6) % 7];
    const todayIdx = sorted.findIndex(d => d.key === todayKey);
    D.sessionOffset = todayIdx > 0 ? -todayIdx : 0;
    save();
    refreshAll();
    renderResources();
    renderMaterial();
    setIaState('error', 'Text is too short (minimum 40 words required for B2 grading).');
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
    const cardEls = Array.from(
        root.querySelectorAll('.card, .stat-card, .exam-card, .practice-card, .listen-test, .step, .err-item')
    ).filter(isVisible);
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
        root.querySelectorAll(
            '.grid-12, .stat-grid, .exam-select-grid, .today-shell, .today-grid, .plan-shell, #wpRows, .practice-grid, .lt-grid, #errList'
        )
    ).filter(isVisible);
    const containers = containerEls.map(c => {
        const cs = getComputedStyle(c);
        return {
            cls: c.className || c.id,
            rowGap: Math.round(parseFloat(cs.rowGap) || 0),
            colGap: Math.round(parseFloat(cs.columnGap) || 0),
        };
    });

    // Internal horizontal overflow check: only allowed on .table-wrap
    const internalScrollers = Array.from(root.querySelectorAll('*')).filter(el => {
        if (!isVisible(el)) return false;
        const cs = getComputedStyle(el);
        if (cs.overflowX !== 'auto' && cs.overflowX !== 'scroll') return false;
        return el.scrollWidth > el.clientWidth + 1;
    }).map(el => ({
        tag: el.tagName.toLowerCase(),
        cls: el.className || '',
        id: el.id || '',
        clientWidth: el.clientWidth,
        scrollWidth: el.scrollWidth,
    }));

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

    // 7. Practice specific: consistent .step row heights, uniform padding/gap, single button variant & height
    let practiceCheck = null;
    if (viewId === 'practice') {
        const steps = Array.from(root.querySelectorAll('#partsList .step')).filter(isVisible);
        const stepBtns = Array.from(root.querySelectorAll('#partsList .step button')).filter(isVisible);
        practiceCheck = {
            stepCount: steps.length,
            stepHeights: steps.map(s => Math.round(s.getBoundingClientRect().height)),
            stepPaddings: steps.map(s => {
                const cs = getComputedStyle(s);
                return [
                    Math.round(parseFloat(cs.paddingTop)),
                    Math.round(parseFloat(cs.paddingRight)),
                    Math.round(parseFloat(cs.paddingBottom)),
                    Math.round(parseFloat(cs.paddingLeft)),
                ];
            }),
            buttonVariants: Array.from(new Set(stepBtns.map(b => b.className.trim()))),
            buttonHeights: Array.from(new Set(stepBtns.map(b => Math.round(b.getBoundingClientRect().height)))),
        };
    }

    // 8. Resources specific: sample cards uniform padding/gap, link rhythm, right-aligned tabular-nums, name highest weight
    let resourcesCheck = null;
    if (viewId === 'resources') {
        const sampleCards = Array.from(root.querySelectorAll('#resourcesList .listen-test')).filter(isVisible);
        const practiceCards = Array.from(root.querySelectorAll('#practiceGrid .practice-card')).filter(isVisible);
        const books = Array.from(root.querySelectorAll('#onlineList .book, #matList .book')).filter(isVisible);
        resourcesCheck = {
            sampleCount: sampleCards.length,
            samplePaddings: sampleCards.map(c => {
                const cs = getComputedStyle(c);
                return [
                    Math.round(parseFloat(cs.paddingTop)),
                    Math.round(parseFloat(cs.paddingRight)),
                    Math.round(parseFloat(cs.paddingBottom)),
                    Math.round(parseFloat(cs.paddingLeft)),
                ];
            }),
            practiceCardsHierarchy: practiceCards.map(c => {
                const h3 = c.querySelector('h3');
                const what = c.querySelector('.practice-what');
                const mins = c.querySelector('.practice-mins');
                const h3CS = h3 ? getComputedStyle(h3) : null;
                const whatCS = what ? getComputedStyle(what) : null;
                const minsCS = mins ? getComputedStyle(mins) : null;
                return {
                    nameWeight: h3CS ? parseInt(h3CS.fontWeight, 10) : 0,
                    whatWeight: whatCS ? parseInt(whatCS.fontWeight, 10) : 0,
                    whatSize: whatCS ? Math.round(parseFloat(whatCS.fontSize)) : 0,
                    minsSize: minsCS ? Math.round(parseFloat(minsCS.fontSize)) : 0,
                    minsTabular: minsCS ? minsCS.fontVariantNumeric.includes('tabular-nums') : false,
                    minsAlignRight: minsCS ? minsCS.textAlign === 'right' : false,
                };
            }),
            booksHierarchy: books.map(b => {
                const nameEl = b.querySelector('b');
                const metaEl = b.querySelector('.meta');
                const numEl = b.querySelector('.price, .book-size');
                const bCS = getComputedStyle(b);
                const nCS = nameEl ? getComputedStyle(nameEl) : null;
                const mCS = metaEl ? getComputedStyle(metaEl) : null;
                const numCS = numEl ? getComputedStyle(numEl) : null;
                return {
                    padTop: Math.round(parseFloat(bCS.paddingTop)),
                    padBottom: Math.round(parseFloat(bCS.paddingBottom)),
                    nameWeight: nCS ? parseInt(nCS.fontWeight, 10) : 0,
                    metaWeight: mCS ? parseInt(mCS.fontWeight, 10) : 0,
                    metaSize: mCS ? Math.round(parseFloat(mCS.fontSize)) : 0,
                    numTabular: numCS ? numCS.fontVariantNumeric.includes('tabular-nums') : false,
                    numAlignRight: numCS ? numCS.textAlign === 'right' : false,
                };
            }),
        };
    }

    // 9. Errors specific: legend table at 320px, sticky th, uniform row heights, empty state pattern
    let errCheck = null;
    if (viewId === 'err') {
        const wrap = root.querySelector('#errLegend .table-wrap');
        const tbl = root.querySelector('#errLegend .err-legend-table');
        const ths = Array.from(root.querySelectorAll('#errLegend th')).filter(isVisible);
        const trs = Array.from(root.querySelectorAll('#errLegend tbody tr')).filter(isVisible);
        const items = Array.from(root.querySelectorAll('#errList .err-item')).filter(isVisible);
        errCheck = {
            wrapClientWidth: wrap ? wrap.clientWidth : 0,
            wrapScrollWidth: wrap ? wrap.scrollWidth : 0,
            tableWidth: tbl ? Math.round(tbl.getBoundingClientRect().width) : 0,
            colWidths: ths.map(th => Math.round(th.getBoundingClientRect().width)),
            thSticky: ths.every(th => {
                const cs = getComputedStyle(th);
                return cs.position === 'sticky' && cs.top === '0px';
            }),
            trHeights: trs.map(tr => Math.round(tr.getBoundingClientRect().height)),
            errItemHeights: items.map(it => Math.round(it.getBoundingClientRect().height)),
        };
    }

    // 10. Writing specific: labels above fields, #iaKind height == 48, help text in meta size, danger error visible
    let iaCheck = null;
    if (viewId === 'ia') {
        const lblKind = root.querySelector('label[for="iaKind"]');
        const selKind = root.querySelector('#iaKind');
        const lblText = root.querySelector('label[for="iaText"]');
        const areaText = root.querySelector('#iaText');
        const meter = root.querySelector('.live-word-meter');
        const errBox = root.querySelector('#iaError');
        const errMsg = root.querySelector('#iaErrorMsg');
        const lkR = lblKind ? lblKind.getBoundingClientRect() : null;
        const skR = selKind ? selKind.getBoundingClientRect() : null;
        const ltR = lblText ? lblText.getBoundingClientRect() : null;
        const atR = areaText ? areaText.getBoundingClientRect() : null;
        const mCS = meter ? getComputedStyle(meter) : null;
        iaCheck = {
            kindLabelAbove: (lkR && skR) ? (lkR.bottom <= skR.top + 1) : false,
            textLabelAbove: (ltR && atR) ? (ltR.bottom <= atR.top + 1) : false,
            kindHeight: skR ? Math.round(skR.height) : 0,
            meterFontSize: mCS ? Math.round(parseFloat(mCS.fontSize)) : 0,
            errorVisible: errBox ? isVisible(errBox) : false,
            errorMsgText: errMsg ? errMsg.innerText.trim() : '',
        };
    }

    return {
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        internalScrollers,
        headings,
        buttons,
        cards,
        containers,
        planCheck,
        examCheck,
        progCheck,
        practiceCheck,
        resourcesCheck,
        errCheck,
        iaCheck,
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
        '.step h3',
        '.practice-card h3',
        '.practice-what',
        '.book b',
        '.book .meta',
        '.listen-test .lt-head',
        '#errLegend td',
        '.err-item .err-desc',
        '#iaErrorMsg',
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

                # 1. Zero horizontal scroll on documentElement
                assert m["scrollWidth"] <= m["clientWidth"], (
                    f"{vw}px {view_id}: page horizontal scroll {m['scrollWidth']} > {m['clientWidth']}"
                )
                # Internal horizontal scroll is only allowed inside .table-wrap
                for sc in m["internalScrollers"]:
                    assert "table-wrap" in sc["cls"], (
                        f"{vw}px {view_id}: unexpected internal horizontal scroll container: {sc}"
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

                if view_id == "practice":
                    pc = m["practiceCheck"]
                    assert pc["stepCount"] == 17, f"{vw}px practice: expected 17 part rows, got {pc['stepCount']}"
                    assert max(pc["stepHeights"]) - min(pc["stepHeights"]) <= 1, (
                        f"{vw}px practice: part rows do not have consistent height: {pc['stepHeights']}"
                    )
                    for pad in pc["stepPaddings"]:
                        assert pad == [16, 16, 16, 16], f"{vw}px practice: step padding {pad} != [16, 16, 16, 16]"
                    # Fase 126: a part row has one primary action (Start) and one
                    # secondary (Resources). The rule is "no invented styles", not
                    # "one variant only": any variant outside this pair is a defect.
                    allowed = {"btn sm", "btn sm gray"}
                    assert set(pc["buttonVariants"]) <= allowed, (
                        f"{vw}px practice: unexpected button variants: {pc['buttonVariants']}"
                    )

                    assert pc["buttonHeights"] == [44], (
                        f"{vw}px practice: practice button heights {pc['buttonHeights']} != [44]"
                    )

                if view_id == "resources":
                    rc = m["resourcesCheck"]
                    assert rc["sampleCount"] > 0, f"{vw}px resources: no sample cards rendered"
                    for pad in rc["samplePaddings"]:
                        assert pad == [16, 16, 16, 16], f"{vw}px resources: sample card padding {pad} != [16, 16, 16, 16]"
                    for pch in rc["practiceCardsHierarchy"]:
                        assert pch["nameWeight"] > pch["whatWeight"], (
                            f"{vw}px resources: practice-card name not highest weight: {pch}"
                        )
                        assert pch["whatSize"] == 12 and pch["minsSize"] == 12, (
                            f"{vw}px resources: practice-card secondary text not meta size (12px): {pch}"
                        )
                        assert pch["minsTabular"] and pch["minsAlignRight"], (
                            f"{vw}px resources: practice-mins not right-aligned tabular-nums: {pch}"
                        )
                    for bh in rc["booksHierarchy"]:
                        assert bh["padTop"] == 12 and bh["padBottom"] == 12, (
                            f"{vw}px resources: book vertical rhythm not uniform 12px: {bh}"
                        )
                        assert bh["nameWeight"] > bh["metaWeight"], (
                            f"{vw}px resources: book name not highest weight: {bh}"
                        )
                        assert bh["metaSize"] == 12, f"{vw}px resources: book meta size != 12: {bh}"
                        assert bh["numTabular"] and bh["numAlignRight"], (
                            f"{vw}px resources: book price/size not right-aligned tabular-nums: {bh}"
                        )

                if view_id == "err":
                    ec = m["errCheck"]
                    assert ec["thSticky"], f"{vw}px err: table headers are not sticky: {ec}"
                    assert ec["tableWidth"] >= 500, f"{vw}px err: legend table crushed ({ec['tableWidth']}px)"
                    assert all(w >= 60 for w in ec["colWidths"]), (
                        f"{vw}px err: legend table column clipped: {ec['colWidths']}"
                    )
                    assert max(ec["trHeights"]) - min(ec["trHeights"]) <= 1, (
                        f"{vw}px err: legend table rows do not have consistent height: {ec['trHeights']}"
                    )
                    assert max(ec["errItemHeights"]) - min(ec["errItemHeights"]) <= 1, (
                        f"{vw}px err: logged error rows do not have consistent height: {ec['errItemHeights']}"
                    )
                    if vw == 320:
                        assert ec["wrapScrollWidth"] > ec["wrapClientWidth"], (
                            f"320px err: expected internal scroll on .table-wrap: {ec}"
                        )

                if view_id == "ia":
                    ic = m["iaCheck"]
                    assert ic["kindLabelAbove"] and ic["textLabelAbove"], (
                        f"{vw}px ia: labels are not above fields: {ic}"
                    )
                    assert ic["kindHeight"] == 48, (
                        f"{vw}px ia: #iaKind height {ic['kindHeight']} != 48 (secondary button height)"
                    )
                    assert ic["meterFontSize"] == 12, (
                        f"{vw}px ia: help text below field not meta size (12px): {ic}"
                    )
                    assert ic["errorVisible"] and ic["errorMsgText"], (
                        f"{vw}px ia: error message not visible for validation check: {ic}"
                    )

                # 6. Screenshots
                shot_primary = OUT_DIR / f"design_{view_id}_{vw}.png"
                page.screenshot(path=str(shot_primary), full_page=False)
                assert shot_primary.exists() and shot_primary.stat().st_size > 1000
                if alias != view_id:
                    shot_alias = OUT_DIR / f"design_{alias}_{vw}.png"
                    shot_alias.write_bytes(shot_primary.read_bytes())

            # Verify cross-tab heading consistency at this width across all 8 tabs
            for level, by_tab in heading_by_level.items():
                distinct = set(by_tab.values())
                assert len(distinct) == 1, (
                    f"{vw}px: {level} (font-size, font-weight) differs across tabs: {by_tab}"
                )

        # Contrast >= 4.5:1 in light and dark themes across all 8 tabs
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

        # Verify empty state pattern in Errors and focus ring across Practice, Resources, Errors, Writing
        page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        page.evaluate("() => { D.errs = []; renderErrs(); renderErrPills(); showView('err'); }")
        page.wait_for_timeout(100)
        empty_check = page.evaluate(
            """() => {
                const empties = Array.from(document.querySelectorAll('#v-err .empty'));
                return empties.map(e => {
                    const cs = getComputedStyle(e);
                    return {
                        padTop: Math.round(parseFloat(cs.paddingTop)),
                        padBottom: Math.round(parseFloat(cs.paddingBottom)),
                        rowGap: Math.round(parseFloat(cs.rowGap)),
                        hasBtn: !!e.querySelector('button.btn'),
                    };
                });
            }"""
        )
        assert len(empty_check) == 2 and all(
            ec["padTop"] == 16 and ec["padBottom"] == 16 and ec["rowGap"] == 8 and ec["hasBtn"]
            for ec in empty_check
        ), f"Errors empty state does not use unified .empty pattern: {empty_check}"

        focus_targets = [
            ("practice", "#v-practice #partsList .step button"),
            ("resources", "#v-resources #practiceGrid a.btn"),
            ("err", "#v-err #errCode2"),
            ("ia", "#v-ia #iaKind"),
        ]
        for view_id, sel in focus_targets:
            page.evaluate(f"showView('{view_id}')")
            page.wait_for_timeout(80)
            fc = page.evaluate(
                """(selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return null;
                    el.focus();
                    const cs = getComputedStyle(el);
                    return {
                        outlineStyle: cs.outlineStyle,
                        outlineWidth: Math.round(parseFloat(cs.outlineWidth)),
                        outlineOffset: Math.round(parseFloat(cs.outlineOffset)),
                    };
                }""",
                sel,
            )
            assert fc and fc["outlineStyle"] == "solid" and fc["outlineWidth"] == 2 and fc["outlineOffset"] == 2, (
                f"Focus ring mismatch on {view_id} ({sel}): {fc}"
            )

        assert not errors, f"page errors: {errors}"
        browser.close()

    print(json.dumps(report, indent=2))
    print("DESIGN_CONSISTENCY_OK")


if __name__ == "__main__":
    main()
