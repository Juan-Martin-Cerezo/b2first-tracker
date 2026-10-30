"""Helpers for the tests: start a session before interacting with the app.

The frontend requires a session. Tests must NOT depend on the owner's real
password (it is a human secret and it gets rotated), so they use a dedicated
account that the helper registers on first use and reuses afterwards.

Override with B2_TEST_USER / B2_TEST_PASS when running against another host.
"""
import os

OWNER_NAME = os.environ.get("B2_TEST_USER", "test-runner")
OWNER_PASS = os.environ.get("B2_TEST_PASS", "test-runner-pass-9")


def _api(url, path, payload, token=None):
    import json
    import urllib.request

    req = urllib.request.Request(
        url + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def _ensure_account(url, name, password):
    """Register the account if it does not exist yet (ignore 409)."""
    import urllib.error

    try:
        _api(url, "api/register", {"name": name, "password": password})
    except urllib.error.HTTPError:
        return  # already registered (409) or registration closed: try login
    except Exception:
        return


def login_user(pg, url, name, password, register=True):
    """Log an arbitrary account in via the API and set the session locally.

    Returns the user record (id, name, color, token) so suites can seed their
    own progress document without borrowing the shared test account.
    """
    import json

    if register:
        _ensure_account(url, name, password)
    u = _api(url, "api/login", {"name": name, "password": password})
    pg.evaluate(
        "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(u))
    )
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    # Close the first-run onboarding if it appears (user without D.onboarded)
    if pg.evaluate("typeof finishOnboarding==='function' && document.getElementById('onboardingOverlay') && document.getElementById('onboardingOverlay').style.display==='flex'"):
        pg.evaluate("finishOnboarding()")
        pg.wait_for_timeout(300)
    return u


def login_owner(pg, url):
    """Log in as the shared throwaway test account."""
    return login_user(pg, url, OWNER_NAME, OWNER_PASS)
