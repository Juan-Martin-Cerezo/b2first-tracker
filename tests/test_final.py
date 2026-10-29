import json
from playwright.sync_api import sync_playwright
from helpers import login_owner

URL = "http://127.0.0.1:8088/"
# Views hidden behind the "More" button in the mobile bottom nav (5 + More)
HIDDEN_VIEWS = {"graf", "err", "libros", "ia", "diag"}
ALL_VIEWS = ["hoy", "exam", "partes", "prog", "graf", "plan", "err", "libros", "ia", "diag"]


def goto_view(pg, name):
    if name in HIDDEN_VIEWS:
        pg.evaluate("document.getElementById('navMoreBtn').click()")
        pg.wait_for_timeout(80)
    pg.click(f"nav button[data-view='{name}']")
    pg.wait_for_timeout(250)


def js_txt_bg_contrast(pg):
    # Relative-luminance contrast of --txt over --bg, computed in the page.
    # getComputedStyle serializes oklch() unresolved here, so convert to sRGB first.
    return pg.evaluate(
        r"""() => {
        function toRgb(c) {
            if (c.indexOf('oklch') === 0) {
                const n = (c.match(/-?\d+(\.\d+)?/g) || []).map(Number);
                const L = n[0], C = n[1], H = n[2];
                const h = H * Math.PI / 180;
                const a = C * Math.cos(h), b = C * Math.sin(h);
                const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
                const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
                const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
                const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
                const lin = [
                    +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
                ];
                return lin.map(x => {
                    x = Math.min(1, Math.max(0, x));
                    return (x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055) * 255;
                });
            }
            return (c.match(/\d+(\.\d+)?/g) || []).map(Number).slice(0, 3);
        }
        function lum(rgb) {
            const f = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
            return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
        }
        const probe = document.createElement('span');
        probe.style.cssText = 'position:absolute;visibility:hidden;color:var(--txt);background:var(--bg)';
        document.body.appendChild(probe);
        const fg = getComputedStyle(probe).color;
        const bg = getComputedStyle(probe).backgroundColor;
        probe.remove();
        const l1 = lum(toRgb(fg)), l2 = lum(toRgb(bg));
        return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    }"""
    )


