"""Phase 33 acceptance: Stripe Checkout + signed, idempotent webhooks.

Own server process on a temporary DATA_DIR and a local stub that plays Stripe,
so the whole path (auth -> checkout -> provider -> signed webhook -> plan) runs
without network. The webhook path is exercised with **real HMAC signatures**:
every accepted callback carries a `Stripe-Signature` computed here over the
exact raw body, and the rejected ones fail the same check (bad secret, missing
header, stale timestamp).

    cd tests && uv run --with httpx python test_billing.py
"""
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402

USER = "billing-runner"
PASS = "billing-runner-pass-9"

# Deliberately live-looking so the "nothing in data/" check is meaningful.
SECRET_KEY = "sk_live_thisMustNeverReachTheDisk_7f31"
PRICE_ID = "price_stub_5usd"
WEBHOOK_SECRET = "whsec_stub_secret_for_tests"
PUBLIC_URL = "https://firsttracker.app"

STUB = {"calls": 0, "path": "", "payload": None, "idempotency": ""}


class StubStripe(BaseHTTPRequestHandler):
    """Plays the two Stripe endpoints the server calls (JSON, no card data)."""

    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        STUB["calls"] += 1
        STUB["path"] = self.path
        STUB["idempotency"] = self.headers.get("Idempotency-Key", "")
        try:
            STUB["payload"] = json.loads(raw.decode("utf-8"))
        except ValueError:
            STUB["payload"] = None
        if self.path.startswith("/v1/checkout/sessions"):
            body = json.dumps({"id": "cs_stub_1",
                               "url": "https://checkout.stripe.test/c/cs_stub_1"}).encode()
        else:
            body = json.dumps({"id": "bps_stub_1",
                               "url": "https://billing.stripe.test/p/bps_stub_1"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def wait_health(base, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def request(base, path, body=None, token=None, headers=None, method="POST"):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def raw_post(base, path, raw, headers):
    req = urllib.request.Request(base + path, data=raw, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def sign(payload, secret=WEBHOOK_SECRET, timestamp=None):
    """The real header Stripe sends: t=<unix>,v1=<hex hmac over t.body>."""
    ts = int(time.time()) if timestamp is None else int(timestamp)
    mac = hmac.new(secret.encode("utf-8"), str(ts).encode() + b"." + payload,
                   hashlib.sha256).hexdigest()
    return "t=%d,v1=%s" % (ts, mac)


def event_body(event_id, kind, obj):
    return json.dumps({"id": event_id, "type": kind,
                       "data": {"object": obj}}, separators=(",", ":")).encode("utf-8")


def webhook(base, raw, header=None):
    headers = {"Content-Type": "application/json"}
    if header is not None:
        headers["Stripe-Signature"] = header
    return raw_post(base, "/api/billing/webhook", raw, headers)


def start_server(data_dir, extra_env, port):
    env = dict(os.environ)
    env.update({
        "DATA_DIR": data_dir,
        "PORT": str(port),
        "B2_HOST": "127.0.0.1",
        "B2_DEMO": "0",
        "B2_REGISTER": "open",
    })
    env.update(extra_env)
    out_path = os.path.join(data_dir, "..", os.path.basename(data_dir) + "-%d.log" % port)
    out = open(out_path, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, os.path.join(REPO, "server.py")],
                            cwd=REPO, env=env, stdout=out, stderr=subprocess.STDOUT)
    return proc, out, out_path


def stop_server(proc, handle):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    handle.close()


def read_tree(root):
    chunks = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            try:
                with open(os.path.join(dirpath, name), "rb") as f:
                    chunks.append(f.read())
            except OSError:
                pass
    return b"\n".join(chunks)


FORBIDDEN_KEYS = {"card", "number", "cvc", "exp", "cvv", "expiry"}


def forbidden_key_paths(node, path=()):
    hits = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_KEYS:
                hits.append(path + (key,))
            hits.extend(forbidden_key_paths(value, path + (key,)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            hits.extend(forbidden_key_paths(value, path + (index,)))
    return hits


out = {}
stub = ThreadingHTTPServer(("127.0.0.1", 0), StubStripe)
STUB_URL = "http://127.0.0.1:%d" % stub.server_address[1]
threading.Thread(target=stub.serve_forever, daemon=True).start()

DATA_DIR = tempfile.mkdtemp(prefix="b2billing-")
BILLING_DIR = os.path.join(DATA_DIR, "billing")
SUBS = os.path.join(BILLING_DIR, "subs.json")
EVENTS = os.path.join(BILLING_DIR, "events.json")

try:
    # ------------------------------------------------------------------
    # A. Billing off (the default): checkout is 503, the rest keeps working.
    # ------------------------------------------------------------------
    PORT_A = free_port()
    BASE_A = "http://127.0.0.1:%d" % PORT_A
    proc_a, log_a, log_a_path = start_server(DATA_DIR, {"B2_BILLING_MODE": "off"}, PORT_A)
    try:
        assert wait_health(BASE_A), "off-mode server did not start"
        helpers._ensure_account(BASE_A + "/", USER, PASS)
        login = helpers._api(BASE_A + "/", "api/login", {"name": USER, "password": PASS})
        UID, TOKEN = login["id"], login["token"]

        st, body, _ = request(BASE_A, "/api/billing/checkout", None, token=TOKEN)
        assert st == 503, "checkout was not refused in off mode: %s %s" % (st, body)
        assert json.loads(body).get("error") == "billing_not_configured", body

        st, body, _ = request(BASE_A, "/api/plan", token=TOKEN, method="GET")
        assert st == 200 and json.loads(body).get("plan") == "free", (st, body)

        st, body, _ = request(BASE_A, "/api/billing/status", token=TOKEN, method="GET")
        assert st == 200 and json.loads(body).get("plan") == "free", (st, body)

        probe = event_body("evt_off", "customer.subscription.updated", {})
        st, body = webhook(BASE_A, probe, sign(probe))
        assert st == 503, "the webhook ran without keys: %s %s" % (st, body)
        out["1_off_mode"] = {"checkout": 503, "plan": "free", "webhook": 503}
    finally:
        stop_server(proc_a, log_a)

    # ------------------------------------------------------------------
    # B. Billing configured against the stub.
    # ------------------------------------------------------------------
    PORT = free_port()
    BASE = "http://127.0.0.1:%d" % PORT
    env_b = {
        "B2_BILLING_MODE": "test",
        "B2_STRIPE_SECRET_KEY": SECRET_KEY,
        "B2_STRIPE_PRICE_ID": PRICE_ID,
        "B2_STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "B2_PUBLIC_URL": PUBLIC_URL,
        "B2_STRIPE_API_BASE": STUB_URL,
    }
    proc_b, log_b, log_b_path = start_server(DATA_DIR, env_b, PORT)
    try:
        assert wait_health(BASE), "billing server did not start"
        login = helpers._api(BASE + "/", "api/login", {"name": USER, "password": PASS})
        UID, TOKEN = login["id"], login["token"]

        def plan():
            st, body, _ = request(BASE, "/api/plan", token=TOKEN, method="GET")
            assert st == 200, "GET /api/plan: %s %s" % (st, body)
            return json.loads(body)

        def status():
            st, body, _ = request(BASE, "/api/billing/status", token=TOKEN, method="GET")
            assert st == 200, "GET /api/billing/status: %s %s" % (st, body)
            return json.loads(body)

        # 2. Checkout reaches the provider with the right account and price.
        st, body, _ = request(BASE, "/api/billing/checkout", None, token=TOKEN)
        assert st == 200, "checkout failed: %s %s" % (st, body)
        checkout = json.loads(body)
        assert "cs_stub_1" in checkout.get("url", ""), checkout
        assert STUB["path"] == "/v1/checkout/sessions", STUB["path"]
        payload = STUB["payload"] or {}
        assert payload.get("client_reference_id") == UID, payload
        assert payload.get("mode") == "subscription", payload
        assert payload.get("line_items") == [{"price": PRICE_ID, "quantity": 1}], payload
        assert "customer_email" not in payload, payload
        assert payload.get("subscription_data", {}).get("metadata", {}).get("user_id") == UID
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert STUB["idempotency"] == "%s-%s" % (UID, today), STUB["idempotency"]
        out["2_checkout"] = {"url": checkout["url"], "idempotency": STUB["idempotency"]}

        # 3. A bad signature, a missing header and a stale timestamp are 400
        #    and leave the plan alone (still free).
        good = event_body("evt_valid_1", "customer.subscription.updated", {
            "id": "sub_stub_1", "customer": "cus_stub_1", "status": "active",
            "current_period_end": int(time.time()) + 30 * 86400,
            "metadata": {"user_id": UID},
        })
        st, body = webhook(BASE, good, sign(good, secret="whsec_wrong_secret"))
        assert st == 400, "bad signature accepted: %s %s" % (st, body)
        assert "evt_valid_1" not in body and "cus_stub_1" not in body, "body echoed"
        st, body = webhook(BASE, good, None)
        assert st == 400, "unsigned webhook accepted: %s %s" % (st, body)
        stale = int(time.time()) - 600
        st, body = webhook(BASE, good, sign(good, timestamp=stale))
        assert st == 400, "stale signature accepted: %s %s" % (st, body)
        assert plan()["plan"] == "free", "a rejected webhook changed the plan"
        out["3_signature_rejected"] = {"bad": 400, "missing": 400, "stale": 400}

        # 4. Valid signature: subscription.updated grants pro and the period end.
        period_end = int(time.time()) + 30 * 86400
        good = event_body("evt_valid_1", "customer.subscription.updated", {
            "id": "sub_stub_1", "customer": "cus_stub_1", "status": "active",
            "current_period_end": period_end,
            "metadata": {"user_id": UID},
        })
        st, body = webhook(BASE, good, sign(good))
        assert st == 200, "valid webhook refused: %s %s" % (st, body)
        assert json.loads(body) == {"ok": True}, body
        current = plan()
        assert current["plan"] == "pro", current
        assert current["until"] == time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime(period_end)), current
        assert current["source"] == "stripe", current
        out["4_subscription_updated"] = {"plan": current["plan"], "until": current["until"]}

        # 5. Replay of the same event id: 200, plan unchanged, one ledger entry.
        before = plan()
        st, body = webhook(BASE, good, sign(good))
        assert st == 200, "replay was not acknowledged: %s %s" % (st, body)
        after = plan()
        assert after["until"] == before["until"] and after["plan"] == before["plan"], \
            "replay moved the plan"
        with open(EVENTS, "r", encoding="utf-8") as f:
            ids = json.load(f)
        assert ids == ["evt_valid_1"], "events ledger is not idempotent: %r" % (ids,)
        out["5_replay_idempotent"] = {"ids": ids}

        # 6. customer.subscription.deleted demotes to free immediately.
        deleted = event_body("evt_deleted_2", "customer.subscription.deleted", {
            "id": "sub_stub_1", "customer": "cus_stub_1", "status": "canceled",
            "current_period_end": period_end,
            "metadata": {"user_id": UID},
        })
        st, body = webhook(BASE, deleted, sign(deleted))
        assert st == 200, "deleted event refused: %s %s" % (st, body)
        assert plan()["plan"] == "free", "cancellation did not demote to free"
        out["6_deleted_free"] = plan()["plan"]

        # 7. invoice.payment_failed keeps pro with a 3-day grace window.
        reactivate = event_body("evt_valid_3", "customer.subscription.updated", {
            "id": "sub_stub_1", "customer": "cus_stub_1", "status": "active",
            "current_period_end": int(time.time()) + 30 * 86400,
            "metadata": {"user_id": UID},
        })
        st, body = webhook(BASE, reactivate, sign(reactivate))
        assert st == 200 and plan()["plan"] == "pro", (st, body)

        failed = event_body("evt_failed_4", "invoice.payment_failed", {
            "customer": "cus_stub_1", "subscription": "sub_stub_1",
            "amount_due": 500, "status": "open",
            "metadata": {"user_id": UID},
        })
        st, body = webhook(BASE, failed, sign(failed))
        assert st == 200, "payment_failed refused: %s %s" % (st, body)
        current = plan()
        assert current["plan"] == "pro", "grace period lost pro immediately: %s" % current
        st_obj = status()
        assert st_obj["status"] == "past_due", st_obj
        assert st_obj["grace_until"], "grace_until was not set: %s" % st_obj
        with open(SUBS, "r", encoding="utf-8") as f:
            row = json.load(f)[UID]
        assert row["status"] == "past_due" and row.get("grace_until"), row
        assert "amount_due" not in json.dumps(row), "an amount was persisted: %s" % row
        out["7_payment_failed_grace"] = {"plan": current["plan"],
                                         "grace_until": row["grace_until"]}

        # 8. Clock past the grace -> free. The real resolver is asked with a
        #    future `now`; the file is then aged so the HTTP path agrees.
        import billing  # noqa: E402
        import plans  # noqa: E402
        import store  # noqa: E402

        store.DATA_DIR = DATA_DIR
        future = time.time() + (billing.GRACE_DAYS + 2) * 86400
        assert plans.effective_plan(UID, now=time.time())["plan"] == "pro", \
            "resolver dropped pro during grace"
        assert plans.effective_plan(UID, now=future)["plan"] == "free", \
            "resolver kept pro after grace"

        aged = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        row["grace_until"] = aged
        with open(SUBS, "w", encoding="utf-8") as f:
            json.dump({UID: row}, f)
        os.chmod(SUBS, 0o600)
        assert plan()["plan"] == "free", "HTTP plan ignored an expired grace window"
        out["8_grace_expires"] = "free"

        # 9. A body that carried card-like fields is not persisted or echoed.
        card_event = event_body("evt_card_5", "customer.subscription.updated", {
            "id": "sub_stub_1", "customer": "cus_stub_1", "status": "active",
            "current_period_end": int(time.time()) + 30 * 86400,
            "metadata": {"user_id": UID},
            "card": {"number": "4242424242424242", "cvc": "123", "exp": "12/30"},
        })
        st, body = webhook(BASE, card_event, sign(card_event))
        assert st == 200, (st, body)
        assert "4242424242424242" not in body and "card" not in body, "card data echoed"

        on_disk = read_tree(BILLING_DIR)
        assert b"4242424242424242" not in on_disk, "card number reached data/"
        for name in os.listdir(BILLING_DIR):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(BILLING_DIR, name), "r", encoding="utf-8") as f:
                hits = forbidden_key_paths(json.load(f))
            assert not hits, "forbidden field(s) in %s: %s" % (name, hits)

        # 10. No live key anywhere under data/ (nor in the server log).
        everything = read_tree(DATA_DIR)
        assert b"sk_live" not in everything, "a live secret reached data/"
        log_text = open(log_b_path, "r", encoding="utf-8", errors="replace").read()
        assert "sk_live" not in log_text, "a live secret reached the server log"
        out["9_no_card_data"] = {"billing_files": sorted(os.listdir(BILLING_DIR))}

        # 11. status exposes the portal only once a customer exists.
        st_obj = status()
        assert st_obj["portal_available"] is True, st_obj
        assert st_obj["billing_mode"] == "test", st_obj
        out["10_status"] = {"portal_available": True, "status": st_obj["status"]}
    finally:
        stop_server(proc_b, log_b)

    print(json.dumps(out, ensure_ascii=False, indent=1))
finally:
    stub.shutdown()
