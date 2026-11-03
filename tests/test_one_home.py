"""Phase 47 — the one-home rule.

Every content block lives in exactly one .view. This suite fails the build
when a block, a heading, a number or a control comes back in a second place.

Standalone Playwright suite (no pytest). Run with:
    python3 tests/test_one_home.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = Path(__file__).with_name("out")
OUT.mkdir(exist_ok=True)

# The inventory from the phase brief: each id must appear once and in one view.
MARKERS = [
    # Today
    "todaySessions", "weekSummary",
    # Practise
    "practiceNow", "partsList", "practiceLibrary", "practiceBooks",
    "examPacing", "gUeChips", "examSelectGrid", "examSources",
    # Writing
    "iaCard",
    # Progress
    "recentList", "nextBox", "gates", "logTable", "statsTable",
    "gEvol", "gPart", "gErr", "gCons", "errList", "errPills",
    # Plan
    "examCountdown", "weeklyPlanCard", "planCustom", "planTuning", "planAccount",
]

# First-render bound for each tab (sub-tabs inherit their parent's bound).
BOUNDS = {
    "hoy": 12, "practice": 80, "exam": 80, "partes": 80, "ia": 80,
    "prog": 40, "graf": 40, "err": 40, "plan": 60,
}
LABELS = {
    "hoy": "Today", "practice": "Practise · Practice", "exam": "Practise · Exam",
    "partes": "Practise · Parts", "ia": "Practise · Writing",
    "prog": "Progress · Overview", "graf": "Progress · Charts", "err": "Progress · Errors",
    "plan": "Plan",
}
ORDER = ["hoy", "practice", "exam", "partes", "ia", "prog", "graf", "err", "plan"]

VIS = "e => e.checkVisibility && e.checkVisibility({checkVisibilityCSS:true, checkOpacity:true})"

SNAPSHOT = """(v) => {
    const vis = %s;
    const id = 'v-' + v;
    const sec = document.getElementById(id);
    if (!sec) return {missing: true};
    const controls = [...sec.querySelectorAll('button,input,select,textarea,a[href]')]
        .filter(e => e.closest('.view') === sec && vis(e));
    const heads = [...sec.querySelectorAll('h2,h3')]
        .filter(e => e.closest('.view') === sec && vis(e))
        .map(e => e.textContent.replace(/\\s+/g, ' ').trim().toLowerCase())
        .filter(Boolean);
    const keys = [...sec.querySelectorAll('[data-home-key]')]
        .map(e => e.getAttribute('data-home-key'));
    return {count: controls.length, heads: heads, keys: keys};
}""" % VIS


def snapshot(pg, view):
    pg.evaluate("v => showView(v)", view)
    pg.wait_for_timeout(120)
    return pg.evaluate(SNAPSHOT, view)


def run():
    report = {"counts": {}, "duplicate_headings": [], "duplicate_home_keys": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL + "app", wait_until="networkidle")
        login_owner(pg, URL)
        pg.wait_for_timeout(400)

        # 1 + 2. Each marker once, inside exactly one .view.
        markers = pg.evaluate(
            """(ids) => ids.map(id => {
                const all = [...document.querySelectorAll('#' + id)];
                const el = all[0];
                const view = el ? el.closest('.view') : null;
                return {id, count: all.length, view: view ? view.id : null};
            })""",
            MARKERS,
        )
        for m in markers:
            assert m["count"] == 1, f"marker #{m['id']} appears {m['count']} times"
            assert m["view"], f"marker #{m['id']} is not inside a .view"
        report["markers"] = markers

        # 3. Visible headings and home keys per view.
        snapshots = {}
        for view in ORDER:
            snap = snapshot(pg, view)
            assert not snap.get("missing"), f"view v-{view} is missing"
            snapshots[view] = snap

        owner = {}
        for view, snap in snapshots.items():
            for head in snap["heads"]:
                if head in owner and owner[head] != view:
                    report["duplicate_headings"].append([head, owner[head], view])
                else:
                    owner[head] = view
        key_owner = {}
        for view, snap in snapshots.items():
            for key in snap["keys"]:
                if key in key_owner and key_owner[key] != view:
                    report["duplicate_home_keys"].append([key, key_owner[key], view])
                else:
                    key_owner[key] = view

        assert not report["duplicate_headings"], (
            "the same heading is visible in two views: %s" % report["duplicate_headings"]
        )
        assert not report["duplicate_home_keys"], (
            "the same data-home-key is rendered in two views: %s"
            % report["duplicate_home_keys"]
        )

        # 4. Visible controls at first render, per tab and sub-tab.
        for view, snap in snapshots.items():
            report["counts"][view] = snap["count"]
            bound = BOUNDS[view]
            assert snap["count"] < bound, (
                "%s has %d visible controls (bound %d)" % (LABELS[view], snap["count"], bound)
            )

        report["errors"] = errors
        assert errors == [], f"page errors: {errors}"

        # Screenshots: the one onboarding screen, the Practise list, four tabs at 390px.
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.evaluate("showOnboarding()")
        pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / "onboarding_single.png"))
        pg.evaluate("hideOnboarding(); refreshAll()")
        pg.evaluate("showView('practice')")
        pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / "practice_list_390.png"))
        for view in ["hoy", "practice", "prog", "plan"]:
            pg.evaluate("v => showView(v)", view)
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(OUT / ("tab_%s_390.png" % view)))

        browser.close()

    print("control counts at first render:")
    for view in ORDER:
        print("  %-24s %3d  (bound %d)" % (LABELS[view], report["counts"][view], BOUNDS[view]))
    print("duplicate heading scan:", "clean" if not report["duplicate_headings"] else report["duplicate_headings"])
    print("duplicate data-home-key scan:", "clean" if not report["duplicate_home_keys"] else report["duplicate_home_keys"])
    print("markers:", json.dumps(report["markers"], ensure_ascii=False))
    print("page errors:", report["errors"])


if __name__ == "__main__":
    run()
