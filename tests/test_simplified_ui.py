"""Phase 46 — four top-level tabs, one-card Today, plain language.

Standalone Playwright suite (no pytest). Run with:
    python3 tests/test_simplified_ui.py
"""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = Path(__file__).with_name("out")
OUT.mkdir(exist_ok=True)

FORBIDDEN = re.compile(r"R&UoE|F51|Keys |Phase 2|Thresholds|Rotation|Gate")
TABS = ["Today", "Practise", "Progress", "Plan"]
GROUPS = {
    "practice": ("practice", "practice", ["practice", "exam", "partes", "ia"]),
    "progress": ("prog", "progress", ["prog", "graf", "err"]),
}
SUBTABS = {
    "practice": "#subnav-practise",
    "progress": "#subnav-progress",
}


def visible_active(pg):
    return pg.evaluate(
        """() => {
        const visible = [...document.querySelectorAll('.view.active')]
            .filter(el => el.offsetParent !== null);
        return visible.length ? visible[visible.length - 1].id : null;
    }"""
    )


def seed_session_today(pg):
    pg.evaluate(
        """() => {
        const key = PLAN_WEEK_BY_JS[new Date().getDay()];
        D.profile = null;
        D.diag = null;
        D.settings = Object.assign({}, SETTINGS_DEFAULT, {week: {}});
        PLAN_WEEK_KEYS.forEach(k => {
            D.settings.week[k] = {mode: 'off', preset: null, parts: planEmptyParts(), min: null, time: ''};
        });
        D.settings.week[key] = {mode: 'custom', preset: 'ue_full', parts: planEmptyParts(), min: 45, time: '18:00'};
        D.activeSession = null;
        save();
        refreshAll();
    }"""
    )
    pg.wait_for_timeout(250)


def seed_rest_day(pg):
    pg.evaluate(
        """() => {
        D.profile = null;
        D.diag = null;
        D.settings = Object.assign({}, SETTINGS_DEFAULT, {week: {}});
        PLAN_WEEK_KEYS.forEach(k => {
            D.settings.week[k] = {mode: 'off', preset: null, parts: planEmptyParts(), min: null, time: ''};
        });
        D.activeSession = null;
        save();
        refreshAll();
    }"""
    )
    pg.wait_for_timeout(250)


