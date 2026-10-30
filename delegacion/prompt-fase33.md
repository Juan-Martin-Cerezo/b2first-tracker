# Phase 33 — Real subscriptions: Stripe checkout + signed webhooks

## Goal
`pro` must be bought with a card, renew automatically, and stop by itself when the
subscription is cancelled or the payment fails. No manual codes in the happy path
(the phase-31 codes stay as a fallback for comps and support).

Price: **US$5 / month**. Never touch card data on this server: the payment page is
hosted by the provider, so the PCI scope stays at SAQ A.

## Hard rules
1. Stdlib only. Talk to Stripe with `urllib.request` and JSON — no `stripe` SDK.
2. **Never store card data, never log a request body that could contain one.**
   The server only ever sees ids (`cus_…`, `sub_…`, `cs_…`).
3. Webhook signatures **must** be verified (`Stripe-Signature: t=…,v1=…`):
   HMAC-SHA256 over `"{t}.{raw_body}"` with `B2_STRIPE_WEBHOOK_SECRET`, tolerance
   ±300 s, compared with `hmac.compare_digest`. An unsigned or stale request → 400.
4. Webhooks are **idempotent**: the same `event.id` processed twice must not grant
   two months or double-count usage. Store processed ids (`data/billing/events.json`,
   last 1000, `0600`).
5. Everything degrades cleanly when the keys are absent: the endpoints return
   `503 {error:"billing_not_configured"}` and the rest of the app keeps working.

## Config (env, all optional until the account exists)
```
B2_STRIPE_SECRET_KEY=sk_live_...
B2_STRIPE_PRICE_ID=price_...
B2_STRIPE_WEBHOOK_SECRET=whsec_...
B2_PUBLIC_URL=https://firsttracker.app
```

## Server work
1. `billing.py` (new module, pure functions + one thin HTTP helper):
   - `create_checkout_session(user, price_id, success_url, cancel_url)`
   - `create_portal_session(customer_id, return_url)`
   - `verify_webhook(raw_body, header, secret, now)` → `(ok, event)`
   - `plan_from_subscription(status, current_period_end)` → `pro|free`
   Keep every network call behind a small `_post(path, payload)` so tests can stub
   it exactly like `tests/test_speaking_pa.py` stubs Azure.
2. Routes:
   - `POST /api/billing/checkout` (auth) → `{url}` for Stripe Checkout, with
     `client_reference_id = user_id`, `customer_email` NOT set (no email stored),
     and idempotency key = `user_id + day`.
   - `POST /api/billing/portal` (auth) → `{url}` to the customer portal (cancel,
     update card, invoices).
   - `POST /api/billing/webhook` (no auth, signature only) → handles
     `checkout.session.completed`, `customer.subscription.updated`,
     `customer.subscription.deleted`, `invoice.payment_failed`.
   - `GET /api/billing/status` (auth) → `{plan, renews_at, status, portal_available}`.
3. Persist `data/billing/subs.json` (`0600`):
   `{user_id: {customer_id, subscription_id, status, current_period_end, plan}}`.
   The plan resolver from phase 31 reads this **after** checking expiry by clock.
4. `invoice.payment_failed` → keep `pro` for a **3-day grace period**, then `free`.
   Log an audit event (`billing_payment_failed`) with the user id, no amounts.
5. Webhook body limit 64 KB; reject larger with 413 before reading it all.
6. Add `B2_BILLING_MODE=live|test|off`; `off` (default) → `503` on checkout.

## Client work
1. Plan card (phase 31) gets: **"Subscribe — US$5/month"** button → checkout, and
   "Manage subscription" when `portal_available`.
2. After returning from checkout, poll `GET /api/billing/status` up to 10 s and
   show the new plan without a reload.
3. Copy must be plain: "US$5 per month, cancel anytime from Manage subscription.
   Card handled by Stripe; we never see it."
4. Error states: cancelled checkout, webhook not configured, payment failed
   (show grace-period days left).

## Acceptance (write `tests/test_billing.py`, httpx + a local stub)
- With billing `off`: `/api/billing/checkout` → 503, `/api/plan` still works.
- Stub the provider: checkout returns a URL containing the session id; the request
  to the stub carries `client_reference_id` = user id and the configured price.
- Webhook with a **valid** signature → `subscription.updated` sets `pro` and
  `current_period_end`.
- Webhook with a bad signature, a missing header, and a timestamp 10 minutes old →
  `400` each, plan unchanged.
- **Replay**: the same event id twice → plan unchanged the second time, and
  `events.json` has one entry.
- `customer.subscription.deleted` → `free` immediately.
- `invoice.payment_failed` → still `pro`, `grace_until` set; simulate the clock
  past the grace → `free`.
- No card data: assert no field named `card`, `number`, `cvc`, `exp` is ever
  written to `data/`, and that the webhook handler never echoes the body.
- `grep -r "sk_live" data/` → nothing.

## Verify before finishing
```
cd tests && uv run --with httpx python test_billing.py        # exit 0
cd tests && uv run --with httpx python test_plans.py          # green
cd tests && uv run --with playwright python test_final.py     # green
```
Finish with `VERDICT: ok` only if all three pass, and state in the verdict that
the webhook path was exercised with real HMAC signatures (not by bypassing the
check).
