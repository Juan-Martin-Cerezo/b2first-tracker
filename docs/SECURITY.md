# Security Policy — B2 First Tracker

**Version 1.1** · Last updated: 2026-11-18 · Served live at `/security`

**Changelog**

- 1.1 — 2026-11-18 · Hosted service: accounts and data live on the provider's
  server. Host, network and internal paths removed from the public policy.
- 1.0 — 2026-10-30 · First published security policy and disclosure process.

## 1. What this service is

A hosted study service for the Cambridge B2 First. Students create an account at
`https://firsttracker.app` and use the tracker from a browser. Accounts, progress
and the application data live on the provider's server; nothing is installed on
the student's machine. The application itself is Python's standard library HTTP
server — no framework and no external database.

## 2. Reporting a vulnerability

Use the private advisory form:

https://github.com/Juan-Martin-Cerezo/b2first-tracker/security/advisories/new

The machine-readable contact and expiry are in `/.well-known/security.txt`
(RFC 9116). There is no published owner mailbox and no bug bounty.

Please include: the affected endpoint or file, the steps to reproduce, the
impact you believe it has, and whether you accessed any other user's data. Do
not run denial-of-service tests, do not modify or exfiltrate other people's
progress, and do not paste real passwords or third-party API keys into a report.

**What to expect.** Acknowledgement through the advisory thread, an assessment,
and a fix or a documented decision. There is no guaranteed response time: this
is a single-owner project. We will credit you in the advisory unless you ask us
not to.

## 3. Data protection in place

- Passwords and MFA: PBKDF2-HMAC-SHA256, 600,000 iterations, unique 128-bit salt,
  constant-time comparison. Hashes below the current cost are upgraded on login.
  The embedded password blocklist (1,000 sourced entries plus deterministic
  derivations), passwords equal to the username, and anything shorter than 12
  characters are rejected. Optional TOTP two-factor authentication (RFC 6238)
  with hashed one-time recovery codes, Google OAuth, and WebAuthn passkeys are
  also supported.
- Sessions: 192-bit random tokens; only `sha256(token)` is stored; 30-day sliding
  expiry capped by a 90-day absolute ceiling; every session is revoked on a
  password change; a User-Agent change is logged but not blocked.
- Storage: account data, session records, usage counters and the audit log are
  private to the service; per-account directories are more restrictive; writes
  are atomic (temporary file + rename).
- Audit: append-only JSON lines with a SHA-256 hash chain. An edited or deleted
  line is detectable. Retention is 90 days.
- Access log: method, path, status, duration, request id and a truncated hash of
  the client address. Never the raw IP, never a token, never a request body.
- Rate limits: registration, login (per IP and per username, with lockout and
  backoff), progress writes, AI calls and speaking minutes.
- Transport: HSTS, no version banner, restrictive CSP (inline scripts verified
  by SHA-256 hash, no `'unsafe-inline'` or `'unsafe-hashes'` in `script-src`,
  and `https://static.cloudflareinsights.com` as the only external script),
  `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, closed CORS, Host allowlist
  and path traversal checks. TLS terminates at the edge network in front of the
  service (see `/privacy`).

## 4. What is intentionally not protected

- **The server is the trust boundary.** Anyone with administrative access to the
  host can read the stored data. Disk encryption is not part of the application.
- **The AI providers receive what you send them.** Writing text goes to
  DeepSeek (or the configured provider); live speaking audio goes from your
  browser directly to **Google**; pronunciation clips go to Azure when enabled.
  Their handling is governed by their own terms.
- **The edge provider is in the request path.** It terminates TLS and can see
  request bodies in plaintext.
- **No email recovery.** There is no address to send a reset link to; a user can file a manual
  request from the login screen, but the password is only reset by the operator.
- **Backups are daily and rotated.** A deleted account can persist in a backup
  for up to 14 days.

## 5. Scope

In scope: authentication and session handling, access control between accounts,
path traversal, request smuggling, injection, CSP bypasses, data exposure through
the API, and leaks of secrets into logs or the audit file.

Out of scope: findings that require administrative access to the host, physical
access, a compromised edge account, social engineering, and automated scanners'
informational output without a demonstrated impact.

## 6. Disclosure

Please give us a reasonable window to fix the issue before publishing details.
We will coordinate the disclosure date in the advisory. Security advisories are
published at the repository URL above.
