# Privacy Policy — B2 First Tracker

**Version 1.0** · Last updated: 2026-10-30 · Served live at `/privacy`

**Changelog**

- 1.0 — 2026-10-30 · First complete version: data map, third parties, retention,
  self-service export and deletion, age policy.

This policy describes what this instance of B2 First Tracker actually stores and
what it sends to third parties. It is written against the code, not against an
aspiration. If a claim here cannot be checked in this repository, it is marked
as unverified.

## 1. Who runs this service

This is a self-hosted study application. The server is a Raspberry Pi at a
private address in Argentina; the public entry point is
`https://firsttracker.app`. There is no company, no cloud database and no
analytics platform. The owner of the instance is the person who deployed it.

## 2. What is stored, and where

Everything below lives on that Raspberry Pi, under the `data/` directory of the
application. Files are readable only by the service user (`0600`; account
directories `0700`).

| Data | What it contains | Where |
| --- | --- | --- |
| Account | username, avatar colour, creation date, salt and PBKDF2-HMAC-SHA256 password hash (600,000 iterations) | `data/users.json` |
| Sessions | `sha256(token)` and expiry timestamps — the token itself is never written | `data/tokens.json` |
| Progress | practice log, error log, profile, settings, plan mirror | `data/users/<id>/progress.json` |
| Backups | the last 20 versions of that progress file | `data/users/<id>/backups/` |
| Speaking ledger | minutes spoken today (a number, no audio) | `data/users/<id>/speaking.json` |
| Transcripts | only if you explicitly ask to save a session | `data/users/<id>/speaking/` |
| Plan and usage | plan row, writing/speaking counters, last-seen date | `data/plans.json`, `data/usage.json` |
| Licence rows | `sha256(code)`, never the code in readable form | `data/licenses.json` |
| Security audit | event type, timestamp, request id, account name or id, hashed client address | `data/audit.log` |
| Product events | feature name, duration, truncated error text, random tab id, account id, salted address hash | `data/events/*.jsonl` |

The password itself is never stored. The raw session token is never stored. Raw
IP addresses are not stored: the audit log and the access log keep only the
first 12 hex characters of `sha256(IP)`, and product events keep 16 characters
of a salted hash. There is no email address, no real name, no user agent string
(only `sha256(user agent)` attached to a session) and no payment data anywhere
in `data/`.

## 3. What is never stored

- **Audio is never written to disk.** The live examiner streams microphone audio
  from your browser directly to Google; it does not pass through this server.
  Pronunciation clips are held in memory for the single Azure request and are
  deleted in the same handler (`del audio`). No audio file, temporary file or
  log entry is created.
- No writing or answer is logged in the audit log or in product events. The AI
  request sends the text you chose to correct and receives feedback; the text is
  not persisted by this server beyond the request (the accepted result is saved
  in your own progress).
- No email, phone, address, age, or government identifier is collected.
- No advertising identifiers, no tracking pixels, no third-party analytics
  script. Cloudflare may inject its Web Analytics beacon at the edge; this
  instance's Content-Security-Policy blocks `static.cloudflareinsights.com`, so
  the beacon never executes. The owner is also expected to keep Web Analytics
  disabled in the Cloudflare dashboard.

## 4. Third parties that receive data

