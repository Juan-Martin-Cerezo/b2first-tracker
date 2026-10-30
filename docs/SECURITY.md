# Security Policy — B2 First Tracker

**Version 1.0** · Last updated: 2026-10-30 · Served live at `/security`

**Changelog**

- 1.0 — 2026-10-30 · First published security policy and disclosure process.

## 1. What this service is

A self-hosted study application running on a single Raspberry Pi in Argentina.
Public traffic reaches it through a **Cloudflare** tunnel; TLS terminates at
Cloudflare's edge and a QUIC tunnel carries the request to the origin on
`127.0.0.1`. The application itself is Python's standard library HTTP server —
no framework, no database, no container orchestration.

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

- Passwords: PBKDF2-HMAC-SHA256, 600,000 iterations, unique 128-bit salt,
  constant-time comparison. Hashes below the current cost are upgraded on login.
  The 1,000 most common passwords, passwords equal to the username, and anything
  shorter than 10 characters are rejected.
- Sessions: 192-bit random tokens; only `sha256(token)` is stored; 30-day sliding
  expiry capped by a 90-day absolute ceiling; every session is revoked on a
  password change; a User-Agent change is logged but not blocked.
- Storage: `data/users.json`, `data/tokens.json`, `data/usage.json`,
  `data/licenses.json` and `data/audit.log` are `0600`; per-account directories
  are `0700`; writes are atomic (temporary file + rename).
- Audit: append-only JSON lines with a SHA-256 hash chain. `tools/verify_audit.py`
  exits non-zero if a line is edited or deleted. Retention is 90 days.
- Access log: method, path, status, duration, request id and a truncated hash of
  the client address. Never the raw IP, never a token, never a request body.
- Rate limits: registration, login (per IP and per username, with lockout and
  backoff), progress writes, AI calls and speaking minutes.
- Transport: HSTS, no version banner, restrictive CSP, `X-Frame-Options: DENY`,
  `nosniff`, `no-referrer`, closed CORS, Host allowlist and path traversal
  checks. Cloudflare sees plaintext requests at the edge (see `/privacy`).

## 4. What is intentionally not protected

- **The host is the trust boundary.** Anyone with root on the Pi can read the
  data. Disk encryption is not enabled.
- **The AI providers receive what you send them.** Writing text goes to
  DeepSeek (or the configured provider); live speaking audio goes from your
  browser directly to **Google**; pronunciation clips go to Azure when enabled.
  Their handling is governed by their own terms.
- **Cloudflare is in the request path.** It terminates TLS and can see request
  bodies in plaintext.
- **No email recovery.** A lost password requires local access to the host.
- **Backups are daily and rotated.** A deleted account can persist in a host
  backup for up to 14 days.

## 5. Scope

In scope: authentication and session handling, access control between accounts,
path traversal, request smuggling, injection, CSP bypasses, data exposure through
`/api/*`, and leaks of secrets into logs or the audit file.

Out of scope: findings that require root on the host, physical access, a
compromised Cloudflare account, social engineering, and automated scanners'
informational output without a demonstrated impact.

## 6. Disclosure

Please give us a reasonable window to fix the issue before publishing details.
We will coordinate the disclosure date in the advisory. Security advisories are
published at the repository URL above.
