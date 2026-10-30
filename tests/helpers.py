"""Helpers for the tests: start a session before interacting with the app.

The frontend requires a session. Tests must NOT depend on the owner's real
password (it is a human secret and it gets rotated), so they use a dedicated
account that the helper registers on first use and reuses afterwards.

Override with B2_TEST_USER / B2_TEST_PASS when running against another host.
"""
import os

OWNER_NAME = os.environ.get("B2_TEST_USER", "test-runner")
OWNER_PASS = os.environ.get("B2_TEST_PASS", "test-runner-pass-9")


def _ensure_test_user(url):
    """Register the test account if it does not exist yet (ignore 409)."""
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        url + "api/register",
        data=json.dumps({"name": OWNER_NAME, "password": OWNER_PASS}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            r.read()
    except urllib.error.HTTPError:
        return  # already registered (409) or registration closed: try login
    except Exception:
        return


def login_owner(pg, url):
    """Log in as the owner via the API and set the session in localStorage."""
    import json
    import urllib.request

    _ensure_test_user(url)
    req = urllib.request.Request(
        url + "api/login",
        data=json.dumps({"name": OWNER_NAME, "password": OWNER_PASS}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        u = json.loads(r.read().decode())
    pg.evaluate(
        "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(u))
    )
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    # Close the first-run onboarding if it appears (user without D.onboarded)
    if pg.evaluate("typeof finishOnboarding==='function' && document.getElementById('onboardingOverlay') && document.getElementById('onboardingOverlay').style.display==='flex'"):
        pg.evaluate("finishOnboarding()")
        pg.wait_for_timeout(300)