| Provider | When | What it receives | Where it processes |
| --- | --- | --- | --- |
| **Cloudflare, Inc.** | Every public request | the full HTTP request **in plaintext** (TLS terminates at Cloudflare's edge), including headers, path, cookies and request bodies; your IP address | global edge network |
| **Google (Gemini Live)** | Speaking Parts 1–4 with the live examiner/partner | your microphone audio (16 kHz PCM), the examiner script, and the session token | Google infrastructure outside Argentina |
| **Google (Gemini API)** | If the owner configures Gemini as the text provider, or for speaking-report generation | the text you asked to correct or the transcript you chose to analyse | Google infrastructure |
| **DeepSeek** | Writing corrections and speaking reports, by default | the text you explicitly submitted for correction, plus the task type | DeepSeek infrastructure |
| **Microsoft Azure AI Speech** | Pronunciation assessment, only when the owner has configured it | at most 10 seconds of audio per turn and, optionally, the reference sentence | Microsoft regional speech endpoints |

Cloudflare sees requests at the edge, so it can read them even though the hop
from Cloudflare to the Pi is encrypted. This is a property of terminating TLS at
a CDN, not a hidden feature.

**Google Gemini free tier.** If this instance uses a free-tier Google API key,
Google's terms allow it to use the content it receives to improve its products.
Paid-tier API usage is excluded from that training use. Which tier is active
depends on the key the owner configured; the application cannot detect or change
it. This statement reflects Google's published Gemini API terms and is not a
guarantee about Google's internal processing.

**DeepSeek.** DeepSeek receives the writing text and may retain it under its own
API terms. This application sends no account identifier with the request, but
the provider sees the request from the server's address.

**Azure** is used only when the owner has configured a speech key and region. If
it is not configured, the endpoint answers `speech not configured` and
pronunciation is reported as *not measured*; the app never invents that score.

## 5. Why each piece exists

- **Progress and account** — so the plan, streak and charts survive a reload and
  follow you between your phone and your computer.
- **Sessions** — to keep you logged in without asking for the password on every
  request.
- **Security audit** — to detect brute force, credential stuffing and account
  abuse, and to let an account holder see their own security events.
- **Product events** — to find crashes and slow views. They are counts and
  truncated error messages, never content.
- **Usage counters** — to enforce the fair-use limits of your plan.

## 6. How long it is kept

| Data | Retention |
| --- | --- |
| Security audit log | 90 days, then removed by `tools/retention.py` |
| Product events | 7 days (older files are deleted on write) |
| Usage counters | 13 months |
| Progress backups | the last 20 versions per account |
| Progress, account, plan | until you delete the account |
| Session tokens | 30 days sliding, with a 90-day absolute ceiling |
| Audio | never stored |
| Transcripts | until you delete them or the account |

The limits above are enforced by `tools/retention.py`, an idempotent, cron-safe
script that prints every deletion. It is written to run daily from cron; the
repository ships the tool, and the host schedules it.

## 7. Your rights, all self-service

- **Export everything.** Click your avatar / stage badge in the top-right corner,
  open **Account**, and press **Export my data** (or call `GET /api/export` with
  your session). The JSON file contains your progress, plan, usage counters and
  your own audit events.
- **Delete the account.** Same **Account** panel → **Delete my account** → enter
  your password and type `DELETE` (or `DELETE /api/account`). This removes the
  user record, every session, the progress directory including backups, the plan
  and usage rows, and any licence link. A final audit event records that an
  account was deleted; it contains the account id, never the username.
- **Clear your own provider key.** Open the **AI** tab → the **✨ AI provider**
  card → **Clear key**. A BYO key lives only in your browser's localStorage and
  is sent per request; it is never stored on the server.

Because there is no email on file, a deleted account cannot be recovered. Export
first if you want a copy. Deletion is immediate; the only surviving trace is the
non-identifying audit line described above and the daily host backup, which the
owner rotates out within 14 days.

## 8. Age

The product targets users aged **16 and over**. If you are under 18, you may use
it only with the permission of a parent or guardian. The account form asks for no
birth date, so the service relies on this statement.

## 9. No selling, no advertising, no tracking

We do not sell, rent or trade personal data. There is no advertising, no
behavioural profiling, no tracking pixel, no third-party analytics SDK and no
session recording. There is exactly one first-party browser preference:
`localStorage` holds your theme, your language, your local progress cache and —
if you choose to use it — your own provider key. It leaves your browser only
when you sync or export.

If your browser sends `DNT: 1` or the Global Privacy Control signal, the app
sends no product events at all. Every feature keeps working.

## 10. Security measures

- PBKDF2-HMAC-SHA256 at 600,000 iterations, per-account salt, constant-time
  comparison; hashes below the current cost are re-hashed on the next login.
- The 1,000 most common passwords are rejected, as are passwords equal to the
  username and passwords shorter than 10 characters.
- Tokens are stored hashed, rotate on password change, and are capped at 90 days.
- Login lockout and exponential backoff; per-IP and per-account rate limits.
- The audit log is a SHA-256 hash chain; `tools/verify_audit.py` detects edited
  or deleted lines.
- Data files are `0600`, account directories `0700`, and the service binds to
  loopback behind the Cloudflare tunnel.

No system is perfectly secure. See `/security` for the disclosure policy.

## 11. Legal basis and contact

This policy is written with Argentina's Personal Data Protection Law
(**Ley 25.326**) in mind: access, correction and deletion rights are available
through the self-service tools above. The application makes no claim of
certified compliance with any other regulation.

There is no published owner mailbox. Security and privacy requests go through
the repository's private advisory form:
https://github.com/Juan-Martin-Cerezo/b2first-tracker/security/advisories/new
The machine-readable disclosure file is `/.well-known/security.txt`.

## 12. Changes

The version and date at the top of this page are authoritative. Material changes
are announced in the app and reflected in the changelog. Continued use after a
change means you accept the updated policy; you may export and delete your
account at any time.
