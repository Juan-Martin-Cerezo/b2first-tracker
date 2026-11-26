# Privacy Policy — B2 First Tracker

**Version 1.4** · Last updated: 2026-11-26 · Served live at `/privacy`

**Changelog**

- 1.4 — 2026-11-26 · Clarified that speaking transcripts are never stored by the web
  app (`store_transcript: false`) and aligned retention and quota references with the
  current code.
- 1.3 — 2026-11-18 · Hosted service: accounts and progress live on the provider's
  server. Internal host details removed from the public policy.
- 1.2 — 2026-11-04 · Speaking exam: recognition runs in the browser, the application
  uploads no audio, and the transcript leaves only when an AI provider is configured.
- 1.1 — 2026-11-02 · Account-recovery requests: what the login form stores, who reads it,
  and the 90-day retention.
- 1.0 — 2026-10-30 · First complete version: data map, third parties, retention,
  self-service export and deletion, age policy.

This policy describes what the B2 First Tracker service stores and what it sends to
third parties. It is written against the code, not against an aspiration.

## 1. Who runs this service

B2 First Tracker is a hosted study service for the Cambridge B2 First. The public
entry point is `https://firsttracker.app`. Accounts and progress live on the
provider's server; there is no company, no cloud database and no advertising
network behind it. The only web analytics is cookie-free aggregate Cloudflare Web
Analytics (page views, country, and referrer). The operator of the service is the
person who runs the server and answers the contact address below.

## 2. What is stored, and where

Everything below lives on the provider's server, attached to your account. Files
are private to the service and are not served to anyone else.

| Data | What it contains |
| --- | --- |
| Account | username, avatar colour, creation date, salt and PBKDF2-HMAC-SHA256 password hash (600,000 iterations) |
| Sessions | `sha256(token)` and expiry timestamps — the token itself is never written |
| Progress | practice log, error log, profile, settings |
| Backups | the last 20 versions of your progress |
| Speaking ledger | minutes spoken today (a number, no audio, no transcript) |
| Usage counters | writing and speaking counters for the current day |
| Security audit | event type, timestamp, request id, account name or id, hashed client address |
| Product events | feature name, duration, truncated error text, random tab id, account id, salted address hash |
| Google link | Google's stable `sub` mapped to your local account id (no name, no address) |
| Passkeys | credential id, public key (COSE), signature counter and the device label you choose |
| Two-factor auth (TOTP) | base32 TOTP secret and hashed one-time recovery codes, only if you enable MFA |
| Own Listening material | optional practice audio (up to 20 MB per file, 40 MB / 10 items per account) and task/key/script text you upload under Listening |
| Recovery requests | user name, the optional contact you type, timestamp, 16-character hash of your address |

The password itself is never stored. The raw session token is never stored. Raw
IP addresses are not stored: the audit log and the access log keep only the
first 12 hex characters of `sha256(IP)`, and product events keep 16 characters
of a salted hash. There is no email address in readable form, no real name, no
user agent string (only `sha256(user agent)` attached to a session) and no
payment data anywhere.

**Optional email hash.** When you sign in with Google for the first time, the
confirmation screen offers a checkbox to keep your email for account recovery.
It is off by default. If you enable it, the server stores only
`sha256(normalised email)`; the address itself is never written to disk, logged
or sent anywhere else. Turning the checkbox off stores nothing.

**Account-recovery requests.** The *Forgot your password?* form on the login screen stores exactly
this, per request:

- the user name you type;
- the contact string you type, which is optional — it can be an email, a `@telegram` handle or
  anything else you want the operator to use;
- the timestamp of the request;
- a 16-character hash of your IP address (the raw address is never written).

It exists so the operator can reset the password by hand and answer you. Only the operator reads
it; it is never sent to a third party. Entries older than 90 days are deleted, and the store is
capped at 500 entries.

## 3. What is never stored

