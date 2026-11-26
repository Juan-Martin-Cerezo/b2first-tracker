"""Phase P1 acceptance: Progress view narrative hierarchy and hand-rolled SVG charts.

Verifies with Playwright + isolated_server():
- Rich synthetic log across 360x740 (touch) and 1280x800 (desktop), dark & light
  themes, and English & Spanish:
  * Progress view opens cleanly with zero console/page errors;
  * no horizontal overflow (scrollWidth <= innerWidth + 1);
  * summary KPIs (4) and per-skill bars with last-3 trend (4);
  * 3 SVG charts (#gEvol, #gPart, #gCons) with role="img", non-empty
    <title>/<desc>, real axes, and legends (no removed errors chart);
  * basic contrast check: axis text fill != surface background (and >= 4.5:1);
  * tap/click interaction updates the inline readout (.pg-tip.has-val);
  * collapsible numeric detail (#progDetail) expands cleanly without overflow;
  * screenshots saved to tests/out/progress-<vp>-<theme>.png.
- Single-log state: no NaN in any SVG path or coordinate.
- Dirty-data state: malformed entries are skipped without crashing or NaN.
- Empty state (no logs): shows #progChartsEmpty with CTA and no broken SVG charts.

Run: cd tests && uv run --no-project --with playwright python test_progress_view.py
"""
import datetime
import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
NAME = "prog-p1-suite"
PASS = "prog-p1-suite-pass-9"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT_DIR, exist_ok=True)


def day_offset(delta_days):
    return (datetime.date.today() + datetime.timedelta(days=delta_days)).isoformat()


def rich_doc():
    logs = [
        {"type": "ue", "part": 1, "date": day_offset(-34), "correct": 5, "total": 8, "min": 8},
        {"type": "ue", "part": 2, "date": day_offset(-31), "correct": 4, "total": 8, "min": 10},
        {"type": "ue", "part": 3, "date": day_offset(-28), "correct": 5, "total": 8, "min": 10},
        {"type": "ue", "part": 4, "date": day_offset(-25), "correct": 2, "total": 6, "min": 12},
        {"type": "ue", "part": 5, "date": day_offset(-22), "correct": 4, "total": 6, "min": 14},
        {"type": "ue", "part": 6, "date": day_offset(-19), "correct": 2, "total": 6, "min": 15},
        {"type": "ue", "part": 7, "date": day_offset(-16), "correct": 7, "total": 10, "min": 14},
        {"type": "ue", "part": 1, "date": day_offset(-12), "correct": 7, "total": 8, "min": 8},
        {"type": "ue", "part": 4, "date": day_offset(-8), "correct": 4, "total": 6, "min": 12},
        {"type": "ue", "part": 6, "date": day_offset(-3), "correct": 4, "total": 6, "min": 14},
        {"type": "rue", "date": day_offset(-1), "correct": 42, "total": 52, "min": 72},
        {"type": "w", "kind": "Essay", "date": day_offset(-27), "score": 13, "min": 40},
        {"type": "w", "kind": "Article", "date": day_offset(-15), "score": 15, "min": 38},
        {"type": "w", "kind": "Review", "date": day_offset(-5), "score": 17, "min": 36},
        {"type": "lp", "part": 2, "date": day_offset(-24), "correct": 6, "total": 10, "min": 10},
        {"type": "l", "date": day_offset(-14), "correct": 21, "total": 30, "min": 40},
        {"type": "l", "date": day_offset(-4), "correct": 25, "total": 30, "min": 38},
        {"type": "sp", "part": 2, "date": day_offset(-20), "score": 3, "min": 12},
        {"type": "sp", "part": 3, "date": day_offset(-10), "score": 4, "min": 12},
        {"type": "sp", "part": 4, "date": day_offset(-2), "score": 4.5, "min": 14},
    ]
    errs = [
        {"date": day_offset(-32), "code": "L-GAP", "desc": "Collocation miss", "fix": "Notebook"},
        {"date": day_offset(-30), "code": "G-ERR", "desc": "Inversion", "fix": "Drill"},
        {"date": day_offset(-26), "code": "G-ERR", "desc": "Conditionals", "fix": "Drill"},
        {"date": day_offset(-23), "code": "T-MIS", "desc": "Distractor", "fix": "Underline"},
        {"date": day_offset(-18), "code": "T-LIM", "desc": "Part 6 time", "fix": "Timer"},
        {"date": day_offset(-11), "code": "L-GAP", "desc": "Phrasal verb", "fix": "Cards"},
        {"date": day_offset(-6), "code": "T-MIS", "desc": "Audio trap", "fix": "Re-listen"},
        {"date": day_offset(-2), "code": "L-GAP", "desc": "Idiom", "fix": "Review"},
    ]
    return {
        "log": logs,
        "errs": errs,
        "examDates": [],
        "stage": 1,
        "settings": {"lang": "en", "weekGoal": 4},
        "overrides": {},
        "weekOverrides": {},
        "mat": {},
        "diag": None,
        "profile": {
            "examDate": day_offset(45),
            "targetGrade": "A",
            "skills": {"rue": 4, "w": 3, "l": 4, "sp": 3},
            "hoursWeek": 5,
            "days": ["mon", "wed", "fri"],
            "struggles": ["L-GAP"],
            "strugglesDeclared": ["Lexical gap"],
            "declaredAt": day_offset(-40),
        },
        "onboarded": True,
        "sessionOffset": 0,
    }


