"""Phase 117, 118 & 121: Today desktop layout redesigned with design-fundamentals principles.

Verifies:
- At 1280 and 1440 (and >= 1024): centered container 960-1040 px (>= 880 px)
  with vertical padding clamp(32px, 6vh, 72px); two visible columns (left session
  weight 1.6, right plain-text aside weight 1); session card >= 480 px wide,
  >= 280 px tall, 32 px padding, hero duration clamp(30px, 3.4vw, 46px);
  right column >= 240 px wide.
- Phase 118 & 121 vertical composition (>= 1024 px):
  - Today content block fills available height (min-height calc(100dvh - nav - footer))
    with grid-auto-rows: min-content and align-content: center when content fits,
    and natural top-aligned scroll when content exceeds the available height.
  - At 1024, 1280, and 1440: the first visible child of .today-shell has
    childTop - areaTop >= 15% of area height, areaBottom - childBottom >= 15%
    of area height, and their difference <= 15% of area height.
  - Right column (#todayAside) starts within <= 8 px of #todaySession top edge,
    measures >= 45% of #todaySession height, and distributes any extra height
    between its two blocks (no leftover gap at the bottom).
- Plain-text 'Next session' (e.g. 'Mon · Writing report · 15:30', or fallback
  'No session days configured') and 'This cycle' (e.g. 'Reading 4 of 7 parts done'
  read from D.log), with no pill border-radius, no chip background, no shadows,
  and no decorative icons.
- At most 3 font-size levels inside #v-hoy; spacing in 4/8 multiples with outer
  block gap > inner element gap; contrast >= 4.5:1 in light and dark themes;
  visible focus on Start, Fast-forward, and links; buttons >= 44x44 with full text
  and natural tab order.
- Below 1024 px (320, 380, 768): single centered 560 px column with right column
  stacked below the session and still visible; at 380 px the block starts in the
  first 20% of the page (not vertically centered).
- Zero horizontal scroll across 320, 380, 768, 1024, 1280, 1440 and no bottom-bar
  overlap.
- Screenshots saved to tests/out/today_1280.png, tests/out/today_1440.png, and
  tests/out/today_1440_scroll.png (1440x700).
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from helpers import isolated_server, login_owner

OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEED_DESKTOP = """
() => {
    const wd = new Date().getDay();
    const nextWd = (wd + 4) % 7;
    D.profile = {
        examDate: null, targetGrade: 'B',
        skills: {rue: 3, w: 3, l: 3, sp: 3},
        hoursWeek: 4, days: [wd, nextWd],
        struggles: [], strugglesDeclared: [],
    };
    D.diag = null;
    D.errs = [];
    D.sessionOffset = 0;
    D.weekOverrides = {};
    D.settings.rotationMode = 'by-part';
    D.settings.itemsPerSession = 1;
    D.settings.schedule = [{day: wd, time: '15:30'}, {day: nextWd, time: '13:00'}];
    D.settings.sessions = D.settings.schedule.slice();
    D.log = [
        {id: 'r1', date: '2026-04-01', created_at: 1000, type: 'ue', part: 1, ok: 6, total: 8, min: 8},
        {id: 'r2', date: '2026-04-02', created_at: 2000, type: 'ue', part: 2, ok: 6, total: 8, min: 8},
        {id: 'r3', date: '2026-04-03', created_at: 3000, type: 'ue', part: 3, ok: 6, total: 8, min: 8},
        {id: 'r4', date: '2026-04-04', created_at: 4000, type: 'ue', part: 4, ok: 4, total: 6, min: 10}
    ];
    const sorted = getSessionDays();
    const todayKey = PLAN_DAY_ORDER[(wd + 6) % 7];
    const todayIdx = sorted.findIndex(d => d.key === todayKey);
    D.sessionOffset = todayIdx > 0 ? -todayIdx : 0;
    save();
    refreshAll();
}
"""

MEASURE_DESKTOP = """
() => {
    const doc = document.documentElement;
    const hoy = document.getElementById('v-hoy');
    const shell = hoy.querySelector('.today-shell');
    const grid = document.getElementById('todayGrid');
    const session = document.getElementById('todaySession');
    const aside = document.getElementById('todayAside');
    const nextBlock = document.getElementById('todayNextBlock');
    const cycleBlock = document.getElementById('todayCycleBlock');
    const nextLbl = document.getElementById('todayNextLabel');
    const nextVal = document.getElementById('todayNextValue');
    const cycleLbl = document.getElementById('todayCycleLabel');
    const cycleVal = document.getElementById('todayCycleValue');
    const dur = session.querySelector('.ts-duration');
    const title = session.querySelector('.ts-title');
    const when = session.querySelector('.ts-when');
    const mode = session.querySelector('.ts-mode');
    const nav = document.getElementById('sideNav');

    const main = document.querySelector('.content main');
    const head = hoy.querySelector('.today-head');

    const mainR = main.getBoundingClientRect();
    const headR = head.getBoundingClientRect();
    const sr = shell.getBoundingClientRect();
    const firstChild = Array.from(shell.children).find(el => {
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const b = el.getBoundingClientRect();
        return b.width > 0 && b.height > 0;
    });
    const firstChildR = firstChild ? firstChild.getBoundingClientRect() : sr;
    const cardR = session.getBoundingClientRect();
    const asideR = aside.getBoundingClientRect();
    const nextR = nextBlock.getBoundingClientRect();
    const cycleR = cycleBlock.getBoundingClientRect();
    const navR = nav.getBoundingClientRect();

    const shellCS = getComputedStyle(shell);
    const cardCS = getComputedStyle(session);
    const asideCS = getComputedStyle(aside);
    const nextBlockCS = getComputedStyle(nextBlock);
    const durCS = dur ? getComputedStyle(dur) : null;

    const styleCheck = el => {
        const cs = getComputedStyle(el);
        return {
            bg: cs.backgroundColor,
            radius: parseFloat(cs.borderTopLeftRadius) || 0,
            shadow: cs.boxShadow,
        };
    };

    // Visible text font sizes inside #v-hoy
    const fontSizes = new Set();
    for (const el of hoy.querySelectorAll('*')) {
        const hasText = Array.from(el.childNodes).some(
            n => n.nodeType === 3 && n.textContent.trim()
        );
        if (!hasText) continue;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const b = el.getBoundingClientRect();
        if (b.width < 1 || b.height < 1) continue;
        fontSizes.add(Math.round(parseFloat(cs.fontSize) * 10) / 10);
    }

    const buttons = Array.from(session.querySelectorAll('.ts-row:not(.ts-next-unit) button'));
    const btnStats = buttons.map(b => {
        const r = b.getBoundingClientRect();
        b.focus();
        const fcs = getComputedStyle(b);
        return {
            text: b.textContent.trim(),
            w: Math.round(r.width),
            h: Math.round(r.height),
            left: r.left,
            top: r.top,
            clipped: b.scrollWidth > b.clientWidth + 1,
            outlineStyle: fcs.outlineStyle,
            outlineWidth: parseFloat(fcs.outlineWidth) || 0,
            tabIndex: b.tabIndex,
        };
    });
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();

    // Check nav overlapped with content when nav is fixed at bottom
    const navCS = getComputedStyle(nav);
    const navAtBottom = navCS.position === 'fixed' && navR.top > window.innerHeight / 2;
    const bottomOverlap = navAtBottom && (cardR.bottom > navR.top + 1 || asideR.bottom > navR.top + 1);

    return {
        vw: window.innerWidth,
        vh: window.innerHeight,
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        area: {
            top: mainR.top,
            bottom: mainR.bottom,
            h: mainR.height,
            centerY: (mainR.top + mainR.bottom) / 2,
        },
        head: {
            top: headR.top,
            bottom: headR.bottom,
            h: headR.height,
        },
        firstChild: {
            top: firstChildR.top,
            bottom: firstChildR.bottom,
            h: firstChildR.height,
            centerY: (firstChildR.top + firstChildR.bottom) / 2,
        },
        shell: {
            w: Math.round(sr.width),
            h: Math.round(sr.height),
            top: sr.top,
            bottom: sr.bottom,
            left: sr.left,
            right: sr.right,
            center: (sr.left + sr.right) / 2,
            centerY: (sr.top + sr.bottom) / 2,
            padTop: parseFloat(shellCS.paddingTop) || 0,
            padBottom: parseFloat(shellCS.paddingBottom) || 0,
            maxWidth: shellCS.maxWidth,
            alignContent: shellCS.alignContent,
        },
        session: {
            w: Math.round(cardR.width),
            h: Math.round(cardR.height),
            left: cardR.left,
            right: cardR.right,
            top: cardR.top,
            bottom: cardR.bottom,
            centerY: (cardR.top + cardR.bottom) / 2,
            padTop: parseFloat(cardCS.paddingTop) || 0,
            padRight: parseFloat(cardCS.paddingRight) || 0,
            padBottom: parseFloat(cardCS.paddingBottom) || 0,
            padLeft: parseFloat(cardCS.paddingLeft) || 0,
        },
        aside: {
            w: Math.round(asideR.width),
            h: Math.round(asideR.height),
            left: asideR.left,
            right: asideR.right,
            top: asideR.top,
            bottom: asideR.bottom,
            nextTop: nextR.top,
            nextBottom: nextR.bottom,
            cycleTop: cycleR.top,
            cycleBottom: cycleR.bottom,
            contentSpan: cycleR.bottom - nextR.top,
            visible: asideR.width > 0 && asideR.height > 0 && asideCS.display !== 'none',
            gap: parseFloat(asideCS.rowGap || asideCS.gap) || 0,
            blockGap: parseFloat(nextBlockCS.rowGap || nextBlockCS.gap) || 0,
            icons: aside.querySelectorAll('svg, img, .badge, .chip, .ico').length,
            styles: {
                aside: styleCheck(aside),
                nextBlock: styleCheck(nextBlock),
                cycleBlock: styleCheck(cycleBlock),
                nextLbl: styleCheck(nextLbl),
                nextVal: styleCheck(nextVal),
                cycleLbl: styleCheck(cycleLbl),
                cycleVal: styleCheck(cycleVal),
            },
        },
        copy: {
            title: title ? title.innerText.trim() : '',
            titleTextContent: title ? title.textContent.trim() : '',
            duration: dur ? dur.innerText.trim() : '',
            durationFontSize: durCS ? parseFloat(durCS.fontSize) : 0,
            when: when ? when.innerText.trim() : '',
            mode: mode ? mode.innerText.trim() : '',
            nextLabel: nextLbl ? nextLbl.innerText.trim() : '',
            nextValue: nextVal ? nextVal.innerText.trim() : '',
            cycleLabel: cycleLbl ? cycleLbl.innerText.trim() : '',
            cycleValue: cycleVal ? cycleVal.innerText.trim() : '',
        },
        fontSizes: Array.from(fontSizes).sort((a, b) => a - b),
        buttons: btnStats,
        bottomOverlap: bottomOverlap,
    };
}
"""

CONTRAST_JS = """
() => {
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
    const selectors = [
        '#v-hoy .page-title',
        '#todaySession h2',
        '#todaySession .ts-title',
        '#todaySession .ts-duration',
        '#todaySession .ts-when',
        '#todaySession .ts-mode',
        '#todaySession .btn.ok',
        '#todaySession .btn.gray',
        '#todayNextLabel',
        '#todayNextValue',
        '#todayCycleLabel',
        '#todayCycleValue',
    ];
    const out = {};
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const fg = toRgb(getComputedStyle(el).color);
        const bg = effBg(el);
        out[sel] = Math.round(ratio(fg, bg) * 100) / 100;
    }
    return out;
}
"""

URL = isolated_server() + "/"
report = {"desktop": {}, "responsive": {}, "contrast": {}}

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL + "app", wait_until="networkidle")
    login_owner(page, URL)
    page.evaluate("setLang('en')")
    page.wait_for_timeout(200)
    page.click("nav button[data-view='hoy']")
    page.wait_for_timeout(200)
    page.evaluate(SEED_DESKTOP)
    page.wait_for_timeout(250)

    # 1. Desktop viewports: 1280 and 1440 (plus 1024)
    for vw, vh in [(1024, 900), (1280, 900), (1440, 900)]:
        page.set_viewport_size({"width": vw, "height": vh})
        page.wait_for_timeout(200)
        m = page.evaluate(MEASURE_DESKTOP)
        report["desktop"][str(vw)] = m

        # Container >= 880 px (960-1040 px) and centered, vertical padding clamp(32px, 6vh, 72px)
        assert 880 <= m["shell"]["w"] <= 1040, f"{vw}: container width {m['shell']['w']} not in 880..1040"
        assert abs(m["shell"]["center"] - vw / 2) <= 2, f"{vw}: container not centered ({m['shell']['center']} vs {vw/2})"
        assert 32 <= m["shell"]["padTop"] <= 72, f"{vw}: vertical padTop {m['shell']['padTop']} outside 32..72"
        assert 32 <= m["shell"]["padBottom"] <= 72, f"{vw}: vertical padBottom {m['shell']['padBottom']} outside 32..72"

        # Two visible columns: session on left (>= 480w, >= 280h, padding 32), aside on right (>= 240w)
        assert m["session"]["w"] >= 480, f"{vw}: session width {m['session']['w']} < 480"
        assert m["session"]["h"] >= 280, f"{vw}: session height {m['session']['h']} < 280"
        for side in ("padTop", "padRight", "padBottom", "padLeft"):
            assert m["session"][side] == 32, f"{vw}: session {side}={m['session'][side]} != 32"
        assert m["aside"]["visible"], f"{vw}: right column not visible"
        assert m["aside"]["w"] >= 240, f"{vw}: right column width {m['aside']['w']} < 240"
        assert m["aside"]["left"] >= m["session"]["right"] + 16, (
            f"{vw}: columns not side-by-side (session.right={m['session']['right']}, aside.left={m['aside']['left']})"
        )
        weight_ratio = m["session"]["w"] / m["aside"]["w"]
        assert 1.45 <= weight_ratio <= 1.75, f"{vw}: column ratio {weight_ratio:.2f} not ~1.6"

        # Phase 118 & 121: Vertical centering in content area (main) measured on first visible child of shell
        area_h = m["area"]["h"]
        area_center = m["area"]["centerY"]
        child_top_space = m["firstChild"]["top"] - m["area"]["top"]
        child_bottom_space = m["area"]["bottom"] - m["firstChild"]["bottom"]
        assert child_top_space >= 0.15 * area_h, (
            f"{vw}: firstChild top space {child_top_space:.1f} < 15% of area height {area_h:.1f}"
        )
        assert child_bottom_space >= 0.15 * area_h, (
            f"{vw}: firstChild bottom space {child_bottom_space:.1f} < 15% of area height {area_h:.1f}"
        )
        assert abs(child_top_space - child_bottom_space) <= 0.15 * area_h, (
            f"{vw}: firstChild top/bottom air diff {abs(child_top_space - child_bottom_space):.1f} > 15% of {area_h:.1f}"
        )
        session_center_diff = abs(m["session"]["centerY"] - area_center)
        assert session_center_diff < 0.15 * area_h, (
            f"{vw}: session centerY {m['session']['centerY']:.1f} too far from content area center "
            f"{area_center:.1f} (diff={session_center_diff:.1f}, limit={0.15 * area_h:.1f})"
        )
        # Free space above and below: both >= 15% of content area height and difference <= 15%
        top_space_session = m["session"]["top"] - m["area"]["top"]
        bottom_space_session = m["area"]["bottom"] - m["session"]["bottom"]
        top_space_block = m["head"]["top"] - m["area"]["top"]
        bottom_space_block = m["area"]["bottom"] - m["session"]["bottom"]
        assert top_space_session >= 0.15 * area_h and bottom_space_session >= 0.15 * area_h, (
            f"{vw}: session free space top={top_space_session:.1f} bottom={bottom_space_session:.1f} (< 15% of {area_h:.1f})"
        )
        assert abs(top_space_session - bottom_space_session) <= 0.15 * area_h, (
            f"{vw}: session top/bottom air diff {abs(top_space_session - bottom_space_session):.1f} > 15% of {area_h:.1f}"
        )
        assert top_space_block >= 0.15 * area_h and bottom_space_block >= 0.15 * area_h, (
            f"{vw}: block free space top={top_space_block:.1f} bottom={bottom_space_block:.1f} (< 15% of {area_h:.1f})"
        )
        assert abs(top_space_block - bottom_space_block) <= 0.15 * area_h, (
            f"{vw}: block top/bottom air diff {abs(top_space_block - bottom_space_block):.1f} > 15% of {area_h:.1f}"
        )

        # Phase 118 A.3 & B.5: Right column top-aligned (<= 8px from session top) and >= 45% of session height
        assert abs(m["aside"]["top"] - m["session"]["top"]) <= 8, (
            f"{vw}: aside top {m['aside']['top']} not within 8px of session top {m['session']['top']}"
        )
        assert abs(m["aside"]["nextTop"] - m["session"]["top"]) <= 8, (
            f"{vw}: nextBlock top {m['aside']['nextTop']} not within 8px of session top {m['session']['top']}"
        )
        assert m["aside"]["h"] >= 0.45 * m["session"]["h"], (
            f"{vw}: aside height {m['aside']['h']} < 45% of session height {m['session']['h']}"
        )
        assert m["aside"]["contentSpan"] >= 0.45 * m["session"]["h"], (
            f"{vw}: aside content span {m['aside']['contentSpan']:.1f} < 45% of session height {m['session']['h']}"
        )
        assert abs(m["aside"]["bottom"] - m["aside"]["cycleBottom"]) <= 2, (
            f"{vw}: extra height left as hole below cycleBlock ({m['aside']['bottom']} vs {m['aside']['cycleBottom']})"
        )

        # Duration hero size clamp(30px, 3.4vw, 46px)
        expected_dur = min(46.0, max(30.0, vw * 0.034))
        assert abs(m["copy"]["durationFontSize"] - expected_dur) <= 1.5, (
            f"{vw}: duration font-size {m['copy']['durationFontSize']} != {expected_dur}"
        )
        assert m["copy"]["duration"].endswith("min"), f"{vw}: duration text {m['copy']['duration']!r}"

        # Hierarchy: at most 3 font-size levels
        assert 2 <= len(m["fontSizes"]) <= 3, f"{vw}: expected <= 3 font-size levels, got {m['fontSizes']}"

        # Spacing: outer block gap > inner block gap, multiples of 4/8
        assert m["aside"]["gap"] > m["aside"]["blockGap"], (
            f"{vw}: outer gap {m['aside']['gap']} not > inner gap {m['aside']['blockGap']}"
        )
        assert m["aside"]["gap"] % 8 == 0 and m["aside"]["blockGap"] % 4 == 0

        # Next session & This cycle non-empty, plain text (no pill radius, no chip background, no icons)
        assert m["copy"]["nextLabel"] == "Next session", f"{vw}: {m['copy']}"
        assert m["copy"]["cycleLabel"] == "This cycle", f"{vw}: {m['copy']}"
        assert " · " in m["copy"]["nextValue"] and "13:00" in m["copy"]["nextValue"], (
            f"{vw}: unexpected Next session {m['copy']['nextValue']!r}"
        )
        assert m["copy"]["cycleValue"] == "Reading 4 of 7 parts done", (
            f"{vw}: unexpected This cycle {m['copy']['cycleValue']!r}"
        )
        assert m["aside"]["icons"] == 0, f"{vw}: decorative icons in aside: {m['aside']['icons']}"
        for key, st in m["aside"]["styles"].items():
            assert st["radius"] == 0, f"{vw}: {key} has border-radius {st['radius']}"
            assert st["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), f"{vw}: {key} has chip bg {st['bg']}"
            assert st["shadow"] == "none", f"{vw}: {key} has shadow {st['shadow']}"

        # Buttons >= 44x44, full text, visible focus, natural tab order
        assert len(m["buttons"]) == 2, f"{vw}: expected 2 buttons, got {m['buttons']}"
        for b in m["buttons"]:
            assert b["w"] >= 44 and b["h"] >= 44, f"{vw}: button {b['text']} < 44x44 ({b['w']}x{b['h']})"
            assert not b["clipped"], f"{vw}: button {b['text']} clipped"
            assert b["outlineStyle"] != "none" and b["outlineWidth"] >= 2, f"{vw}: button {b['text']} missing focus ring"
        assert m["buttons"][0]["left"] < m["buttons"][1]["left"], f"{vw}: Start must precede Fast-forward"

        # No horizontal scroll, no bottom bar overlap
        assert m["scrollWidth"] <= m["clientWidth"], f"{vw}: horizontal scroll {m['scrollWidth']} > {m['clientWidth']}"
        assert not m["bottomOverlap"], f"{vw}: bottom bar overlap"

        if vw in (1280, 1440):
            shot = OUT_DIR / f"today_{vw}.png"
            page.screenshot(path=str(shot), full_page=False)
            assert shot.exists() and shot.stat().st_size > 1000, f"missing screenshot {shot}"

    # 1b. Shorter desktop window (1440x700): today_1440_scroll.png & no broken layout
    page.set_viewport_size({"width": 1440, "height": 700})
    page.wait_for_timeout(200)
    m_scroll = page.evaluate(MEASURE_DESKTOP)
    report["desktop"]["1440x700"] = m_scroll
    assert m_scroll["scrollWidth"] <= m_scroll["clientWidth"]
    assert not m_scroll["bottomOverlap"]
    assert m_scroll["firstChild"]["top"] >= m_scroll["area"]["top"] + 24, (
        f"1440x700: firstChild clipped under nav ({m_scroll['firstChild']['top']} vs {m_scroll['area']['top']})"
    )
    assert abs(m_scroll["aside"]["top"] - m_scroll["session"]["top"]) <= 8
    assert m_scroll["aside"]["h"] >= 0.45 * m_scroll["session"]["h"]
    shot_scroll = OUT_DIR / "today_1440_scroll.png"
    page.screenshot(path=str(shot_scroll), full_page=False)
    assert shot_scroll.exists() and shot_scroll.stat().st_size > 1000, f"missing screenshot {shot_scroll}"

    # 1c. Overflow desktop window (1440x480): when content exceeds available height, top-aligned & natural scroll
    page.set_viewport_size({"width": 1440, "height": 480})
    page.wait_for_timeout(150)
    m_overflow = page.evaluate(MEASURE_DESKTOP)
    assert m_overflow["scrollWidth"] <= m_overflow["clientWidth"]
    assert not m_overflow["bottomOverlap"]
    assert abs(m_overflow["firstChild"]["top"] - (m_overflow["area"]["top"] + m_overflow["shell"]["padTop"])) <= 2, (
        f"1440x480: overflow content not top-aligned ({m_overflow['firstChild']['top']} vs {m_overflow['area']['top'] + m_overflow['shell']['padTop']})"
    )

    # 2. Contrast >= 4.5:1 in both light and dark themes
    for theme in ("light", "dark"):
        page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
        page.wait_for_timeout(100)
        ratios = page.evaluate(CONTRAST_JS)
        report["contrast"][theme] = ratios
        for sel, r in ratios.items():
            assert r >= 4.5, f"{theme} contrast on {sel} is {r} < 4.5"
    page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")

    # 3. Mobile & tablet (< 1024 px): single 560 px column, right column stacked below session and visible
    for vw, vh in [(320, 640), (380, 720), (768, 900)]:
        page.set_viewport_size({"width": vw, "height": vh})
        page.wait_for_timeout(150)
        m = page.evaluate(MEASURE_DESKTOP)
        report["responsive"][str(vw)] = {
            "shellW": m["shell"]["w"],
            "shellTop": round(m["shell"]["top"], 1),
            "sessionTop": round(m["session"]["top"], 1),
            "sessionBottom": round(m["session"]["bottom"]),
            "asideTop": round(m["aside"]["top"]),
            "asideVisible": m["aside"]["visible"],
            "scrollWidth": m["scrollWidth"],
            "clientWidth": m["clientWidth"],
        }
        assert m["shell"]["w"] <= 560, f"{vw}: mobile/tablet shell width {m['shell']['w']} > 560"
        assert m["aside"]["visible"], f"{vw}: aside hidden on mobile/tablet"
        assert m["aside"]["top"] >= m["session"]["bottom"] - 1, (
            f"{vw}: aside not stacked below session (aside.top={m['aside']['top']}, session.bottom={m['session']['bottom']})"
        )
        assert m["scrollWidth"] <= m["clientWidth"], f"{vw}: horizontal scroll {m['scrollWidth']} > {m['clientWidth']}"
        if vw == 380:
            # At 380 px: the block starts in the first 20% of the page (not centered)
            assert m["shell"]["top"] <= 0.20 * vh, (
                f"380: shell top {m['shell']['top']} > 20% of viewport height {vh}"
            )
            assert m["session"]["top"] <= 0.20 * vh, (
                f"380: session top {m['session']['top']} > 20% of viewport height {vh}"
            )

    # 4. Empty schedule fallback: 'No session days configured'
    page.set_viewport_size({"width": 1280, "height": 900})
    page.evaluate("""() => {
        D.settings.schedule = [];
        D.settings.sessions = [];
        D.profile.days = [];
        save();
        refreshAll();
    }""")
    page.wait_for_timeout(150)
    empty_next = page.evaluate("document.getElementById('todayNextValue').innerText.trim()")
    assert empty_next == "No session days configured", f"unexpected empty fallback: {empty_next!r}"
    report["emptyFallback"] = empty_next

    assert not errors, f"page errors: {errors}"
    browser.close()

print(json.dumps(report, indent=2))
print("TODAY_DESKTOP_LAYOUT_OK")
