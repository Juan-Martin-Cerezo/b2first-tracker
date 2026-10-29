"""Helpers for the tests: log in as the owner before interacting with the app.

The frontend now requires a session (login overlay). The existing tests
verify the working app, so they log in as the 'owner' user (created by the
migration) with the default password.
"""

OWNER_NAME = "Owner"
OWNER_PASS = "b2first"


def login_owner(pg, url):
    """Log in as the owner via the API and set the session in localStorage."""
    import json
    import urllib.request

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