def put_doc(user, doc):
    req = urllib.request.Request(
        URL + "api/progress?user=" + user["id"],
        data=json.dumps(doc).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + user["token"],
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        r.read()


def parse_rgb(css_color):
    m = re.match(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", css_color or "")
    if not m:
        return None
    return tuple(float(m.group(i)) / 255.0 for i in (1, 2, 3))


def rel_lum(rgb):
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(c1, c2):
    rgb1, rgb2 = parse_rgb(c1), parse_rgb(c2)
    if not rgb1 or not rgb2:
        return None
    l1, l2 = rel_lum(rgb1), rel_lum(rgb2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


INSPECT_JS = r"""() => {
  const active = document.getElementById('v-prog').classList.contains('active');
  const scrollWidth = document.documentElement.scrollWidth;
  const innerWidth = window.innerWidth;
  const kpis = document.querySelectorAll('#pgKpis .pg-kpi').length;
  const skills = document.querySelectorAll('#pgSkills .pg-skill').length;
  const chartIds = ['gEvol', 'gPart', 'gCons'];
  const charts = chartIds.map(id => {
    const box = document.getElementById(id);
    const svg = box ? box.querySelector('svg') : null;
    const title = svg ? svg.querySelector('title') : null;
    const desc = svg ? svg.querySelector('desc') : null;
    const texts = svg ? [...svg.querySelectorAll('text')] : [];
    const lines = svg ? svg.querySelectorAll('line').length : 0;
    const paths = svg ? [...svg.querySelectorAll('path')].map(p => p.getAttribute('d') || '') : [];
    const leg = box ? box.querySelectorAll('.pg-legend .pg-leg-item').length : 0;
    const card = box ? box.closest('.card') : null;
    const surfaceBg = card ? getComputedStyle(card).backgroundColor : '';
    const axisFill = texts.length ? getComputedStyle(texts[0]).fill : '';
    const hasNaN = paths.some(d => /NaN|undefined/i.test(d)) ||
      (svg ? /NaN|undefined/.test(svg.innerHTML) : false);
    return {
      id,
      hasSvg: !!svg,
      role: svg ? svg.getAttribute('role') : null,
      title: title ? title.textContent.trim() : '',
      desc: desc ? desc.textContent.trim() : '',
      textCount: texts.length,
      textSample: texts.slice(0, 6).map(t => t.textContent.trim()),
      lines,
      legendItems: leg,
      surfaceBg,
      axisFill,
      hasNaN,
    };
  });
  return {
    active,
    scrollWidth,
    innerWidth,
    kpis,
    skills,
    charts,
    detailOpen: !!document.getElementById('progDetail')?.open,
  };
}"""


def main():
    out = {"matrix": [], "edges": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch()

        boot_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        bpg = boot_ctx.new_page()
        bpg.goto(URL + "app", wait_until="load")
        user = login_user(bpg, URL, NAME, PASS)
        doc = rich_doc()
        put_doc(user, doc)
        boot_ctx.close()

        viewports = [
            ("360x740", 360, 740, True),
            ("1280x800", 1280, 800, False),
        ]
        for vp_name, w, h, is_touch in viewports:
            for theme in ("light", "dark"):
                for lang in ("en", "es"):
                    ctx = browser.new_context(
                        viewport={"width": w, "height": h},
                        is_mobile=is_touch,
                        has_touch=is_touch,
                    )
                    pg = ctx.new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    pg.on(
                        "console",
                        lambda m: errors.append(m.text)
                        if m.type == "error" and "Failed to load resource" not in m.text else None,
                    )
                    pg.add_init_script(
                        "localStorage.setItem('b2first_user', %s);localStorage.setItem('b2first_theme', %s);"
                        % (json.dumps(json.dumps(user)), json.dumps(theme))
                    )
                    pg.goto(URL + "app", wait_until="load")
                    pg.wait_for_timeout(350)
                    pg.evaluate(
                        """([lang, theme]) => {
                            if (typeof hideOnboarding === 'function') hideOnboarding();
                            setThemeMode(theme);
                            if (LANG !== lang) setLang(lang);
                            showView('prog');
                        }""",
                        [lang, theme],
                    )
                    # Charts paint on the next idle tick (skeleton path), so wait
                    # for the real signal instead of a fixed sleep: a loaded Pi
                    # can take longer than 350 ms and the assertion would race.
                    pg.wait_for_function(
                        "document.querySelectorAll('.pg-chart svg').length >= 3",
                        timeout=10000,
                    )
                    pg.wait_for_timeout(150)

                    info = pg.evaluate(INSPECT_JS)
                    assert info["active"], f"{vp_name} {theme} {lang}: #v-prog not active"
                    assert info["scrollWidth"] <= info["innerWidth"] + 1, (
                        f"{vp_name} {theme} {lang}: horizontal overflow {info['scrollWidth']} > {info['innerWidth']}"
                    )
                    assert info["kpis"] == 4, f"expected 4 KPIs, got {info['kpis']}"
                    assert info["skills"] == 4, f"expected 4 skill rows, got {info['skills']}"
                    assert info["detailOpen"] is False, "numeric detail should start collapsed"

                    svg_count = sum(1 for c in info["charts"] if c["hasSvg"])
                    assert svg_count == 3, f"expected 3 SVG charts, got {info['charts']}"
                    for c in info["charts"]:
                        assert c["role"] == "img", f"{c['id']} missing role='img'"
                        assert c["title"], f"{c['id']} has empty <title>"
                        assert c["desc"], f"{c['id']} has empty <desc>"
                        assert c["lines"] >= 2, f"{c['id']} missing axis/grid lines"
                        assert c["textCount"] >= 2, f"{c['id']} missing axis labels"
                        assert c["legendItems"] >= 2, f"{c['id']} missing legend"
                        assert not c["hasNaN"], f"{c['id']} has NaN/undefined in SVG"
                        assert c["axisFill"] and c["axisFill"] != c["surfaceBg"], (
                            f"{c['id']} axis text equals surface: {c['axisFill']} vs {c['surfaceBg']}"
                        )
                        cr = contrast_ratio(c["axisFill"], c["surfaceBg"])
                        if cr is not None:
                            assert cr >= 4.5, (
                                f"{vp_name} {theme} {c['id']} axis contrast too low: {cr:.2f} "
                                f"({c['axisFill']} on {c['surfaceBg']})"
                            )

                    # Verify tap/click interaction shows point detail in .pg-tip
                    pg.click("#gEvol .pg-pt")
                    pg.wait_for_timeout(120)
                    tip_text = pg.evaluate("document.querySelector('#gEvol .pg-tip.has-val')?.textContent || ''")
                    assert "%" in tip_text and "/" in tip_text, f"evol tap tooltip did not update: {tip_text!r}"

                    pg.click("#gPart .pg-bar-hit")
                    pg.wait_for_timeout(120)
                    part_tip = pg.evaluate("document.querySelector('#gPart .pg-tip.has-val')?.textContent || ''")
                    assert "%" in part_tip, f"part tap tooltip did not update: {part_tip!r}"

                    # Save required screenshots (one per vp + theme)
                    if lang == "en":
                        pg.evaluate("window.scrollTo(0, 0)")
                        pg.wait_for_timeout(120)
                        shot = os.path.join(OUT_DIR, f"progress-{vp_name}-{theme}.png")
                        pg.screenshot(path=shot, full_page=True)

                    # Expanding numeric detail stays overflow-free
                    pg.click("#progDetail > summary")
                    pg.wait_for_timeout(150)
                    after_open = pg.evaluate("({open: document.getElementById('progDetail').open, sw: document.documentElement.scrollWidth, iw: window.innerWidth})")
                    assert after_open["open"] is True
                    assert after_open["sw"] <= after_open["iw"] + 1, (
                        f"{vp_name} {theme} {lang}: overflow after opening detail {after_open}"
                    )

                    assert not errors, f"{vp_name} {theme} {lang} errors: {errors}"
                    out["matrix"].append({
                        "vp": vp_name, "theme": theme, "lang": lang,
                        "scroll": f"{info['scrollWidth']}/{info['innerWidth']}",
                        "svgs": svg_count,
                    })
                    ctx.close()

        # Edge cases: empty user, single log, dirty data
        ctx = browser.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        edge_errors = []
        pg.on("pageerror", lambda e: edge_errors.append(str(e)))
        pg.add_init_script("localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user)))
        pg.goto(URL + "app", wait_until="load")
        pg.wait_for_timeout(300)
        pg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); showView('prog');")
        pg.wait_for_timeout(200)

        # 1) Empty user: no broken SVGs, visible CTA
        empty_state = pg.evaluate("""() => {
            D.log = []; D.errs = []; save(); refreshAll();
            const emptyBox = document.getElementById('progChartsEmpty');
            const cta = emptyBox ? emptyBox.querySelector('button') : null;
            return {
                emptyVisible: emptyBox && getComputedStyle(emptyBox).display !== 'none',
                hasCta: !!cta && getComputedStyle(cta).display !== 'none',
                svgsVisible: [...document.querySelectorAll('#v-prog svg')].filter(s => s.getBoundingClientRect().width > 0).length,
                kpis: document.querySelectorAll('#pgKpis .pg-kpi').length,
            };
        }""")
        assert empty_state["emptyVisible"] and empty_state["hasCta"], f"empty CTA missing: {empty_state}"
        assert empty_state["svgsVisible"] == 0, f"broken/empty SVG rendered on empty log: {empty_state}"
        assert empty_state["kpis"] == 4, empty_state
        out["edges"]["empty"] = empty_state

        # 2) Single log: no NaN in paths, renders clean dot
        single_state = pg.evaluate("""() => {
            D.log = [{type: 'ue', part: 3, date: new Date().toLocaleDateString('sv-SE'), correct: 6, total: 8, min: 8}];
            D.errs = [];
            save(); refreshAll();
            const evol = document.getElementById('gEvol');
            const paths = [...evol.querySelectorAll('path')].map(p => p.getAttribute('d') || '');
            const pts = evol.querySelectorAll('.pg-pt').length;
            const hasNaN = /NaN|undefined/i.test(evol.innerHTML);
            return {paths, pts, hasNaN, partSvgs: document.querySelectorAll('#gPart .pg-svg-wrap > svg').length};
        }""")
        assert single_state["pts"] == 1 and not single_state["hasNaN"], f"single log broke evolution chart: {single_state}"
        assert all("NaN" not in d for d in single_state["paths"]), single_state
        assert single_state["partSvgs"] == 1, single_state
        out["edges"]["single_log"] = single_state

        # 3) Dirty data mixed with valid log (malformed dates, NaN, zero totals, unknown codes)
        dirty_state = pg.evaluate("""() => {
            D.log = [
                {type: 'ue', part: 1, date: 'not-a-date', correct: 5, total: 8},
                {type: 'ue', part: 2, date: '2026-99-99', correct: 5, total: 8},
                {type: 'ue', part: 3, date: '2026-11-10', correct: 'bad', total: 0},
                {type: 'w', kind: 'Essay', date: '2026-11-11', score: NaN},
                {type: 'ue', part: 5, date: '2026-11-12', correct: 4, total: 6, min: 14},
                {type: 'w', kind: 'Essay', date: '2026-11-13', score: 16, min: 40},
            ];
            D.errs = [{date: 'bad', code: 'L-GAP'}, {date: '2026-11-12', code: 'BOGUS'}, {date: '2026-11-12', code: 'L-GAP'}];
            refreshAll();
            // Also verify Progress renderers directly tolerate null entries without throwing
            D.log.unshift(null);
            D.errs.unshift(null);
            renderProgSummary(); renderProgSkills();
            renderGrafEvol(); renderGrafPart(); renderGrafCons();
            const svgs = [...document.querySelectorAll('#v-prog .pg-svg-wrap > svg')];
            return {
                svgCount: svgs.length,
                anyNaN: svgs.some(s => /NaN|undefined/.test(s.innerHTML)),
            };
        }""")
        assert dirty_state["svgCount"] == 3 and not dirty_state["anyNaN"], f"dirty data broke charts: {dirty_state}"
        assert not edge_errors, f"edge case page errors: {edge_errors}"
        out["edges"]["dirty_data"] = dirty_state

        ctx.close()
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=1))
    sys.exit(0)


if __name__ == "__main__":
    main()
