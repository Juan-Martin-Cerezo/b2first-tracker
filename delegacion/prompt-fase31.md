# Phase 31 — Three plans: free (tight), bring-your-own-key, pro

## Goal
Turn the single "owner pays for everything" model into three plans the product can
actually enforce. No payment gateway yet: pro is unlocked by an **activation code**
the owner issues himself.

Owner instruction (verbatim): "Implementemos las 3, que sea gratis con un numero
muy limitado, que pueda poner su clave o pagar una suscripción y yo se lo puedo
proveer."

## The three plans
| Plan | How you get it | Writing | Speaking | Pronunciation |
| --- | --- | --- | --- | --- |
| `free` | default for every account | **3 / day** | **1 mock / week** (5 min) | preview only |
| `byo` | set your own key (phase 30) | unlimited to us (per-IP limits still apply) | unlimited, **their key** | if they configured Azure |
| `pro` | activation code **or subscription (phase 33)** | 60 / month | 6 mocks / month | full |

Cost ceiling per plan (measured inputs: ~US$0.25 per speaking mock, ~US$0.01 per
writing correction): free ≈ $0.10/month, pro ≈ $2.10/month against a US$5 price —
Stripe takes ~$0.45, so pro nets ~$2.45. **Do not raise the pro limits** without
recomputing that; 8 mocks/day at $0.25 would be US$60/month.

`free` is deliberately tight: it exists to let someone try the loop, not to run a
preparation for free.

## Data model
`data/plans.json` — `{user_id: {plan, since, until, source, code_hash}}`.
Add `plan` to the progress document as a **read-only mirror** so the UI can render
it; the server is the source of truth and recomputes on every request.

## Activation codes (`tools/issue_license.py`)
- Stdlib only, run by the owner: `python3 tools/issue_license.py pro 30` prints a
  code like `FT-PRO-3M-7K2QX-9WZ4M`.
- Format: payload `plan|days|issued|nonce`, **HMAC-SHA256** with a secret read from
  `B2_LICENSE_SECRET` (env, 32+ bytes, generated once, never in the repo). Code is
  base32 of payload+mac so it is short enough to type.
- Codes are single-use: on redemption the server stores **only** `sha256(code)` in
  `data/licenses.json` with `{user_id, plan, until, redeemed_at}`.
- Redemption endpoint `POST /api/plan/redeem` — 5 attempts/hour/account, invalid
  code → generic `400` (no oracle about why), successful → plan updated + audit
  event.
- Expiry is enforced on read: `until < now` → back to `free`, no job needed.
- `tools/issue_license.py --list` shows issued codes (hashes + who redeemed).

## Server work
1. `_plan_for(user)` → `free|byo|pro` + limits; one place, used by every AI route.
2. Replace the flat `B2_AI_DAILY_PER_USER=8` with per-plan limits, keeping the env
   var as the **instance-wide** ceiling (`B2_AI_DAILY_TOTAL`) so the Pi cannot be
   burned by 50 pro accounts.
3. Speaking: count `mock_minutes` per account per week in `data/usage.json`
   (rotating, `0600`), enforced in the token route.
4. `GET /api/plan` → `{plan, limits, usage:{writing_today, speaking_week, reset_at}}`.
5. `/api/health` must stay PII-free.

## Client work
1. Settings → **Plan** card: current plan, usage bars, reset date, and a
   "Have a code?" input.
2. When a limit is hit: a modal that explains the three options and links to the
   BYO-key block and to the code input. No dead-end 429 toast.
3. `free` users see the limits up front, not after failing.

## Acceptance (write `tests/test_plans.py`)
- A fresh account is `free` with the tight limits.
- 4th writing correction in a day → `429` with `error.plan_limit` and the reset
  time; the response says which plan would unlock it.
- Redeeming a valid code → `pro`, limits grow, `GET /api/plan` reflects it.
- Redeeming the same code twice → `400`, plan unchanged.
- A code with one character changed → `400`; the response is byte-identical to the
  reused-code response (no oracle).
- An expired code (`until` in the past) → `free` again on the next request.
- 6 bad redemption attempts → the 6th is rate-limited.
- `data/licenses.json` contains no plaintext code: grep for the code string → 0.
- With a BYO key set, the free writing limit does **not** apply.

## Verify before finishing
```
cd tests && uv run --with httpx python test_plans.py        # exit 0
cd tests && uv run --with playwright python test_byokey.py  # green
cd tests && uv run --with playwright python test_final.py   # green
```
Finish with `VERDICT: ok` only if all three pass.
