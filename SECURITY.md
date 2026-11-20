# Security Model — B2 First Tracker

## 1. Scope

This document covers the security of the hosted B2 First Tracker service at
`https://firsttracker.app`. Accounts and progress live on the provider's server;
students use the app from a browser.

**What the system protects:**

- **Study progress per user** — sessions, scores, error taxonomy, weekly plans,
  writing submissions and corrections. Each account has its own data, and
  accounts cannot read each other.
- **Credentials** — account passwords (stored only as PBKDF2 hashes) and session
  tokens (stored only as SHA-256 hashes).
- **The AI provider keys** — the operator's shared key used for corrections, and
  any key a user brings for themselves.

**What it deliberately does not protect or contain:**

- **No payment data.** There is no purchase flow anywhere in the product.
- **No personal data beyond the chosen display name.** No email, no real name,
  no address, no phone. Accounts are identified by a name the user invents.
- **No defence against a compromised server.** Anyone with administrative access
  can read the stored data. The model assumes the host and its operator are
  trusted.
- **The provider sees the text submitted for correction.** Only the text leaves
  the service, together with the key being used; nothing else is sent anywhere.

**How to verify:**

- `bash tools/audit.sh` — external checks against the public service (TLS,
  HSTS/preload, CSP directives, COOP/CORP, `security.txt`, sensitive paths,
  method/traversal/body-limit probes, auth gates, CORS, banner hygiene). Every
  check prints PASS/FAIL and one line of evidence; the script exits non-zero on
  any regression.
- `python3 tools/verify_audit.py` — validates the SHA-256 hash chain of the audit
  log and exits non-zero if a line was edited, deleted or reordered.
- [docs/SECURITY-CHECKLIST.md](docs/SECURITY-CHECKLIST.md) — the ASVS 4.0.3
  Level 2 table with PASS/FAIL/N/A per control.
- `tests/test_security3.py` and the rest of `tests/` cover the same guarantees
  from the inside (re-hashing, absolute TTL, backoff, audit chain, payload
  limits, revocation, headers).

## 2. Threat model

