# Data map — what the service stores, and how it is protected

Generated for phase 32. The code is the source of truth: this file is only a
map of it. Every claim below is implemented in `store.py`, `plans.py` or
`server.py`.

## Stores under `data/`

| Store | Path | Contents | Protection |
| --- | --- | --- | --- |
| accounts | `data/users.json` | `id`, `name`, `salt`, `hash` (PBKDF2-HMAC-SHA256, 600k), `algo`, `iters`, `color`, `created`; optional `email_hash` and `password_set: false` for Google-created accounts | `0600`, atomic writes |
| Google links | `data/oauth.json` | Google `sub` → local account id; never a name or address | `0600`, atomic writes |
| passkeys | `data/webauthn/<id>.json` | `{credential_id, public_key_cose, sign_count, created, label}` | directory `0700`, file `0600` |
| sessions | `data/tokens.json` | `sha256(token)` → `{user_id, exp, issued, absolute_exp, last_seen, ua_hash}` | `0600`; the raw token is never written |
| progress | `data/users/<id>/progress.json` | practice log, errors, profile, settings, plan mirror | directory `0700`, file `0600` |
| backups | `data/users/<id>/backups/` | last 20 progress documents (`BK_KEEP = 20`) | directory `0700`, files `0600` |
| speaking ledger | `data/users/<id>/speaking.json` | seconds spoken and tokens minted today; no audio | directory `0700`, file `0600` |
| transcripts | `data/users/<id>/speaking/<stamp>.json` | only when the client sets `store_transcript: true` | directory `0700`, file `0600` |
| audit | `data/audit.log` (+ `.1` rotation) | security events, SHA-256 hash chain (`prev` per line) | `0600`, rotates at 5 MB, 90-day retention |
| usage | `data/usage.json` | per-account writing/speaking counters and `last_seen` | `0600` |
| plans | `data/plans.json` | `pro` plan rows: plan, since, until, source, code hash | `0600` |
| licenses | `data/licenses.json` | `sha256(code)` → plan, days, issue/redeem dates, user id | `0600`; plaintext codes never touch disk |
| product events | `data/events/YYYY-MM-DD.jsonl` | whitelisted event names and scalar props, salted IP hash | `0600`, 7-day retention |
| events salt | `data/.events_salt` | random salt for the event IP hash | `0600` |

All JSON writes go through `store._write_json`: a temporary sibling file with
mode `0600`, then `os.replace`, then a final `chmod 0600`. Account directories
are created with `0700` and re-`chmod`ed on every write.

## What is deliberately absent

- No email address in readable form, phone number, real name, address or birth date.
  A Google sign-in can opt in to store only `sha256(email)` for account recovery.
- No raw IP address: access logs, audit lines and product events keep only a
  truncated `sha256` of the client address.
- No User-Agent string: sessions store `sha256(user agent)`.
- No passwords, tokens, licence codes or provider keys in plaintext.
- No audio and no writing content in any log. AI text is forwarded per request
  and only the accepted result lands in the user's own progress.

## Access log (stdout, not `data/`)

One line per request:

```
2026-10-30T12:00:00Z rid=1a2b3c4d GET /api/me 200 7ms ip=4f2c9a1b7e03
```

`rid` is a random per-request id; `ip=` is `sha256(IP)[:12]`. The query string is
not logged, so tokens passed in a URL cannot leak. Request bodies are never
logged.

## Retention

| Data | Limit | Enforced by |
| --- | --- | --- |
| audit | 90 days | `tools/retention.py` (re-chains retained lines and hashes any legacy raw IP) |
| usage counters | 13 months | `tools/retention.py`; `plans.py` also prunes rows unseen for 13 months on write |
| backups | 20 versions | `store.put_progress` and `tools/retention.py` |
| product events | 7 days | `server._prune_events` |
| sessions | 30 days sliding / 90 days absolute | `server.auth_from_token` |

## Deletion (`DELETE /api/account`)

1. Verify the password (constant-time, with the same PBKDF2 cost as a login).
2. Remove `data/users/<id>/` (progress, backups, speaking ledger, transcripts).
3. Remove the record from `data/users.json`.
4. Remove every token whose `user_id` is the account.
5. `plans.forget_user`: remove the plan row and the usage row, and detach
   redeemed licence rows (`user_id = null`) while keeping the code burnt.
6. Remove the Google link (`data/oauth.json`) and the passkey file
   (`data/webauthn/<id>.json`), so neither can outlive the account.
7. Append one final `account_delete` audit event that carries the account id and
   the request id — **never the username**. This is the only file left that
   mentions the account.

`tools/retention.py` is cron-safe, idempotent, and prints every deletion.
