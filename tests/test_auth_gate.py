"""Phase A1: an account is required to use the app (no guest, no demo).

Playwright + an isolated server on a throwaway data dir.

Contract checked here:
- with no session, /app shows #authOverlay and paints no user views
  (#v-hoy and #v-prog hidden or empty) and window.D carries no real log;
- an orphan local document (deleted user / guest era) is left in storage but
  never loaded for an anonymous visitor;
- ?demo=1 changes nothing: the overlay is still the only thing on screen;
- with a session the app boots normally and the overlay stays hidden;
- POST /api/logout + reload brings the overlay back;
- a 401 on /api/progress returns the app to the overlay;
- /api/config does not expose a `demo` key.

Run: cd tests && uv run --no-project --with playwright python test_auth_gate.py
"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server({"B2_REGISTER": "open"}) + "/"
NAME = "auth-gate-suite"
PASS = "auth-gate-suite-pass-9"

out = {}


def api(path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as r:
        body = r.read().decode()
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return body


def overlay_visible(pg):
    pg.wait_for_function(
        "() => getComputedStyle(document.getElementById('authOverlay')).display !== 'none'",
        timeout=8000,
    )


def overlay_hidden(pg):
    pg.wait_for_function(
        "() => getComputedStyle(document.getElementById('authOverlay')).display === 'none'",
        timeout=8000,
    )


def snapshot(pg):
    return pg.evaluate(
        """() => {
        const shown = (id) => {
            const el = document.getElementById(id);
            return !!el && getComputedStyle(el).display !== 'none';
        };
        const today = document.getElementById('todaySession');
        const prog = document.getElementById('progChartsEmpty');
        return {
            authVisible: shown('authOverlay'),
            todayShown: shown('v-hoy'),
            progShown: shown('v-prog'),
            todayHtml: today ? today.innerHTML.trim() : null,
            progHtml: prog ? prog.innerHTML.trim() : null,
            logLen: (window.D && Array.isArray(window.D.log)) ? window.D.log.length : null,
            user: !!(window.USER && window.USER.token),
        };
    }"""
    )


with sync_playwright() as p:
    browser = p.chromium.launch()

    # --- 1. No session: nothing but the login overlay ------------------------
    ctx = browser.new_context()
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    pg.wait_for_timeout(400)
    overlay_visible(pg)
    snap = snapshot(pg)
    assert snap["authVisible"] is True, snap
    assert snap["user"] is False, snap
    assert snap["logLen"] == 0, snap
    assert not snap["progShown"], snap
    assert snap["todayHtml"] == "" or not snap["todayShown"], snap
    out["1_no_session_overlay"] = snap

    # Orphan document: kept in storage, never painted.
    orphan = {"log": [{"date": "2020-01-01", "type": "ue", "part": 1, "correct": 5, "total": 6}],
              "errs": [], "stage": 0}
    pg.evaluate(
        "doc => localStorage.setItem('b2first_tracker_v1', JSON.stringify(doc))",
        orphan,
    )
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    overlay_visible(pg)
    snap = snapshot(pg)
    kept = pg.evaluate(
        "() => { try { return JSON.parse(localStorage.getItem('b2first_tracker_v1')); } catch (e) { return null; } }"
    )
    assert snap["logLen"] == 0, snap
    assert snap["todayHtml"] == "" or not snap["todayShown"], snap
    assert kept and len(kept.get("log", [])) == 1, "orphan document was not preserved"
    out["2_orphan_kept_not_shown"] = {"logLen": snap["logLen"], "stored": len(kept["log"])}

    # ?demo=1 does not change anything.
    pg.goto(URL + "app?demo=1", wait_until="networkidle")
    pg.wait_for_timeout(400)
    overlay_visible(pg)
    snap = snapshot(pg)
    assert snap["authVisible"] is True and snap["logLen"] == 0, snap
    out["3_demo_query_ignored"] = snap
    assert errors == [], errors
    ctx.close()

    # --- 2. With a session the app boots normally ---------------------------
    ctx = browser.new_context()
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    user = login_user(pg, URL, NAME, PASS)
    overlay_hidden(pg)
    snap = snapshot(pg)
    assert snap["user"] is True and snap["todayShown"] is True, snap
    out["4_session_boots"] = snap

    # --- 3. Logout + reload brings the overlay back -------------------------
    api("api/logout", {"token": user["token"]})
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    overlay_visible(pg)
    snap = snapshot(pg)
    assert snap["user"] is False and snap["logLen"] == 0, snap
    out["5_logout_reload_overlay"] = snap

    # --- 4. A 401 on /api/progress returns to the overlay -------------------
    user = login_user(pg, URL, NAME, PASS)
    overlay_hidden(pg)

    def reject_progress(route):
        route.fulfill(status=401, content_type="application/json",
                      body=json.dumps({"error": "session expired"}))

    pg.route("**/api/progress*", reject_progress)
    pg.reload(wait_until="domcontentloaded")
    overlay_visible(pg)
    snap = snapshot(pg)
    assert snap["user"] is False and snap["logLen"] == 0, snap
    out["6_progress_401_overlay"] = snap
    pg.unroute("**/api/progress*", reject_progress)
    assert errors == [], errors
    ctx.close()
    browser.close()

# --- 5. /api/config has no demo key -----------------------------------------
cfg = api("api/config")
assert "demo" not in cfg, cfg
assert cfg.get("register") in ("open", "closed"), cfg
out["7_config_no_demo"] = cfg

# --- 6. Data routes answer 401 with no token --------------------------------
import urllib.error

for route in ("api/progress?download=1", "api/me", "api/users"):
    try:
        api(route)
        raise AssertionError(route + " answered without a token")
    except urllib.error.HTTPError as e:
        assert e.code == 401, (route, e.code)
        out["8_no_token_" + route.split("?")[0].split("/")[-1]] = e.code

print(json.dumps(out, ensure_ascii=False, indent=1))
print("auth gate OK")
sys.exit(0)