- **Speaking audio is never written to disk.** The live examiner streams microphone
  audio from your browser directly to Google; it does not pass through our server.
  Turn-based voice and pronunciation clips are held in memory for the single
  provider request and are deleted in the same handler. No speaking audio file,
  temporary file or log entry is created. (Only audio files you explicitly upload
  yourself under Listening → Own material are stored in your private account
  directory, and you can delete them at any time.)
- **Speaking transcripts are not stored.** The web app always sends
  `store_transcript: false` when requesting a Speaking report. Only the summary
  report row (date, bands, and counts) is saved to your progress if you explicitly
  click **Save report**; your spoken turns are never written to disk.
- No writing or answer is logged in the audit log or in product events. The AI
  request sends the text you chose to correct and receives feedback; the text is
  not persisted by the service beyond the request (the accepted result is saved
  in your own progress).
- No email, phone, address, age, or government identifier is collected. The only
  exceptions are the opt-in email hash described in §2 and the optional contact you type into a
  recovery request; neither is used for anything else.
- No advertising identifiers, no tracking pixels, and no behavioural profiling.
  The service allows cookie-free aggregate **Cloudflare Web Analytics**
  (`https://static.cloudflareinsights.com`) for page views, country, and referrer;
  no other external script is allowed by the Content-Security-Policy.

**Speech recognition in the Speaking exam.** The exam transcript is written by
the browser's own speech recogniser (`SpeechRecognition` / `webkitSpeechRecognition`,
`en-GB`), not by our server. The application never records your voice and
never uploads audio for recognition: no recording is created, no audio file is
written, and no audio passes through our server. The recogniser belongs to the
browser, and a browser may use its vendor's speech service to turn speech into
text; that path belongs to the browser, not to this application. With no AI
provider configured, the recognised text stays in the browser and is discarded
when the exam closes. With a provider configured (the service's text key or your
own), only text leaves the browser: the last recognised candidate line goes to
the partner endpoint for one reaction, and the transcript with its timings goes
to the report endpoint only when you ask for a report. Neither request carries
audio. The only Speaking features that send audio are the optional voices listed
in §4.

## 4. Third parties that receive data

