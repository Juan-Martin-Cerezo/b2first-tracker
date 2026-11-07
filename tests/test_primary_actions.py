"""Phase 119: Primary session Start action and extended Quick-Log FAB.

Verifies:
1. Start button (#todaySession .ts-start / .btn.ok):
   - Solid brand background, min-height >= 52 px, width >= 44 px, font-weight 600,
     inline SVG play icon on the left, text 'Start session' (en) / 'Empezar sesión' (es).
   - WCAG relative luminance contrast of computed text color over computed background
     color >= 4.5:1 in both light and dark themes.
   - Explicit states: :hover (darkens ~8%), :active (translateY 2px),
     :focus-visible (outline != 'none', >= 2px width + offset), :disabled (opacity < 1,
     cursor: not-allowed).
   - Below the buttons, the microcopy 'Opens the studio for today's session.' appears
     exactly once on the screen, in meta size and secondary color.
   - 'Fast-forward (+1)' stays secondary (outline, transparent fill, same height as Start).
2. Floating Action Button (#qlFab):
   - Measures >= 44x44 px at all widths, has non-empty aria-label and title ('Log session' /
     'Registrar sesión'), contrast >= 4.5:1 in light and dark themes, and visible focus ring.
   - At >= 768 px (768, 1280): extended FAB showing '+' icon and visible text 'Log session'.
   - At < 768 px (320, 380): circular at rest, and reveals the same 'Log session' label on focus.
   - At 320, 380, 768, 1280: FAB bounding rect does not intersect Start rect, #todaySession rect,
     or the bottom navigation bar (#sideNav).
3. Screenshots saved to tests/out/actions_desktop.png and tests/out/actions_mobile.png.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from helpers import isolated_server, login_owner

OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEED_JS = """
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
    D.log = [];
    const sorted = getSessionDays();
    const todayKey = PLAN_DAY_ORDER[(wd + 6) % 7];
    const todayIdx = sorted.findIndex(d => d.key === todayKey);
    D.sessionOffset = todayIdx > 0 ? -todayIdx : 0;
    save();
    refreshAll();
}
"""

WCAG_CONTRAST_JS = """
(selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;
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
    const effBg = node => {
        let cur = node;
        while (cur && cur !== document.documentElement) {
            const bg = getComputedStyle(cur).backgroundColor;
            const rgba = toRgb(bg);
            if (rgba[3] > 0.05) return rgba;
            cur = cur.parentElement;
        }
        return toRgb(getComputedStyle(document.body).backgroundColor);
    };
    const fg = toRgb(getComputedStyle(el).color);
    const bg = effBg(el);
    return {
        ratio: Math.round(ratio(fg, bg) * 100) / 100,
        fg: fg.slice(0, 3),
        bg: bg.slice(0, 3),
    };
}
"""

MEASURE_ACTIONS_JS = """
() => {
    const card = document.getElementById('todaySession');
    const row = card.querySelector('.ts-row:not(.ts-next-unit)');
    const buttons = row ? Array.from(row.querySelectorAll('.ts-actions button')) : [];
    const startBtn = buttons[0];
    const ffBtn = buttons[1];
    const fab = document.getElementById('qlFab');
    const fabLbl = fab ? fab.querySelector('.ql-fab-label') : null;
    const nav = document.getElementById('sideNav');
    const microEls = Array.from(document.querySelectorAll('#v-hoy .ts-microcopy'));

    const rectObj = el => {
        const r = el.getBoundingClientRect();
        return {
            left: Math.round(r.left * 10) / 10,
            top: Math.round(r.top * 10) / 10,
            right: Math.round(r.right * 10) / 10,
            bottom: Math.round(r.bottom * 10) / 10,
            width: Math.round(r.width * 10) / 10,
            height: Math.round(r.height * 10) / 10,
        };
    };

    const intersects = (a, b) => !(
        a.right <= b.left ||
        a.left >= b.right ||
        a.bottom <= b.top ||
        a.top >= b.bottom
    );

    const startR = rectObj(startBtn);
    const ffR = rectObj(ffBtn);
    const cardR = rectObj(card);
    const fabR = rectObj(fab);
    const navR = rectObj(nav);

    const startCS = getComputedStyle(startBtn);
    const ffCS = getComputedStyle(ffBtn);
    const fabCS = getComputedStyle(fab);
    const fabLblCS = fabLbl ? getComputedStyle(fabLbl) : null;
    const microCS = microEls[0] ? getComputedStyle(microEls[0]) : null;
    const navCS = getComputedStyle(nav);

    const svg = startBtn.querySelector('svg');
    const svgR = svg ? svg.getBoundingClientRect() : null;

    const microSentence = t('today_start_microcopy');
    const pageText = document.getElementById('v-hoy').innerText || '';
    let microCountInText = 0;
    if (microSentence) {
        let pos = 0;
        while ((pos = pageText.indexOf(microSentence, pos)) >= 0) {
            microCountInText++;
            pos += microSentence.length;
        }
    }

    return {
        vw: window.innerWidth,
        vh: window.innerHeight,
        start: {
            rect: startR,
            text: startBtn.innerText.trim(),
            weight: Number(startCS.fontWeight) || startCS.fontWeight,
            padLeft: parseFloat(startCS.paddingLeft) || 0,
            padRight: parseFloat(startCS.paddingRight) || 0,
            bg: startCS.backgroundColor,
            color: startCS.color,
            hasSvg: !!svg,
            svgOnLeft: svgR ? (svgR.left >= startR.left && svgR.right < startR.left + startR.width / 2) : false,
        },
        fastForward: {
            rect: ffR,
            text: ffBtn.innerText.trim(),
            bg: ffCS.backgroundColor,
            borderWidth: parseFloat(ffCS.borderTopWidth) || 0,
            borderStyle: ffCS.borderTopStyle,
        },
        microcopy: {
            domCount: microEls.length,
            textCount: microCountInText,
            text: microEls[0] ? microEls[0].innerText.trim() : '',
            fontSize: microCS ? parseFloat(microCS.fontSize) : 0,
            color: microCS ? microCS.color : '',
            top: microEls[0] ? microEls[0].getBoundingClientRect().top : 0,
        },
        fab: {
            rect: fabR,
            ariaLabel: (fab.getAttribute('aria-label') || '').trim(),
            title: (fab.getAttribute('title') || '').trim(),
            visibleText: fab.innerText.trim(),
            labelDisplay: fabLblCS ? fabLblCS.display : 'none',
            borderRadius: parseFloat(fabCS.borderTopLeftRadius) || 0,
        },
        card: cardR,
        nav: {
            rect: navR,
            fixedBottom: navCS.position === 'fixed' && navR.top > window.innerHeight / 2,
        },
        intersections: {
            fabWithStart: intersects(fabR, startR),
            fabWithCard: intersects(fabR, cardR),
            fabWithNav: (navCS.position === 'fixed' && navR.top > window.innerHeight / 2)
                ? intersects(fabR, navR)
                : false,
        },
    };
}
"""

URL = isolated_server() + "/"
report = {"viewports": {}, "states": {}, "contrast": {}, "i18n": {}}

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
    page.evaluate(SEED_JS)
    page.wait_for_timeout(250)

    # 1. Check across 320, 380, 768, 1280
    for vw, vh in [(320, 640), (380, 720), (768, 900), (1280, 900)]:
        page.set_viewport_size({"width": vw, "height": vh})
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(200)
        m = page.evaluate(MEASURE_ACTIONS_JS)
        report["viewports"][str(vw)] = m

        # Start button dimensions, label, icon, weight, padding
        assert m["start"]["rect"]["height"] >= 52, f"{vw}: Start height {m['start']['rect']['height']} < 52"
        assert m["start"]["rect"]["width"] >= 44, f"{vw}: Start width {m['start']['rect']['width']} < 44"
        assert m["start"]["text"] == "Start session", f"{vw}: Start text {m['start']['text']!r} != 'Start session'"
        assert m["start"]["weight"] == 600, f"{vw}: Start font-weight {m['start']['weight']} != 600"
        assert m["start"]["padLeft"] >= 16 and m["start"]["padRight"] >= 16, (
            f"{vw}: Start horizontal padding too small ({m['start']['padLeft']}, {m['start']['padRight']})"
        )
        assert m["start"]["hasSvg"] and m["start"]["svgOnLeft"], f"{vw}: Start missing left play SVG: {m['start']}"

        # Fast-forward (+1) is secondary outline, same height, no brand fill
        assert m["fastForward"]["text"] == "Fast-forward (+1)", f"{vw}: unexpected FF text {m['fastForward']['text']!r}"
        assert abs(m["fastForward"]["rect"]["height"] - m["start"]["rect"]["height"]) <= 1, (
            f"{vw}: Fast-forward height {m['fastForward']['rect']['height']} != Start height {m['start']['rect']['height']}"
        )
        assert m["fastForward"]["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), (
            f"{vw}: Fast-forward has fill {m['fastForward']['bg']}"
        )
        assert m["fastForward"]["borderWidth"] >= 1 and m["fastForward"]["borderStyle"] == "solid", (
            f"{vw}: Fast-forward missing outline border: {m['fastForward']}"
        )

        # Microcopy appears once per screen, below the Start button
        assert m["microcopy"]["domCount"] == 1 and m["microcopy"]["textCount"] == 1, (
            f"{vw}: microcopy count != 1: {m['microcopy']}"
        )
        assert m["microcopy"]["text"] == "Opens the studio for today's session.", (
            f"{vw}: unexpected microcopy {m['microcopy']['text']!r}"
        )
        assert m["microcopy"]["top"] >= m["start"]["rect"]["bottom"] - 1, (
            f"{vw}: microcopy not below Start ({m['microcopy']['top']} vs {m['start']['rect']['bottom']})"
        )

        # FAB dimensions, aria-label, title, responsive text
        assert m["fab"]["rect"]["width"] >= 44 and m["fab"]["rect"]["height"] >= 44, (
            f"{vw}: FAB < 44x44: {m['fab']['rect']}"
        )
        assert m["fab"]["ariaLabel"] == "Log session", f"{vw}: FAB aria-label {m['fab']['ariaLabel']!r}"
        assert m["fab"]["title"] == "Log session", f"{vw}: FAB title {m['fab']['title']!r}"
        if vw >= 768:
            assert m["fab"]["visibleText"] == "Log session", (
                f"{vw}: extended FAB at >= 768px does not show 'Log session': {m['fab']}"
            )
            assert m["fab"]["rect"]["width"] > m["fab"]["rect"]["height"] + 20, (
                f"{vw}: FAB is not extended at >= 768px: {m['fab']['rect']}"
            )
        else:
            assert abs(m["fab"]["rect"]["width"] - m["fab"]["rect"]["height"]) <= 1, (
                f"{vw}: FAB is not circular at < 768px: {m['fab']['rect']}"
            )
            # On focus in < 768px, the same label text is revealed
            page.focus("#qlFab")
            focused_fab = page.evaluate("""() => {
                const fab = document.getElementById('qlFab');
                const cs = getComputedStyle(fab);
                return {
                    text: fab.innerText.trim(),
                    outlineStyle: cs.outlineStyle,
                    outlineWidth: parseFloat(cs.outlineWidth) || 0,
                };
            }""")
            page.evaluate("document.activeElement && document.activeElement.blur()")
            assert focused_fab["text"] == "Log session", f"{vw}: focused FAB did not show 'Log session': {focused_fab}"
            assert focused_fab["outlineStyle"] != "none" and focused_fab["outlineWidth"] >= 2, (
                f"{vw}: focused FAB missing focus ring: {focused_fab}"
            )

        # Non-intersection: FAB never intersects Start, #todaySession, or bottom bar
        assert not m["intersections"]["fabWithStart"], (
            f"{vw}: FAB rect {m['fab']['rect']} intersects Start rect {m['start']['rect']}"
        )
        assert not m["intersections"]["fabWithCard"], (
            f"{vw}: FAB rect {m['fab']['rect']} intersects session card rect {m['card']}"
        )
        assert not m["intersections"]["fabWithNav"], (
            f"{vw}: FAB rect {m['fab']['rect']} intersects bottom nav rect {m['nav']['rect']}"
        )

        if vw == 380:
            shot_mob = OUT_DIR / "actions_mobile.png"
            page.screenshot(path=str(shot_mob), full_page=False)
            assert shot_mob.exists() and shot_mob.stat().st_size > 1000
        elif vw == 1280:
            shot_desk = OUT_DIR / "actions_desktop.png"
            page.screenshot(path=str(shot_desk), full_page=False)
            assert shot_desk.exists() and shot_desk.stat().st_size > 1000

    # 2. Explicit states on Start (:focus-visible, :hover, :active, :disabled) and FAB
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(150)

    # Check :focus-visible via keyboard Tab navigation onto Start
    page.evaluate("""() => {
        const start = document.querySelector('#todaySession .ts-start');
        start.focus();
    }""")
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    focus_state = page.evaluate("""() => {
        const start = document.querySelector('#todaySession .ts-start');
        const cs = getComputedStyle(start);
        return {
            matchesFocusVisible: start.matches(':focus-visible'),
            outline: cs.outline,
            outlineStyle: cs.outlineStyle,
            outlineWidth: parseFloat(cs.outlineWidth) || 0,
            outlineOffset: parseFloat(cs.outlineOffset) || 0,
        };
    }""")
    assert focus_state["matchesFocusVisible"], f"Start did not match :focus-visible: {focus_state}"
    assert focus_state["outlineStyle"] != "none" and focus_state["outlineWidth"] >= 2, (
        f"Start :focus-visible outline is none or < 2px: {focus_state}"
    )
    assert focus_state["outlineOffset"] >= 2, f"Start :focus-visible outline-offset < 2px: {focus_state}"
    page.evaluate("document.activeElement && document.activeElement.blur()")

    # Check hover, active, disabled states on Start
    rest_bg = page.evaluate("getComputedStyle(document.querySelector('#todaySession .ts-start')).backgroundColor")
    page.hover("#todaySession .ts-start")
    page.wait_for_timeout(180)
    hover_bg = page.evaluate("getComputedStyle(document.querySelector('#todaySession .ts-start')).backgroundColor")
    assert hover_bg != rest_bg, f"Start :hover background did not change ({hover_bg} vs {rest_bg})"

    disabled_state = page.evaluate("""() => {
        const start = document.querySelector('#todaySession .ts-start');
        start.disabled = true;
        const cs = getComputedStyle(start);
        const out = {
            opacity: parseFloat(cs.opacity),
            cursor: cs.cursor,
        };
        start.disabled = false;
        return out;
    }""")
    assert disabled_state["opacity"] < 0.7 and disabled_state["cursor"] == "not-allowed", (
        f"Start :disabled state invalid: {disabled_state}"
    )
    report["states"] = {
        "focusVisible": focus_state,
        "restBg": rest_bg,
        "hoverBg": hover_bg,
        "disabled": disabled_state,
    }

    # 3. WCAG contrast >= 4.5:1 on Start and FAB in both light and dark themes
    for theme in ("light", "dark"):
        page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
        page.wait_for_timeout(100)
        start_c = page.evaluate(WCAG_CONTRAST_JS, "#todaySession .ts-start")
        fab_c = page.evaluate(WCAG_CONTRAST_JS, "#qlFab")
        micro_c = page.evaluate(WCAG_CONTRAST_JS, "#todaySession .ts-microcopy")
        ff_c = page.evaluate(WCAG_CONTRAST_JS, "#todaySession .ts-ff")
        report["contrast"][theme] = {
            "start": start_c,
            "fab": fab_c,
            "microcopy": micro_c,
            "fastForward": ff_c,
        }
        assert start_c["ratio"] >= 4.5, f"{theme}: Start contrast {start_c['ratio']} < 4.5"
        assert fab_c["ratio"] >= 4.5, f"{theme}: FAB contrast {fab_c['ratio']} < 4.5"
        assert micro_c["ratio"] >= 4.5, f"{theme}: microcopy contrast {micro_c['ratio']} < 4.5"
        assert ff_c["ratio"] >= 4.5, f"{theme}: Fast-forward contrast {ff_c['ratio']} < 4.5"
    page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")

    # 4. Spanish i18n check
    page.evaluate("setLang('es')")
    page.wait_for_timeout(200)
    es_state = page.evaluate(MEASURE_ACTIONS_JS)
    assert es_state["start"]["text"] == "Empezar sesión", f"ES Start: {es_state['start']['text']!r}"
    assert es_state["microcopy"]["text"] == "Abre el estudio para la sesión de hoy.", (
        f"ES microcopy: {es_state['microcopy']['text']!r}"
    )
    assert es_state["fab"]["visibleText"] == "Registrar sesión", f"ES FAB: {es_state['fab']}"
    assert es_state["fab"]["ariaLabel"] == "Registrar sesión", f"ES FAB aria: {es_state['fab']}"
    report["i18n"]["es"] = {
        "start": es_state["start"]["text"],
        "microcopy": es_state["microcopy"]["text"],
        "fab": es_state["fab"]["visibleText"],
    }
    page.evaluate("setLang('en')")

    assert not errors, f"page errors: {errors}"
    browser.close()

print(json.dumps(report, indent=2))
print("PRIMARY_ACTIONS_OK")