out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="networkidle")
    login_owner(pg, URL)
    out["titulo"] = pg.title()
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # TODAY: all sessions visible + rotation
    out["sesA"] = pg.evaluate("getComputedStyle(document.getElementById('sesA')).display")
    out["sesB"] = pg.evaluate("getComputedStyle(document.getElementById('sesB')).display")
    out["sesFull"] = pg.evaluate("getComputedStyle(document.getElementById('sesFull')).display")
    out["rot_opts"] = pg.eval_on_selector_all("#ovW option", "els => els.length")
    out["nextBox"] = pg.evaluate("document.getElementById('nextBox').textContent.slice(0,70)")

    # BOOKS: material + books
    goto_view(pg, "libros")
    pg.wait_for_timeout(800)
    out["material_cards"] = pg.eval_on_selector_all("#matList .book", "els => els.length")
    out["audio_players"] = pg.eval_on_selector_all("#matList audio", "els => els.length")
    out["libros_comprables"] = pg.eval_on_selector_all("#bookList .book", "els => els.length")

    # EXAM: timer with real time
    goto_view(pg, "exam")
    out["ex_timer"] = pg.evaluate("document.getElementById('exTimer').textContent")

    # PARTS: 15 exercises
    goto_view(pg, "partes")
    out["partes"] = pg.eval_on_selector_all("#partsList .step", "els => els.length")

    # PROGRESS: gates + stats + export
    goto_view(pg, "prog")
    out["gates"] = pg.eval_on_selector_all(".gate", "els => els.length")
    out["export_ok"] = pg.evaluate("typeof exportData === 'function'")

    # 1. Theme toggle: light -> dark -> persisted in localStorage
    pg.evaluate("localStorage.setItem('b2first_theme','light'); applyTheme('light')")
    pg.click("#themeToggle")
    theme_dark = pg.evaluate(
        "() => ({attr: document.documentElement.getAttribute('data-theme'), stored: localStorage.getItem('b2first_theme')})"
    )
    assert theme_dark == {"attr": "dark", "stored": "dark"}, f"Toggle did not go dark/persist: {theme_dark}"
    out["1_toggle_dark_persist"] = theme_dark

    # 2. In dark mode the body background is NOT rgb(0,0,0)
    dark_bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    assert dark_bg != "rgb(0, 0, 0)", f"Dark bg is pure black: {dark_bg}"
    out["2_dark_bg_not_black"] = dark_bg

    # 4. Contrast of --txt over --bg >= 4.5 in BOTH themes (computed in JS)
    contrast_dark = js_txt_bg_contrast(pg)
    assert contrast_dark >= 4.5, f"Dark --txt/--bg contrast < 4.5: {contrast_dark}"
    out["4_contrast_dark"] = round(contrast_dark, 2)

    # Persistence across reload
    pg.reload(wait_until="networkidle")
    if pg.evaluate(
        "typeof finishOnboarding==='function' && document.getElementById('onboardingOverlay') && document.getElementById('onboardingOverlay').style.display==='flex'"
    ):
        pg.evaluate("finishOnboarding()")
        pg.wait_for_timeout(300)
    persisted = pg.evaluate(
        "() => ({attr: document.documentElement.getAttribute('data-theme'), stored: localStorage.getItem('b2first_theme')})"
    )
    assert persisted == {"attr": "dark", "stored": "dark"}, f"Theme not persisted across reload: {persisted}"
    out["1_persist_after_reload"] = persisted

    pg.click("#themeToggle")
    theme_light = pg.evaluate(
        "() => ({attr: document.documentElement.getAttribute('data-theme'), stored: localStorage.getItem('b2first_theme')})"
    )
    assert theme_light == {"attr": "light", "stored": "light"}, f"Toggle back to light failed: {theme_light}"
    contrast_light = js_txt_bg_contrast(pg)
    assert contrast_light >= 4.5, f"Light --txt/--bg contrast < 4.5: {contrast_light}"
    out["4_contrast_light"] = round(contrast_light, 2)

    # 3. No bare outline:none without a :focus-visible replacement;
    #    at least 3 key controls show a visible focus ring (heuristic).
    css_check = pg.evaluate(
        r"""() => {
        let css = '';
        for (const ss of document.styleSheets) {
            try { for (const r of ss.cssRules) css += r.cssText + '\n'; } catch(e) {}
        }
        const bare = (css.match(/outline\s*:\s*(none|0(?!\.))/g) || []).length;
        const fv = (css.match(/:focus-visible[^{]*\{[^}]*outline/g) || []).length;
        return {bare, fv};
    }"""
    )
    assert css_check["bare"] == 0 or css_check["fv"] >= 1, f"outline:none without :focus-visible: {css_check}"
    rings = []
    for _ in range(15):
        pg.keyboard.press("Tab")
        ring = pg.evaluate(
            """() => {
            const el = document.activeElement;
            if (!el || el === document.body || el === document.documentElement) return null;
            const s = getComputedStyle(el);
            return {tag: el.tagName + (el.id ? '#' + el.id : ''), style: s.outlineStyle, width: parseFloat(s.outlineWidth) || 0};
        }"""
        )
        if ring and ring["style"] != "none" and ring["width"] >= 2:
            rings.append(ring["tag"])
        if len(rings) >= 3:
            break
    assert len(rings) >= 3, f"Fewer than 3 controls show a focus ring: {rings} (css: {css_check})"
    out["3_focus_rings"] = rings
    out["3_outline_rules"] = css_check

    # 5. The mobile nav does not cover the FAB
    fab_nav = pg.evaluate(
        """() => {
        const fab = document.getElementById('qlFab').getBoundingClientRect();
        const nav = document.getElementById('sideNav').getBoundingClientRect();
        return {fabBottomOffset: window.innerHeight - fab.bottom, navHeight: nav.height, overlapped: fab.bottom > nav.top};
    }"""
    )
    assert fab_nav["fabBottomOffset"] > fab_nav["navHeight"], f"FAB bottom not above nav height: {fab_nav}"
    assert not fab_nav["overlapped"], f"Nav overlaps the FAB: {fab_nav}"
    out["5_fab_above_nav"] = fab_nav

    # 6. errores_js empty while visiting all 10 views
    visited = []
    for v in ALL_VIEWS:
        goto_view(pg, v)
        active = pg.evaluate("document.querySelector('.view.active')?.id")
        visited.append(active)
    out["6_views_visited"] = visited
    assert all(a in ("v-" + v, "view-" + v) for a, v in zip(visited, ALL_VIEWS)), f"View activation failed: {visited}"
    assert errs == [], f"JS errors across the 10 views: {errs}"
    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
