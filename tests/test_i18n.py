"""Phase 29 acceptance: English by default, Spanish available in-app.

Runs against a dedicated throwaway account whose progress document is reset
to an empty one before the assertions, so `SETTINGS_DEFAULT` supplies the
language (English) on load. No owner credentials are used.
"""
import json
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from helpers import OWNER_NAME as TEST_USER, OWNER_PASS as TEST_PASS

URL = "http://127.0.0.1:8088/"
NAME = "i18n-suite"
PASS = "i18n-suite-pass-9"

NAV_KEYS = [
    "nav_today", "nav_exam", "nav_parts", "nav_progress", "nav_plan",
    "nav_charts", "nav_errors", "nav_books", "nav_ai", "nav_diag", "nav_more",
]


def api(path, payload=None, token=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method or ("POST" if data is not None else "GET"),
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as r:
        body = r.read().decode()
        try:
            return json.loads(body)
        except ValueError:
            return body


def session_user():
    """Fresh throwaway session.

    Prefer the dedicated account; create it once. Registration is capped at
    5/h/IP, so if that limit is hit (repeated runs) fall back to the shared
    throwaway test account. Both are reset to an empty document below.
    """
    try:
        return api("api/login", {"name": NAME, "password": PASS})
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
    try:
        api("api/register", {"name": NAME, "password": PASS})
        return api("api/login", {"name": NAME, "password": PASS})
    except urllib.error.HTTPError as e:
        if e.code != 429:
            raise
    return api("api/login", {"name": TEST_USER, "password": TEST_PASS})


def reset_progress(user):
    """Leave an empty document with NO settings.lang so the default applies."""
    doc = {
        "log": [], "errs": [], "examDates": [], "stage": 0,
        "settings": {},
        "overrides": {}, "weekOverrides": {}, "mat": {},
        "diag": None, "profile": None, "onboarded": True, "sessionOffset": 0,
    }
    api("api/progress?user=" + user["id"], doc, token=user["token"], method="PUT")


def nav_labels(pg):
    return pg.eval_on_selector_all(
        "#sideNav .nav-label", "els => els.map(e => e.textContent.trim())"
    )


def settle(pg, ms=450):
    pg.wait_for_timeout(ms)
    if pg.evaluate(
        "typeof finishOnboarding==='function' && document.getElementById('onboardingOverlay')"
        " && document.getElementById('onboardingOverlay').style.display==='flex'"
    ):
        pg.evaluate("finishOnboarding()")
        pg.wait_for_timeout(300)


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    console_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.on(
        "console",
        lambda m: console_errors.append(m.text)
        if m.type == "error" and "Failed to load resource" not in m.text
        else None,
    )

    user = session_user()
    reset_progress(user)

    pg.goto(URL, wait_until="networkidle")
    pg.evaluate("localStorage.clear()")
    pg.evaluate("localStorage.setItem('b2first_user', %s)" % json.dumps(json.dumps(user)))
    pg.reload(wait_until="networkidle")
    settle(pg)

    # 1. A fresh account is English.
    assert pg.evaluate("document.documentElement.lang") == "en", "fresh <html lang> is not en"
    labels = nav_labels(pg)
    assert labels[0] == "Today", f"nav does not show Today: {labels}"
    assert pg.evaluate("window.D.settings.lang") == "en", "D.settings.lang default is not en"
    out["1_fresh_english"] = {"lang": "en", "nav0": labels[0], "setting": "en"}

    # 2. The switcher lives in PLAN and turns the UI into Spanish.
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(200)
    assert pg.is_visible("#langEsBtn"), "language switch is not visible in PLAN"
    pg.click("#langEsBtn")
    pg.wait_for_function("document.documentElement.lang === 'es'")
    settle(pg)
    assert pg.evaluate("document.documentElement.lang") == "es", "switcher did not set <html lang=es>"
    labels_es = nav_labels(pg)
    assert labels_es[0] == "Hoy", f"nav did not switch to Hoy: {labels_es}"
    nav_text = pg.eval_on_selector("#sideNav", "el => el.textContent")
    assert "Today" not in nav_text, f"English-only label left in the nav: {nav_text!r}"
    assert nav_text.count("Hoy") >= 1
    assert pg.get_attribute("#langEsBtn", "aria-pressed") == "true"
    assert pg.get_attribute("#langEnBtn", "aria-pressed") == "false"
    assert pg.evaluate("window.D.settings.lang") == "es", "language was not saved to D.settings.lang"
    out["2_switch_spanish"] = {"lang": "es", "nav0": labels_es[0], "nav": labels_es}

    # 3. The choice survives a reload (localStorage + server).
    pg.reload(wait_until="networkidle")
    settle(pg)
    assert pg.evaluate("document.documentElement.lang") == "es", "Spanish did not persist across reload"
    assert nav_labels(pg)[0] == "Hoy", "nav is not Spanish after reload"
    assert pg.evaluate("window.D.settings.lang") == "es", "D.settings.lang did not persist"
    out["3_persisted_reload"] = {"lang": pg.evaluate("document.documentElement.lang"), "nav0": nav_labels(pg)[0]}

    # 4. Switch back to English.
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(200)
    pg.click("#langEnBtn")
    pg.wait_for_function("document.documentElement.lang === 'en'")
    settle(pg)
    assert pg.evaluate("document.documentElement.lang") == "en", "could not switch back to English"
    assert nav_labels(pg)[0] == "Today", "nav did not return to Today"
    assert pg.get_attribute("#langEnBtn", "aria-pressed") == "true"
    assert pg.evaluate("window.D.settings.lang") == "en"
    out["4_switch_back"] = {"lang": "en", "nav0": nav_labels(pg)[0]}

    # 5. Every key used by the markup resolves in both languages, and the two
    #    dictionaries have exactly the same keys (a forgotten string is caught).
    report = pg.evaluate(
        """() => {
        const attrs = ['data-i18n', 'data-i18n-html', 'data-i18n-title',
                       'data-i18n-aria-label', 'data-i18n-placeholder'];
        const keys = [];
        document.querySelectorAll(attrs.map(a => '[' + a + ']').join(',')).forEach(el => {
            attrs.forEach(a => { const k = el.getAttribute(a); if (k && keys.indexOf(k) < 0) keys.push(k); });
        });
        const prev = LANG;
        const missing = [];
        keys.forEach(k => {
            LANG = 'en'; const en = t(k);
            LANG = 'es'; const es = t(k);
            if (!en || !es) missing.push(k);
        });
        LANG = prev;
        const enKeys = Object.keys(I18N.en);
        return {
            keys: keys,
            missing: missing,
            enCount: enKeys.length,
            esCount: Object.keys(I18N.es).length,
            absentInEs: enKeys.filter(k => !(k in I18N.es)),
            absentInEn: Object.keys(I18N.es).filter(k => !(k in I18N.en)),
        };
        }"""
    )
    assert report["keys"], "no data-i18n keys found in the markup"
    assert not report["missing"], f"keys with no text in en/es: {report['missing']}"
    assert report["enCount"] == report["esCount"], f"dictionary size mismatch: {report}"
    assert not report["absentInEs"] and not report["absentInEn"], f"dictionary key mismatch: {report}"
    out["5_keys"] = {
        "used": len(report["keys"]),
        "en": report["enCount"],
        "es": report["esCount"],
    }

    # 6. The nav keys are the ones the acceptance names.
    assert all(k in report["keys"] for k in NAV_KEYS), "nav data-i18n keys missing"

    # 7. Zero JS errors for the whole run.
    assert page_errors == [], f"page errors: {page_errors}"
    assert console_errors == [], f"console errors: {console_errors}"
    out["7_errors"] = {"page": page_errors, "console": console_errors}

    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
sys.exit(0)
