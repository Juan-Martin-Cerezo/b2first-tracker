"""Skeleton loading: placeholders while the pull is in flight, no layout jump.

Covers the acceptance criteria of the skeleton phase:

  * a delayed pull (800 ms) paints `.sk*` on the active view with
    `aria-busy="true"`, and the view height before vs after differs <= 8 px;
  * an immediate pull paints no skeleton at all (no blink);
  * a pull that never answers drops the skeleton by the 4 s bail-out and the
    UI keeps working;
  * `prefers-reduced-motion: reduce` turns the animation off (animation-name
    none);
  * today, plan, log, stats, books and speaking open at 360 px with no console
    errors and no horizontal scroll.

The moment a skeleton appears is recorded in the page (MutationObserver), not
sampled from Python: a route handler that sleeps blocks the driver, and by the
time it returns the overlay is already gone.

Run:  cd tests && uv run --with playwright python test_skeleton.py
"""
import json
import time
import urllib.request

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
NAME = "skeleton-suite"
PASS = "skeleton-suite-pass-9"

# The account document the app pulls. The test seeds the same document into
# localStorage, so the local paint already reserves the final layout: the pull
# only refreshes it. Any movement while the skeleton is up is a real jump.
DOC = {
    "log": [],
    "errs": [],
    "examDates": [],
    "stage": 1,
    "settings": {
        "lang": "en",
        "schedule": [{"day": 1, "time": "17:00"}],
        "sessions": [{"day": 1, "time": "17:00"}],
        "rotationMode": "by-part",
        "itemsPerSession": 1,
    },
    "overrides": {},
    "weekOverrides": {},
    "mat": {},
    "diag": None,
    "profile": {
        "examDate": None,
        "targetGrade": "B",
        "skills": {"rue": 3, "w": 3, "l": 3, "sp": 3},
        "hoursWeek": 4,
        "days": ["mon"],
        "struggles": [],
        "strugglesDeclared": [],
    },
    "onboarded": True,
    "sessionOffset": 0,
}

# Seeds the session + document before the app's own scripts run, then records
# every skeleton that appears: presence, aria-busy and the host height.
# Page.add_init_script() takes no arguments, so the payload is inlined.
INIT_JS = """(() => {
    localStorage.setItem('b2first_user', %s);
    localStorage.setItem('b2first_tracker_v1_' + %s, %s);
    window.__skSeen = false;
    window.__skBusy = false;
    window.__skHeight = 0;
    window.__skAt = 0;
    const scan = () => {
        const layer = document.querySelector('.sk-layer');
        if (!layer || window.__skSeen) return;
        const host = layer.parentElement;
        window.__skSeen = true;
        window.__skAt = performance.now();
        window.__skHeight = host ? host.getBoundingClientRect().height : 0;
        window.__skBusy = !!host && host.getAttribute('aria-busy') === 'true';
    };
    document.addEventListener('DOMContentLoaded', () => {
        scan();
        new MutationObserver(scan)
            .observe(document.documentElement, {childList: true, subtree: true});
    });
})()"""


def init_script(user):
    return INIT_JS % (
        json.dumps(json.dumps(user)),
        json.dumps(user["id"]),
        json.dumps(json.dumps(DOC)),
    )

HEIGHT_JS = "() => { const el = document.getElementById('v-hoy'); return el ? el.getBoundingClientRect().height : 0; }"


def seed_progress(user):
    req = urllib.request.Request(
        URL + "api/progress?user=" + user["id"],
        data=json.dumps(DOC).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + user["token"],
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        r.read()


def delay_route(ms):
    """Intercept /api/progress and hold the response for `ms` milliseconds."""
    def handler(route):
        time.sleep(ms / 1000.0)
        route.continue_()
    return handler


def new_page(browser, user, viewport=(1280, 800), **ctx):
    context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, **ctx)
    pg = context.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on(
        "console",
        lambda m: errors.append(m.text)
        if m.type == "error" and "Failed to load resource" not in m.text else None,
    )
    pg.add_init_script(init_script(user))
    return context, pg, errors


def boot(pg):
    pg.goto(URL + "app", wait_until="domcontentloaded")
    pg.wait_for_timeout(250)
    pg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding();")


def test_delayed_pull(browser, user):
    context, pg, errors = new_page(browser, user)
    pg.route("**/api/progress**", delay_route(800))
    boot(pg)

    # Let the delayed fetch resolve and its refreshAll paint.
    pg.wait_for_timeout(1600)
    pg.wait_for_selector(".sk-layer", state="detached", timeout=4000)
    seen = pg.evaluate("!!window.__skSeen")
    busy = pg.evaluate("!!window.__skBusy")
    height_during = pg.evaluate("window.__skHeight")
    height_after = pg.evaluate(HEIGHT_JS)
    busy_after = pg.evaluate("document.getElementById('v-hoy').getAttribute('aria-busy')")

    jump = abs(height_after - height_during)
    print(json.dumps({
        "case": "delayed_pull",
        "seen": seen,
        "busy": busy,
        "busy_after": busy_after,
        "height_during": round(height_during, 1),
        "height_after": round(height_after, 1),
        "jump_px": round(jump, 1),
        "errors": errors,
    }))

    assert seen is True, "the delayed pull painted no skeleton"
    assert busy is True, "the skeleton host was not aria-busy"
    assert height_during > 0, "the skeleton host collapsed to 0 while loading"
    assert jump <= 8, "layout jumped %.1f px while the skeleton was up" % jump
    assert busy_after is None, "aria-busy was not cleared after the pull"
    assert not errors, "console/page errors during the delayed pull: %s" % errors
    context.close()