| Provider | When | What it receives | Where it processes |
| --- | --- | --- | --- |
| **Cloudflare, Inc.** | Every public request | the full HTTP request **in plaintext** (TLS terminates at Cloudflare's edge), including headers, path, cookies and request bodies; your IP address; cookie-free aggregate Web Analytics (page views, country, referrer) | global edge network |
| **Google Identity (OAuth)** | Only if you press “Continue with Google” | the authorization request (`openid email profile`), your Google account choice and the authorization code; the code is exchanged server-side and never stored | Google infrastructure outside Argentina |
| **Google (Gemini Live)** | Speaking Parts 1–4 with the live examiner/partner | your microphone audio (16 kHz PCM), the examiner script, and the session token | Google infrastructure outside Argentina |
| **Google (Gemini API)** | If the operator configures Gemini as the text provider, or for speaking-report generation | the text you asked to correct or the transcript you chose to analyse | Google infrastructure |
| **DeepSeek** | Writing corrections and speaking reports, by default | the text you explicitly submitted for correction, plus the task type | DeepSeek infrastructure |
| **Microsoft Azure AI Speech** | Pronunciation assessment, only when the operator has configured it | at most 10 seconds of audio per turn and, optionally, the reference sentence | Microsoft regional speech endpoints |

Cloudflare sees requests at the edge, so it can read them even though the hop
from Cloudflare to the origin is encrypted. This is a property of terminating
TLS at a CDN, not a hidden feature.

**Google Gemini free tier.** If the service uses a free-tier Google API key,
Google's terms allow it to use the content it receives to improve its products.
Paid-tier API usage is excluded from that training use. Which tier is active
depends on the key the operator configured; the application cannot detect or
change it. This statement reflects Google's published Gemini API terms and is
not a guarantee about Google's internal processing.

**DeepSeek.** DeepSeek receives the writing text and may retain it under its own
API terms. This application sends no account identifier with the request, but
the provider sees the request from the server's address.

**Azure** is used only when the operator has configured a speech key and region.
If it is not configured, the endpoint answers `speech not configured` and
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
- **Usage counters** — to enforce the daily fair-use limits described in the
  Terms.
- **Recovery requests** — so a forgotten password can be reset by hand when there is no
  email to send a reset link to.

## 6. How long it is kept

| Data | Retention |
| --- | --- |
| Security audit log | 90 days, then removed by the operator's retention job |
| Product events | 7 days (older files are deleted on write) |
| Usage counters | 13 months |
| Progress backups | the last 20 versions per account |
| Progress, account, usage | until you delete the account |
| Session tokens | 30 days sliding, with a 90-day absolute ceiling |
| Recovery requests | 90 days, pruned on the next request; capped at 500 entries |
| Speaking audio | never stored |
| Speaking transcripts | never stored by the web app (`store_transcript: false`) |
| Own Listening material | until you delete the item or the account |

The retention limits are enforced by an idempotent daily job on the server. It is
not something you need to run.

## 7. Your rights, all self-service

- **Export everything.** Click your avatar / stage badge in the top-right corner,
  open **Account**, and press **Export my data** (or call the export endpoint with
  your session). The JSON file contains your progress, usage counters and your
  own audit events.
- **Delete the account.** Same **Account** panel → **Delete my account** → enter
  your password and type `DELETE`. This removes the account record (including any
  TOTP MFA configuration), every session, the progress directory including backups
  and any uploaded Listening material, the usage row, your Google link and your
  passkeys. A final audit event records that an account was
  deleted; it contains the account id, never the username.
- **Clear your own provider key.** Open **Settings** → the **AI provider**
  card → **Clear key**. A BYO key lives only in your browser's localStorage and
  is sent per request; it is never stored on the server.
- **Recovery requests.** A request you filed from the login screen is deleted after at most 90
  days. Because it carries no account id, it is not included in the export or removed by account
  deletion; ask the operator through the advisory form to remove it sooner.

Because there is no email on file, a deleted account cannot be recovered. Export
first if you want a copy. Deletion is immediate; the only surviving trace is the
non-identifying audit line described above and the operator's daily backup,
which is rotated out within 14 days.

## 8. Age

The product targets users aged **16 and over**. If you are under 18, you may use
it only with the permission of a parent or guardian. The account form asks for no
birth date, so the service relies on this statement.

## 9. No selling, no advertising, no tracking

We do not sell, rent or trade personal data. There is no advertising, no
behavioural profiling, no tracking pixel, and no session recording; the only web
analytics is cookie-free aggregate Cloudflare Web Analytics (page views, country,
and referrer). There is exactly one first-party browser preference store:
`localStorage` holds your theme, your language, your local progress cache and —
if you choose to use it — your own provider key. It leaves your browser only
when you sync or export.

If your browser sends `DNT: 1` or the Global Privacy Control signal, the app
sends no product events at all. Every feature keeps working.

## 10. Security measures

- PBKDF2-HMAC-SHA256 at 600,000 iterations, per-account salt, constant-time
  comparison; hashes below the current cost are re-hashed on the next login.
- The embedded password blocklist is checked, as are passwords equal to the
  username and passwords shorter than 12 characters.
- Tokens are stored hashed, rotate on password change, and are capped at 90 days.
- Passkey assertions are verified locally (P-256 ECDSA, RP-ID hash, challenge,
  origin); a signature counter that goes backwards is refused. A Google
  `id_token` is verified against Google's published JWKS (RS256, `iss`, `aud`,
  `exp`, `nonce`) before the account is touched.
- Login lockout and exponential backoff; per-IP and per-account rate limits.
- The audit log is a SHA-256 hash chain; an edited or deleted line is detectable.
- Data files are private to the service, and TLS terminates in front of it.

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