| Asset | Threat | Control |
| --- | --- | --- |
| Study progress | Files stolen or tampered with at rest | Private per-account data, restrictive file modes, atomic writes (temporary file + rename), per-user write lock |
| Passwords | Offline cracking of the account file | PBKDF2-HMAC-SHA256, **600,000 iterations**, 16-char per-user salt; constant-time compare; legacy hashes are re-hashed on the next successful login |
| Session tokens | Theft from disk or replay after logout | Only `sha256(token)` is stored; 30-day **sliding** TTL capped by a 90-day **absolute** expiry; logout revokes; a password change revokes **every** session |
| Accounts | Brute force / credential stuffing | 5 failed logins lock the username for 15 minutes **across IPs**; **exponential backoff** of 5 s / 15 s / 60 s after the 3rd/4th/5th failure; IP and username rate buckets |
| Username privacy | User enumeration via errors or timing | Identical "Wrong username or password." for unknown user and wrong password; the unknown-user path burns a full dummy PBKDF2; `hmac.compare_digest` everywhere; the recovery request answers the same `200 {"ok":true}` for every valid name |
| Per-user data | IDOR: read/write another account's data by guessing its id | The session token must belong to the requested user (otherwise `403`); requests without a token always get `401`; audit events are filtered to the caller |
| Server filesystem | Path traversal via parameters or file routes | User ids validated against an explicit safe pattern with `..` rejection; file routes resolve real paths and require the result to stay inside their root |
| AI provider key | Key theft or free-riding | The key comes only from the environment, never from the request; never logged, never written to disk; a bounded request cap |
| AI budget | Draining the shared key | Per-IP minute/hour buckets; daily per-account caps (5 writing evaluations, 1 Speaking mock / 15 min per UTC day in `plans.py`); instance-wide daily and monthly ceilings; user-supplied keys bypass the shared quota; upstream timeout |
| Availability | DoS via oversized or malformed payloads | Bounded progress payload with a schema (list/string/depth/number caps) → `422`; per-account and per-IP rate limits → `429`; busy locks answer `429` instead of stacking |
| Network surface | Slowloris, connection floods, oversized requests sent by hand | Socket timeout per connection; a global connection semaphore answers `503 {"error":"busy","retry_after":5}` with `Retry-After`; URI/header/body limits; optional Host allowlist |
| Request smuggling / traversal surface | Path traversal, encoded slash tricks, hidden-file probing, unknown verbs | Path rejected for NUL, backslash, `..` in any encoding and empty segments; hidden dot-files → `403`; method allowlist → `405` + `Allow`; `404` never lists candidates |
| Browser sessions | XSS / CSRF | CSP (`default-src 'self'`, hashed inline `<script>` blocks, no `'unsafe-inline'` or `'unsafe-hashes'` in `script-src`, `https://static.cloudflareinsights.com` as the only external script, `frame-ancestors 'none'`, `base-uri 'none'`, `form-action 'self'`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; rendered names go through `html.escape`; API auth is a `Bearer` header (only `/api/listening/material/audio` uses a scoped HttpOnly cookie for `<audio>` Range streaming) and CORS is closed |
| Audit trail | Secrets leaking into logs; users reading each other's events; silent log tampering | Access log: method, path without query, status, request id — never tokens or bodies; the audit log holds events with user + hashed IP only and **every line carries the hash of the previous raw line**, so edits/deletions break the chain; an account sees only its own events |
| Security events | Blind spots during abuse or provider misuse | Append-only events for blocked AI calls, rate limits, rejected pronunciation clips, token mints and revoked sessions — each with a request id and scalar metadata only, no content and no secrets |
| Disclosure metadata | No documented way to report a vulnerability | `/.well-known/security.txt` (RFC 9116): `Contact`, `Expires`, `Canonical`, `Policy` |
| Owner data (legacy path) | Tokenless reads from a request that bypasses the proxy | The no-token owner path is accepted only when the request carries no forwarding headers; on the public service every request arrives through the edge, so the answer is `401` |

## 3. Controls implemented

| Control | Status | Notes |
| --- | --- | --- |
| Input validation | Implemented | Progress shape, list/string/depth/finite-number caps, safe user ids, AI request and model-output schemas, password policy (12 characters, blocklist plus derived rules, username check), diagnostic JSON validation |
| SQL injection | N/A (no database) | Storage is JSON read with `json.load`; there is no query language and no string-built SQL anywhere |
| Password hashing & MFA | Implemented | PBKDF2-HMAC-SHA256, **600,000 iterations**, per-user salt, constant-time compare; older hashes upgraded transparently on the next login; optional TOTP MFA (RFC 6238, `mfa.py`) with hashed recovery codes, Google OAuth, and WebAuthn passkeys |
| Session lifetime | Implemented | 30-day sliding expiry capped by a 90-day absolute expiry per token; both clocks are enforced on read |
| Audit log integrity | Implemented | SHA-256 hash chain on every line; the verifier exits non-zero on a broken link |
| Security headers | Implemented | HSTS `max-age=63072000; includeSubDomains; preload`; CSP `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`, `form-action 'self'`, no `'unsafe-eval'`, no `'unsafe-inline'` or `'unsafe-hashes'` in `script-src`; COOP/CORP `same-origin`; `Referrer-Policy: no-referrer`; `Permissions-Policy` scoped (`microphone=(self)` only on the tracker) |
| Body limits by route | Implemented | Global ceiling checked from `Content-Length` before the body is read; larger documented routes have their own caps and answer `413` |
| Secrets outside the repository | Implemented | Provider keys come from the environment, are never logged and are never written to progress; the repo ships no credentials |
| Server-side auth | Implemented | Every data route validates the Bearer token on every request |
| Rate limit login / reset | Implemented | Login per IP and per username, with 5-failure lockout; registration and password-change buckets; the manual recovery request is capped on top of the credential bucket |
| External timeouts | Implemented | Upstream AI calls have a hard timeout; store locks fail after 5 s and answer `429` busy |
| Retries only on transient errors | Implemented | Nothing retries automatically: an upstream failure returns `502` once, and the client resubmits only on user action |
| Payment idempotency | N/A | There are no payment flows |
| Transactions (equivalent) | Implemented | Per-user locks around backup + write, atomic rename for every JSON write; concurrent writes serialize or get `429` |
| Indexes / N+1 / connection pool | N/A (no database) | Stored documents are read whole; there are no queries and no database connections |
| Versioned migrations | Implemented | Older progress documents are upgraded on read and the original is copied to a backup first |
| Logs with request id | Implemented | Every response carries a request id; the access log line and every audit event store the same id |
| Health check | Implemented | Reports whether the data directory is writable, the user file parses and every user directory exists; absolute paths only when the operator opts in |
| 429, not 500 | Implemented | Rate limits and lock contention answer `429` with `Retry-After`; `500` is reserved for unexpected exceptions, never for load |
| Backups + tested restore | Implemented | Per-save rotation (20 per user) and a daily verified tarball (14 kept); every backup run performs a test restore and parses every JSON file |
| CORS closed | Implemented | No `Access-Control-Allow-Origin` on any response; preflights answer `204` with no permissive header |
| A user cannot read another user's data by id | Implemented | Token↔user binding answers `403` across accounts, the audit endpoint filters to the caller, and the user list exposes only login directory fields (id, name, colour, created) |

**External audit status.** `bash tools/audit.sh` passes every check against the
public service. The `Server` banner is `B2First` with no version. The remaining
non-PASS control is the password blocklist (PARTIAL); see section 5.6.

## 4. Backups and restore

Backups are made at two levels:

1. **On every save.** Before a progress file is overwritten, the previous version
   is copied to that account's backup directory, keeping the **20** most recent.
2. **Daily job.** A scheduled job creates a timestamped archive of the whole data
   set. The archive is encrypted and stored outside the application directory.

**Verification on every run.** The job refuses to pass unless the archive lists
cleanly, a test restore into a temporary directory extracts cleanly, and every
JSON document in the restored copy parses. It keeps the 14 newest archives and
appends one line to its log.

**Restore.** The operator stops writes, moves the current data aside, extracts
the chosen archive, restores private permissions, starts the service and checks
the health endpoint. The procedure is rehearsed on a scratch copy before it is
used.

## 5. Residual risks (honest status)

### 5.1 CSP: `style-src 'unsafe-inline'` and Cloudflare Web Analytics beacon

`script-src` contains neither `'unsafe-inline'` nor `'unsafe-hashes'`. All inline
event handlers were removed in favour of `data-*` event delegation in
`index.html`, so `script-src` only needs `'self'`, the SHA-256 hashes of the
served `<script>` blocks, and `https://static.cloudflareinsights.com` for
cookie-free aggregate Cloudflare Web Analytics (`connect-src` allows
`https://cloudflareinsights.com` and `https://static.cloudflareinsights.com` for
the beacon POST, plus `wss://generativelanguage.googleapis.com` for live
Speaking).

The remaining CSP compromises are:

- `style-src 'self' 'unsafe-inline'` is still used for inline `style` attributes.
- `'strict-dynamic'` is intentionally omitted because CSP3 browsers ignore host
  allowlists when it is set, which would block the Cloudflare Web Analytics
  beacon injected at the edge.

- **Mitigations already in place:** all dynamic names go through `html.escape`;
  student text and AI output are rendered with `textContent`; zero inline event
  handlers; `connect-src` restricted; `frame-ancestors 'none'`,
  `base-uri 'none'`, `object-src 'none'`; the browser test suite checks for zero
  `securitypolicyviolation` events.

### 5.2 Audit history written before the hash chain

Audit lines created before the hash chain have no previous-hash field. They are
an **unverifiable prefix**: the verifier reports them as such, verifies the
transition into the first chained line, and verifies every link from there on.
An attacker who edited a line *before* the upgrade cannot be detected
retroactively. Rotation removes that prefix over time.

### 5.3 Host and operator are trusted

Anyone with administrative access to the server can read the stored data and
could rewrite the whole audit log (a fresh, internally consistent chain is
possible with write access). The hash chain detects accidental or partial
tampering and tampering by a process that lacks write access to the file; it is
not a defence against a compromised host.

### 5.4 No dedicated disclosure mailbox

There is no published email address for this project. `/.well-known/security.txt`
publishes the GitHub private security advisory URL as the working `Contact`
channel.

### 5.5 Account recovery is manual

There is no email flow, so a forgotten password is handled by hand: the login
screen can file a request (user name plus an optional contact) and the operator
resets it. Nothing is sent by email and the request endpoint never confirms
whether an account exists. This is a deliberate consequence of not collecting
personal data.

### 5.6 Password blocklist is still partial

ASVS 4.0.3 asks for at least 12 characters (2.1.1) and a check against the top
3,000 breached passwords (2.1.7). This product enforces **12 characters** and
ships a **1,000-entry sourced blocklist plus deterministic derivatives** (app
words, common suffixes, keyboard walks, repetitions: 22,492 candidates). There
is no downloaded wordlist and no dependency. The length row is PASS; the
blocklist row stays **PARTIAL** because the embedded list is not the full ASVS
top 3,000. Loading a larger sourced list is a small, isolated change.

### 5.7 Rotated audit history keeps only one file

One rotated audit segment is kept; when a second rotation happens the oldest
segment is deleted, so its hash-chain head becomes unverifiable. The current
segment and the transition remain verifiable. Longer retention would need a
different sink (append-only object storage).

## 6. Reporting a vulnerability

Report security issues privately through GitHub's vulnerability reporting for
this repository:

**https://github.com/Juan-Martin-Cerezo/b2first-tracker/security/advisories/new**

Machine-readable disclosure metadata: **https://firsttracker.app/.well-known/security.txt**
(RFC 9116), which lists the GitHub advisory URL above as the contact channel.

(If you cannot use advisories, open an issue with no details asking for a
contact channel.)

What to expect:

- An acknowledgement within a few days.
- Confirmation of the issue and, when it is understood, a fix or a documented
  mitigation.
- Disclosure timing agreed with you before anything is published.
- Credit in the release notes if you want it.

This is a no-budget project: there is no bug bounty, but every report gets a real
answer. Please do not test against other users' accounts on the public service —
a proof of concept against your own account is enough.
