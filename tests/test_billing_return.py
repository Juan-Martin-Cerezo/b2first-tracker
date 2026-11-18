"""B3: Stripe returns must land on /app with the billing flag intact.

Part 1 asks the real server for Checkout and Billing Portal sessions against a
local Stripe stub, and checks the return URLs it sends to the provider.
Part 2 loads `/app?billing=success` in Chromium with `/api/billing/status`
intercepted, and checks `handleBillingReturn()` reacts to the parameter.

Stripe form encoding in billing.py is NOT verified here (no live keys):
it is reported as UNVERIFIED instead of faked.

    cd tests && uv run --with playwright --with httpx python test_billing_return.py
"""
import json
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from helpers import isolated_server, login_user

PUBLIC_URL = "https://firsttracker.example"
failed = []
STUB = {"path": "", "payload": None}


def check(name, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + name + ((" :: " + str(detail)) if not cond and detail else ""))
    if not cond:
        failed.append(name)


class StubStripe(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        STUB["path"] = self.path
        try:
            STUB["payload"] = json.loads(raw.decode("utf-8"))
        except ValueError:
            STUB["payload"] = None
        body = json.dumps({"id": "cs_stub", "url": "https://checkout.stripe.test/x"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def api(base, path, payload, token=None):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as r:
        body = r.read().decode()
    return json.loads(body) if body else None


def main():
    stub = ThreadingHTTPServer(("127.0.0.1", 0), StubStripe)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    stub_base = "http://127.0.0.1:%d" % stub.server_address[1]

    URL = isolated_server(extra_env={
        "B2_BILLING_MODE": "test",
        "B2_STRIPE_SECRET_KEY": "sk_test_stub",
        "B2_STRIPE_PRICE_ID": "price_stub",
        "B2_STRIPE_WEBHOOK_SECRET": "whsec_stub",
        "B2_STRIPE_API_BASE": stub_base,
        "B2_PUBLIC_URL": PUBLIC_URL,
    })

    import billing  # noqa: E402  (after the isolated data dir is chosen)

    user = api(URL, "/api/register", {"name": "billing-return", "password": "billing-return-pass-9"})
    token, uid = user["token"], user["id"]

    api(URL, "/api/billing/checkout", {}, token)
    check("checkout hits Stripe", STUB["path"].startswith("/v1/checkout/sessions"), STUB["path"])
    payload = STUB["payload"] or {}
    check("success_url lands on /app?billing=success",
          payload.get("success_url") == PUBLIC_URL + "/app?billing=success", payload.get("success_url"))
    check("cancel_url lands on /app?billing=cancel",
          payload.get("cancel_url") == PUBLIC_URL + "/app?billing=cancel", payload.get("cancel_url"))
    check("billing flag preserved (success)", "billing=success" in str(payload.get("success_url")))
    check("billing flag preserved (cancel)", "billing=cancel" in str(payload.get("cancel_url")))

    billing.put_sub(uid, {"customer_id": "cus_stub", "status": "active"})
    api(URL, "/api/billing/portal", {}, token)
    portal = STUB["payload"] or {}
    check("portal return_url lands on /app?billing=portal",
          portal.get("return_url") == PUBLIC_URL + "/app?billing=portal", portal.get("return_url"))

    stub.shutdown()

    # ---- Browser side: handleBillingReturn() reacts to the query ----------
    from playwright.sync_api import sync_playwright

    status_hits = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(URL + "/app", wait_until="networkidle")
        login_user(pg, URL + "/", "billing-return", "billing-return-pass-9")

        def on_status(route):
            status_hits.append(1)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({
                "plan": "pro", "source": "stripe", "renews_at": None,
                "status": "active", "grace_until": None,
                "portal_available": False, "billing_mode": "test",
            }))

        pg.route("**/api/billing/status", on_status)
        pg.goto(URL + "/app?billing=success", wait_until="networkidle")
        pg.wait_for_timeout(2500)

        check("handleBillingReturn polled /api/billing/status", len(status_hits) > 0, len(status_hits))
        check("query flag was cleaned after handling",
              pg.evaluate("location.search.indexOf('billing=')===-1"), pg.evaluate("location.search"))
        txt = pg.evaluate("(document.getElementById('planBillingStatus')||{}).textContent||''")
        check("billing feedback is surfaced", "Pro is active" in txt or "Pro activo" in txt, txt)
        browser.close()

    print()
    print("UNVERIFIED: billing.py form-encoding against Stripe's live API (no keys here).")
    if failed:
        print("VERDICT: FAIL", failed)
        sys.exit(1)
    print("VERDICT: ok")


if __name__ == "__main__":
    main()
