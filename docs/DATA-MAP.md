# Data map — what the service stores, and how it is protected

This is a public map of the data the hosted service keeps. The code is the
source of truth: every claim below is implemented in the storage and server
layers.

## Data categories

| Category | Contents | Protection |
| --- | --- | --- |
| Accounts | account id, display name, salt, password hash, algorithm and cost, colour, creation date; optional email hash, optional TOTP MFA secret and hashed recovery codes, and a "password not set" flag for Google-created accounts | private to the service, atomic writes |
| Google links | Google's stable subject id mapped to a local account id; never a name or address | private, atomic writes |
| Passkeys | credential id, public key, signature counter, creation date and the device label the user chose | per-account private directory |
| Sessions | hash of the session token, expiry, issue and last-seen times, and a hash of the user agent | the raw token is never written |
| Progress | practice log, errors, profile, settings and plan selections | per-account private directory |
| Backups | the last 20 progress documents per account | per-account private directory |
| Own Listening material | optional practice audio (up to 20 MB/file, 40 MB and 10 items per account) plus task, answer key and script metadata | per-account private directory; streamed to the owner via Range requests |
| Speaking ledger | seconds spoken and tokens minted today; no audio | per-account private directory |
| Monthly Speaking guard | aggregate monthly seconds for the instance-wide Gemini Live budget (`spk_spend.json`); no user data, no audio | private, atomic writes |
| Transcripts | only when the client explicitly asks to save a session | per-account private directory |
| Audit log | security events with a SHA-256 hash chain (previous-hash on every line) | private, rotates at 5 MB, 90-day retention |
| Usage counters | per-account writing and speaking counters and the last-seen date | private |
| Product events | whitelisted event names and scalar props with a salted address hash | private, 7-day retention |
| Events salt | random salt used for the event address hash | private |
| Recovery requests | one entry per manual password-reset request: timestamp, name, optional contact, a short address hash and a request id | private, at most 500 entries, 90-day retention |

All JSON writes are atomic: a temporary sibling file with private mode, then a
rename, then a final permission check. Account directories are created with
restrictive permissions and re-checked on every write.

## What is deliberately absent

- No email address in readable form, phone number, real name, address or birth date.
  A Google sign-in can opt in to store only a hash of the email for account recovery. The one
  free-text contact on disk is the optional value a user types into a manual reset request.
- No raw IP address: access logs, audit lines and product events keep only a
  truncated hash of the client address.
- No User-Agent string: sessions store a hash of the user agent.
- No passwords, tokens or provider keys in plaintext.
- No speaking or pronunciation audio and no writing content in any log. Speaking
  audio is never written to disk; AI text is forwarded per request and only the
  accepted result lands in the user's own progress. (Optional Listening practice
  audio uploaded by the user lives only in that account's private directory until
  deleted.)

## Access log (stdout, not stored data)

One line per request:

```text
2026-10-30T12:00:00Z rid=1a2b3c4d GET /api/me 200 7ms ip=4f2c9a1b7e03
```

`rid` is a random per-request id; `ip=` is a truncated hash of the client
address. The query string is not logged, so tokens passed in a URL cannot leak.
Request bodies are never logged.

## Retention

| Data | Limit | Enforced by |
| --- | --- | --- |
| audit | 90 days | the operator's retention job (re-chains retained lines) |
| usage counters | 13 months | the retention job; the meter prunes rows unseen for 13 months on write |
| backups | 20 versions | the progress store and the retention job |
| product events | 7 days | the application on write |
| recovery requests | 90 days / 500 entries | the recovery store (prunes on write, atomic rewrite) |
| sessions | 30 days sliding / 90 days absolute | the session resolver |

## Deletion (account closure)

1. Verify the password with the same cost as a login.
2. Remove the account's progress directory, backups, uploaded Listening material, speaking ledger and transcripts.
3. Remove the account record (including any TOTP MFA configuration).
4. Remove every session token that belongs to the account.
5. Remove the usage row.
6. Remove the Google link and the passkey record, so neither can outlive the account.
7. Append one final `account_delete` audit event that carries the account id and
   the request id — **never the username**. This is the only record left that
   mentions the account.

The retention job is cron-safe, idempotent, and prints every deletion.