def run():
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ----- mobile page (390x844) -----
        pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL + "app", wait_until="networkidle")
        login_owner(pg, URL)
        pg.wait_for_timeout(500)

        # 1. Exactly four top-level tabs with the four names.
        labels = pg.eval_on_selector_all(
            "#sideNav button[data-view] .nav-label",
            "els => els.map(e => e.textContent.trim())",
        )
        assert len(labels) == 4, f"expected 4 top-level tabs, got {labels}"
        assert labels == TABS, f"tab labels are {labels}"
        out["1_tabs"] = labels

        # 2. Segmented controls reach every child; go() keeps working.
        reached = {}
        for parent, (nav_key, host, children) in GROUPS.items():
            pg.click(f"#sideNav button[data-view='{nav_key}']")
            pg.wait_for_timeout(120)
            for child in children:
                pg.click(f"{SUBTABS[host]} button[data-view='{child}']")
                pg.wait_for_timeout(120)
                active = visible_active(pg)
                assert active == "v-" + child, f"{parent}/{child} showed {active}"
                reached[f"{parent}/{child}"] = active
        for name in ["exam", "graf", "err", "partes", "practice", "ia"]:
            pg.evaluate(f"go('{name}')")
            pg.wait_for_timeout(120)
            active = visible_active(pg)
            assert active == "v-" + name, f"go('{name}') showed {active}"
            reached["go:" + name] = active
        out["2_reached"] = reached

        # Today with a session: Start + at most one primary + plain copy.
        seed_session_today(pg)
        pg.evaluate("applyTheme('dark'); showView('hoy')")
        pg.wait_for_timeout(250)
        row_buttons = pg.eval_on_selector_all(
            "#todaySessions .today-row button",
            "els => els.map(e => e.textContent.trim())",
        )
        assert "Start" in row_buttons, f"Today row has no Start button: {row_buttons}"
        out["3_start"] = row_buttons
        today = pg.evaluate(
            """() => {
            const scoped = id => {
                const el = document.getElementById(id);
                return el ? el.innerText : '';
            };
            const primaries = [...document.querySelectorAll('#v-hoy button.btn.ok')]
                .filter(b => b.offsetParent !== null).length;
            return {
                text: scoped('v-hoy'),
                primaries,
                acronymGridInToday: !!document.querySelector('#v-hoy #gUeChips'),
                rows: document.querySelectorAll('#todaySessions .today-row').length,
            };
        }"""
        )
        assert today["primaries"] <= 1, f"more than one primary button in Today: {today}"
        assert not today["acronymGridInToday"], "acronym grid is still inside #v-hoy"
        hit = FORBIDDEN.search(today["text"])
        assert hit is None, f"jargon still visible in Today: {hit.group(0)!r}"
        assert today["rows"] <= 3, f"more than three Today rows: {today}"
        out["3_today"] = today

        # 4. No session today -> rest sentence + one secondary button.
        seed_rest_day(pg)
        rest = pg.evaluate(
            """() => ({
            text: document.getElementById('v-hoy').innerText,
            btn: document.querySelector('#todaySessions button')?.textContent.trim() || '',
            primary: [...document.querySelectorAll('#v-hoy button.btn.ok')]
                .filter(b => b.offsetParent !== null).length,
        })"""
        )
        assert "Rest day" in rest["text"], f"rest day copy missing: {rest}"
        assert rest["btn"] == "Practise something", f"rest day button is {rest['btn']!r}"
        assert rest["primary"] == 0, f"rest day shows a primary button: {rest}"
        out["4_rest"] = rest

        # 5. Mobile: four tabs fit; sub-tabs scroll inside their row, not the page.
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.evaluate("showView('exam')")
        pg.wait_for_timeout(200)
        mobile = pg.evaluate(
            """() => {
            const nav = document.getElementById('sideNav');
            const sub = document.getElementById('subnav-practise');
            return {
                navScroll: nav.scrollWidth, navClient: nav.clientWidth,
                subScroll: sub.scrollWidth, subClient: sub.clientWidth,
                doc: document.documentElement.scrollWidth, win: window.innerWidth,
                navHeight: nav.getBoundingClientRect().height,
            };
        }"""
        )
        assert mobile["navScroll"] <= mobile["navClient"] + 1, f"bottom nav overflows: {mobile}"
        assert mobile["doc"] <= mobile["win"] + 1, f"page overflows at 390px: {mobile}"
        out["5_mobile"] = mobile
        pg.evaluate("applyTheme('dark')")
        pg.screenshot(path=str(OUT / "nav_390.png"))

        # 6. Plan keeps the collapse/expand structure from phase 44/45.
        pg.evaluate("showView('plan')")
        pg.wait_for_timeout(200)
        plan = pg.evaluate(
            """() => ({
            order: [...document.getElementById('v-plan').children].map(e => e.id).filter(Boolean),
            tuningDetails: document.getElementById('planTuning')?.tagName || '',
            accountDetails: document.getElementById('planAccount')?.tagName || '',
        })"""
        )
        assert plan["order"] == ["examCountdown", "weeklyPlanCard", "planCustom", "planTuning", "planAccount"], plan
        assert plan["tuningDetails"] == "DETAILS" and plan["accountDetails"] == "DETAILS", plan
        out["6_plan"] = plan

        # ----- screenshots -----
        seed_session_today(pg)
        pg.evaluate("applyTheme('dark'); showView('hoy')")
        pg.wait_for_timeout(200)
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.screenshot(path=str(OUT / "today_mobile.png"))

        desktop = browser.new_page(viewport={"width": 1280, "height": 900})
        desktop.goto(URL + "app", wait_until="networkidle")
        login_owner(desktop, URL)
        desktop.wait_for_timeout(400)
        seed_session_today(desktop)
        desktop.evaluate("applyTheme('dark'); showView('hoy')")
        desktop.wait_for_timeout(300)
        desktop.screenshot(path=str(OUT / "today_desktop_dark.png"))
        desktop.evaluate("showView('exam')")
        desktop.wait_for_timeout(300)
        desktop.screenshot(path=str(OUT / "practise_subnav.png"))
        desktop.evaluate("showView('prog')")
        desktop.wait_for_timeout(300)
        desktop.screenshot(path=str(OUT / "progress.png"))
        desktop.close()

        assert errors == [], f"page errors: {errors}"
        out["errors"] = errors
        browser.close()
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    run()
