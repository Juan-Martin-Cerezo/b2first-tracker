#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stripe billing (phase 33): hosted Checkout, signed webhooks, subscriptions.

Design rules (see PLAN-HACKATHON-IA.md / phase 33):

* **Stdlib only.** Stripe is called with ``urllib.request`` and JSON. There is
  no SDK and no card data anywhere near this server: the browser is sent to a
  provider-hosted page, so the PCI scope stays at SAQ A. The only identifiers
  that ever reach the disk are ``cus_…``, ``sub_…`` and ``cs_…``.
* **Callbacks are signed.** :func:`verify_webhook` recomputes
  ``HMAC-SHA256(secret, "{t}.{raw_body}")`` and compares it with
  ``hmac.compare_digest`` inside a ±300 s window. An unsigned, tampered or
  stale request is rejected before the event is looked at.
* **Idempotent.** ``data/billing/events.json`` keeps the last 1000 processed
  event ids, so a provider retry cannot grant two months or double-count usage.
* **Clean degradation.** With no keys (or ``B2_BILLING_MODE=off``) the HTTP
  layer answers ``503 billing_not_configured`` and the rest of the app works.

Every path is resolved per call through :func:`store.data_dir`, so tests can
swap ``DATA_DIR`` after import. This module knows nothing about HTTP responses:
it returns plain dicts and lets ``server.py`` map errors.
"""
import calendar
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request

import store

__all__ = [
    "PRICE_USD_MONTH",
    "GRACE_DAYS",
    "WEBHOOK_TOLERANCE",
    "WEBHOOK_MAX_BYTES",
    "EVENTS_KEEP",
    "BillingError",
    "mode",
    "config",
    "checkout_ready",
    "portal_ready",
    "webhook_ready",
    "create_checkout_session",
    "create_portal_session",
    "verify_webhook",
    "plan_from_subscription",
    "active_plan",
    "get_sub",
    "put_sub",
    "find_by_customer",
    "find_by_subscription",
    "forget_user",
    "event_seen",
    "record_event",
    "iso",
    "epoch",
]

PRICE_USD_MONTH = 5
GRACE_DAYS = 3
WEBHOOK_TOLERANCE = 300          # seconds of clock skew accepted
WEBHOOK_MAX_BYTES = 64 * 1024    # reject larger bodies before reading them
EVENTS_KEEP = 1000               # processed ids kept for idempotency
API_BASE_DEFAULT = "https://api.stripe.com"
PUBLIC_URL_DEFAULT = "https://firsttracker.app"
PROVIDER_MAX_RESPONSE = 256 * 1024

_LOCK = threading.RLock()
_DAY = 24 * 3600


class BillingError(Exception):
    """The provider could not be reached or answered with something unusable."""


# ---------------------------------------------------------------------------
# Time helpers (ISO strings, UTC, fixed width: lexical comparison == time).
# ---------------------------------------------------------------------------
def iso(ts):
    """Format an epoch timestamp as 2026-10-30T12:00:00Z."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def epoch(value):
    """Epoch seconds for an ISO string or a Stripe integer; None if unusable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        try:
            return float(value)
        except ValueError:
            pass
        try:
            return float(calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")))
        except (TypeError, ValueError):
            return None
    return None


def _now(now=None):
    return time.time() if now is None else float(now)


# ---------------------------------------------------------------------------
# Configuration (read per call: tests inject env before the server starts).
# ---------------------------------------------------------------------------
def _env(name):
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) else ""


def mode():
    """``live``, ``test`` or ``off`` (the default; unknown values mean off)."""
    value = _env("B2_BILLING_MODE").lower()
    return value if value in ("live", "test") else "off"


def config():
    return {
        "mode": mode(),
        "secret_key": _env("B2_STRIPE_SECRET_KEY"),
        "price_id": _env("B2_STRIPE_PRICE_ID"),
        "webhook_secret": _env("B2_STRIPE_WEBHOOK_SECRET"),
        "public_url": (_env("B2_PUBLIC_URL") or PUBLIC_URL_DEFAULT).rstrip("/"),
        "api_base": (_env("B2_STRIPE_API_BASE") or API_BASE_DEFAULT).rstrip("/"),
    }


def checkout_ready():
    """True when a Checkout session can be created right now."""
    cfg = config()
    return (cfg["mode"] != "off" and bool(cfg["secret_key"])
            and bool(cfg["price_id"]) and bool(cfg["public_url"]))


def portal_ready():
    """True when the customer portal can be reached right now."""
    cfg = config()
    return cfg["mode"] != "off" and bool(cfg["secret_key"]) and bool(cfg["public_url"])


def webhook_ready():
    """True when a signed callback can be verified right now."""
    cfg = config()
    return cfg["mode"] != "off" and bool(cfg["webhook_secret"])


# ---------------------------------------------------------------------------
# Private JSON files: data/billing/subs.json and data/billing/events.json.
# ---------------------------------------------------------------------------
def _data_dir():
    return store.data_dir()


def _billing_dir():
    return os.path.join(_data_dir(), "billing")


def _subs_path():
    return os.path.join(_billing_dir(), "subs.json")


def _events_path():
    return os.path.join(_billing_dir(), "events.json")


def _ensure_dir():
    path = _billing_dir()
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _read(path, default):
    data = store.read_json_private(path, default)
    return data if isinstance(data, type(default)) else default


def _write(path, data):
    _ensure_dir()
    store.write_json_private(path, data)


def _subs():
    return _read(_subs_path(), {})


def get_sub(uid):
    """Stored subscription row for uid, or {} when there is none."""
    row = _subs().get(uid)
    return dict(row) if isinstance(row, dict) else {}


def put_sub(uid, row):
    """Replace the subscription row for uid and return it (atomic, 0600)."""
    if not uid:
        raise ValueError("a subscription needs a user id")
    clean = {k: v for k, v in row.items() if v is not None}
    with _LOCK:
        rows = _subs()
        rows[uid] = clean
        _write(_subs_path(), rows)
        return clean


def _find(field, value):
    """(uid, row) of the first subscription whose `field` equals `value`."""
    if not value:
        return None, {}
    for uid, row in _subs().items():
        if isinstance(row, dict) and row.get(field) == value:
            return uid, dict(row)
    return None, {}


def find_by_customer(customer_id):
    return _find("customer_id", customer_id)


def find_by_subscription(subscription_id):
    return _find("subscription_id", subscription_id)


def forget_user(uid):
    """Drop the subscription row and detach event ids that mention the account."""
    with _LOCK:
        rows = _subs()
        if rows.pop(uid, None) is not None:
            _write(_subs_path(), rows)


# ---------------------------------------------------------------------------
# Idempotency ledger: a plain JSON array of event ids, newest last.
# ---------------------------------------------------------------------------
def _events():
    data = _read(_events_path(), [])
    return [x for x in data if isinstance(x, str)]


def event_seen(event_id):
    """True when this provider event id was already applied."""
    if not isinstance(event_id, str) or not event_id:
        return False
    return event_id in _events()


def record_event(event_id):
    """Remember a processed event id (last EVENTS_KEEP kept, 0600)."""
    if not isinstance(event_id, str) or not event_id:
        return
    with _LOCK:
        ids = _events()
        if event_id in ids:
            return
        ids.append(event_id)
        _write(_events_path(), ids[-EVENTS_KEEP:])


# ---------------------------------------------------------------------------
# Provider calls. Everything network goes through _post so a stub can play
# Stripe (B2_STRIPE_API_BASE) exactly like tests/test_speaking_pa.py does.
# ---------------------------------------------------------------------------
def _post(path, payload, idempotency_key=None):
    """POST JSON to the provider and return the decoded response object."""
    cfg = config()
    if not cfg["secret_key"]:
        raise BillingError("billing_not_configured")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        cfg["api_base"] + path, data=body, method="POST",
        headers={
            "Authorization": "Bearer " + cfg["secret_key"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    if idempotency_key:
        req.add_header("Idempotency-Key", idempotency_key)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(PROVIDER_MAX_RESPONSE)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise BillingError("provider_unreachable") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BillingError("provider_bad_response") from exc
    if not isinstance(data, dict):
        raise BillingError("provider_bad_response")
    return data


def create_checkout_session(user, price_id, success_url, cancel_url,
                            idempotency_key=None):
    """Create a hosted Checkout session for a subscription to `price_id`.

    No ``customer_email``: this server stores no email. The account is carried
    by ``client_reference_id``, which the webhook uses to find the user.
    """
    payload = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "client_reference_id": user,
        # Also stamped on the subscription so `customer.subscription.*` events
        # (which do not carry client_reference_id) can still find the account.
        "subscription_data": {"metadata": {"user_id": user}},
        "success_url": success_url,
        "cancel_url": cancel_url,
        "allow_promotion_codes": True,
    }
    return _post("/v1/checkout/sessions", payload, idempotency_key)


def create_portal_session(customer_id, return_url):
    """Create a hosted customer-portal session (cancel, card, invoices)."""
    return _post("/v1/billing_portal/sessions",
                 {"customer": customer_id, "return_url": return_url})


# ---------------------------------------------------------------------------
# Signed webhooks.
# ---------------------------------------------------------------------------
def verify_webhook(raw_body, header, secret, now=None):
    """Return ``(ok, event)`` for a ``Stripe-Signature: t=…,v1=…`` header.

    The MAC is HMAC-SHA256 over ``"{t}.{raw_body}"``. The timestamp must be
    within ±WEBHOOK_TOLERANCE seconds of `now`; comparison uses
    ``hmac.compare_digest``. Any malformed input is a plain ``(False, None)``.
    """
    if not isinstance(secret, str) or not secret:
        return False, None
    if not isinstance(header, str) or not header.strip():
        return False, None
    if isinstance(raw_body, str):
        raw = raw_body.encode("utf-8")
    elif isinstance(raw_body, (bytes, bytearray)):
        raw = bytes(raw_body)
    else:
        return False, None

    timestamp = None
    signatures = []
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if key == "t" and value.isdigit():
            timestamp = int(value)
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        return False, None
    if abs(_now(now) - timestamp) > WEBHOOK_TOLERANCE:
        return False, None

    signed = str(timestamp).encode("ascii") + b"." + raw
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        return False, None

    try:
        event = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False, None
    if not isinstance(event, dict):
        return False, None
    return True, event


# ---------------------------------------------------------------------------
# Subscription -> plan.
# ---------------------------------------------------------------------------
def plan_from_subscription(status, current_period_end, now=None):
    """``pro`` or ``free`` for a subscription status and its period end.

    ``active``/``trialing`` keep pro until the paid period ends; ``past_due``
    stays pro while the grace window is open (the resolver checks
    ``grace_until``); everything else is free.
    """
    ts = _now(now)
    end = epoch(current_period_end)
    if status in ("active", "trialing"):
        return "pro" if (end is None or end > ts) else "free"
    if status == "past_due":
        return "pro"
    return "free"


def active_plan(uid, now=None):
    """The subscription-derived plan for uid, or None when nothing is active.

    Called by ``plans.effective_plan`` *after* the activation-code check and
    always evaluated against the clock, so a lapsed subscription demotes to
    free on the next request without a cron job.
    """
    if not uid:
        return None
    row = get_sub(uid)
    if not row:
        return None
    ts = _now(now)
    status = row.get("status")
    end = epoch(row.get("current_period_end"))
    grace = epoch(row.get("grace_until"))
    plan = plan_from_subscription(status, end, ts)
    if plan == "pro" and status in ("active", "trialing"):
        return {
            "plan": "pro",
            "since": row.get("since"),
            "until": row.get("current_period_end"),
            "source": "stripe",
            "grace_until": None,
            "status": status,
        }
    if status == "past_due" and grace is not None and grace > ts:
        return {
            "plan": "pro",
            "since": row.get("since"),
            "until": iso(grace),
            "source": "stripe_grace",
            "grace_until": iso(grace),
            "status": status,
        }
    return None