def test_immediate_pull(browser, user):
    context, pg, errors = new_page(browser, user)
    boot(pg)
    pg.wait_for_timeout(700)
    seen = pg.evaluate("!!window.__skSeen")
    print(json.dumps({"case": "immediate_pull", "seen": seen, "errors": errors}))
    assert seen is False, "a skeleton flashed on an immediate pull"
    assert not errors, "console/page errors: %s" % errors
    context.close()


def test_hung_pull(browser, user):
    context, pg, errors = new_page(browser, user)
    # Never answer: only the client's 4 s bail-out can clear the skeleton.
    pg.route("**/api/progress**", lambda route: None)
    boot(pg)

    pg.wait_for_timeout(600)
    seen = pg.evaluate("!!window.__skSeen")
    t0 = time.time()
    pg.wait_for_selector(".sk-layer", state="detached", timeout=5500)
    elapsed = time.time() - t0 + 0.6

    pg.evaluate("showView('plan')")
    pg.wait_for_timeout(300)
    active = pg.evaluate("document.querySelector('.view.active').id")
    print(json.dumps({"case": "hung_pull", "seen": seen, "cleared_s": round(elapsed, 2),
                      "active": active, "errors": errors}))

    assert seen is True, "the hung pull painted no skeleton"
    assert elapsed <= 4.5, "the skeleton outlived the 4 s bail-out (%.1fs)" % elapsed
    assert active == "v-plan", "the UI stopped working after a hung pull: %r" % active
    assert not errors, "console/page errors: %s" % errors
    context.close()


def test_reduced_motion(browser, user):
    context, pg, errors = new_page(browser, user, reduced_motion="reduce")
    boot(pg)
    styles = pg.evaluate("""() => {
        const host = document.querySelector('.view.active');
        const detach = skAttach(host, SK_HTML.today);
        const el = document.querySelector('.sk-title');
        const cs = getComputedStyle(el);
        const out = {animation: cs.animationName, busy: host.getAttribute('aria-busy')};
        detach();
        return out;
    }""")
    print(json.dumps({"case": "reduced_motion", **styles, "errors": errors}))
    assert styles["animation"] == "none", "reduced motion still animates: %s" % styles
    assert not errors, "console/page errors: %s" % errors
    context.close()


SPEAKING_JS = """() => {
    selectSessionStudio('fri-b');
    document.getElementById('spkPanel').style.display = 'block';
    document.getElementById('livePanel').style.display = 'block';
    renderSpeakingReport({
        bands: {grammar_vocabulary: 4, discourse_management: 3,
                pronunciation: null, interactive_communication: null},
        derived: {pronunciation_source: 'none'},
        metrics: {wpm: 132, fillers: 7, longest_silence: 2.4, speech_ratio: 0.71},
        proxies: {initiations: 4, response_latency_ms_p50: 820,
                  question_ratio: 0.3, overlap_ms: 400},
        worst: [{w: 'thoroughly', score: 42}],
        evidence: [{quote: 'Example evidence', note: 'note'}],
        fixes: ['One', 'Two', 'Three'],
    });
}"""


def test_views_360(browser, user):
    context, pg, errors = new_page(browser, user, viewport=(360, 740), is_mobile=True, has_touch=True)
    boot(pg)

    steps = [
        ("today", "showView('hoy')"),
        ("plan", "showView('plan')"),
        ("log", "showView('prog'); document.getElementById('logTable').scrollIntoView({block:'center'})"),
        ("stats", "showView('prog'); document.getElementById('statsTable').scrollIntoView({block:'center'})"),
        ("books", "showView('practice'); document.getElementById('onlineList').scrollIntoView({block:'start'})"),
        ("speaking", "showView('hoy');" + SPEAKING_JS.strip()),
    ]
    rows = []
    for name, js in steps:
        pg.evaluate(js)
        pg.wait_for_timeout(400)
        data = pg.evaluate("""() => ({
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
            skeletons: document.querySelectorAll('.sk-layer').length,
        })""")
        rows.append({"view": name, **data})
        assert data["scrollWidth"] <= data["innerWidth"] + 1, (
            "%s at 360px scrolls sideways: %s" % (name, data)
        )
        assert data["skeletons"] == 0, "%s left a skeleton behind: %s" % (name, data)
    print(json.dumps({"case": "views_360", "rows": rows, "errors": errors}))
    assert not errors, "console/page errors: %s" % errors
    context.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        boot_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        bpg = boot_ctx.new_page()
        bpg.goto(URL + "app", wait_until="networkidle")
        user = login_user(bpg, URL, NAME, PASS)
        seed_progress(user)
        boot_ctx.close()

        test_delayed_pull(browser, user)
        test_immediate_pull(browser, user)
        test_hung_pull(browser, user)
        test_reduced_motion(browser, user)
        test_views_360(browser, user)

        browser.close()
    print("VERDICT: ok")


if __name__ == "__main__":
    main()
