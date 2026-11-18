"""No purchase, no redemption: no view sells anything and no route accepts it.

Two guarantees:

1. The main views render none of the purchase words: "upgrade", "checkout",
   "redeem", "activation code" or "buy". This covers the landing page, the
   tracker views, Settings and the Account panel.
2. Every route that used to sell or redeem is gone: it answers 404, never 200
   and never a 500.

Run: cd tests && uv run --with playwright --with httpx python test_no_purchase.py
"""
import json

import httpx
from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

FORBIDDEN = ("upgrade", "checkout", "redeem", "activation code", "buy")

# Routes removed with the purchase flow. Each one existed in a previous phase
# and must now be indistinguishable from any other unknown path.
REMOVED = [
    ("GET", "/api/billing/status"),
    ("POST", "/api/billing/checkout"),
    ("POST", "/api/billing/portal"),
    ("POST", "/api/billing/webhook"),
    ("POST", "/api/plan/redeem"),
    ("GET", "/api/license/status"),
]


def scan(label, text):
    lowered = text.lower()
    hits = [word for word in FORBIDDEN if word in lowered]
    assert not hits, f"{label} renders purchase copy {hits}: {lowered[:240]!r}"
    return {"label": label, "chars": len(text), "hits": hits}


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))

    # 1. The public page.
    pg.goto(URL, wait_until="networkidle")
    OUT["landing"] = scan("landing", pg.evaluate("document.body.innerText"))

    # 2. Every main view of the tracker.
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    views = ["hoy", "practice", "resources", "exam", "prog", "plan", "err", "ia", "diag"]
    seen = {}
    for view in views:
        pg.evaluate(f"showView('{view}')")
        pg.wait_for_timeout(150)
        seen[view] = scan("view:" + view, pg.evaluate("document.body.innerText"))
    OUT["views"] = seen

    # 3. Settings and Account, where the old upsell lived.
    pg.evaluate("showView('plan')")
    pg.click("#userChip")
    pg.wait_for_timeout(200)
    pg.click("#acctSettingsBtn")
    pg.wait_for_timeout(200)
    OUT["settings"] = scan("settings", pg.evaluate("document.querySelector('#settingsModal').innerText"))
    pg.click("[data-action='closeSettingsModal']")
    pg.wait_for_timeout(150)
    pg.click("#userChip")
    pg.wait_for_timeout(200)
    pg.click("#acctProfileBtn")
    pg.wait_for_timeout(250)
    OUT["account"] = scan("account", pg.evaluate("document.querySelector('#userModal').innerText"))

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["page_errors"] = page_errors
    browser.close()

# 4. Every removed route is a 404, with a session and without one.
with httpx.Client(base_url=URL.rstrip("/"), timeout=10.0) as client:
    login = client.post("/api/login", json={"name": "Owner", "password": "b2first"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    headers = {"Authorization": "Bearer " + token}
    statuses = {}
    for method, path in REMOVED:
        for auth in (True, False):
            hdrs = headers if auth else {}
            kwargs = {"headers": hdrs}
            if method == "POST":
                kwargs["json"] = {}
            response = client.request(method, path, **kwargs)
            key = f"{method} {path} auth={auth}"
            statuses[key] = response.status_code
            assert response.status_code == 404, f"{key} answered {response.status_code}: {response.text[:120]}"
            assert response.status_code != 500
    OUT["removed_routes"] = statuses

print(json.dumps(OUT, ensure_ascii=False, indent=1))
