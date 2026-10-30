# Security Model — B2 First Tracker

## 1. Scope

This document covers the security of the B2 First Tracker as deployed on the public instance
(`https://vps-server.tail40095b.ts.net`) and for self-hosted installs. It describes what the
system protects, the threats it defends against, which controls are actually implemented, and
how to get the data back after a disaster.

**What the system protects:**

- **Study progress per user** — sessions, scores, error taxonomy, weekly plans, writing
  submissions and corrections. Each account has its own data directory; accounts cannot read
  each other.
- **Credentials** — account passwords (stored only as PBKDF2 hashes) and session tokens
  (stored only as SHA-256 hashes).
- **The AI provider key** — the owner's shared key used for corrections on the public instance,
  and any key a user brings for themselves.

**What it deliberately does not protect or contain:**

- **No payment data.** There is no payment flow anywhere in the product.
- **No personal data beyond the chosen display name.** No email, no real name, no address, no
  phone. Accounts are identified by a name the user invents.
- **No defence against a compromised host.** Anyone with shell access to the server can read
  `data/`. The model assumes the host and its operator are trusted.
- **The provider sees the text submitted for correction.** Only the essay text leaves the
  machine, together with the key being used; nothing else is sent anywhere.

**How to verify:**

- `bash tools/audit.sh` — 39 external checks against the public instance (TLS, HSTS/preload, CSP
  directives, COOP/CORP, `security.txt`, sensitive paths, method/traversal/body-limit probes,
  auth gates, CORS, banner hygiene). Every check prints PASS/FAIL and one line of evidence; the
  script exits non-zero on any regression.
- `python3 tools/verify_audit.py` — validates the SHA-256 hash chain of `data/audit.log` and
  exits non-zero if a line was edited, deleted or reordered.
- [docs/SECURITY-CHECKLIST.md](docs/SECURITY-CHECKLIST.md) — the ASVS 4.0.3 Level 2 table with
  PASS/FAIL/N-A per control, where it lives and how it is tested.
- `tests/test_security3.py` and the rest of `tests/` cover the same guarantees from the inside
  (re-hashing, absolute TTL, backoff, audit chain, payload limits, revocation, headers).

## 2. Threat model

| Asset | Threat | Control | Where in the code |
| --- | --- | --- | --- |
| Study progress | Files stolen or tampered with at rest | JSON files under `data/users/<id>/`; directories `0700`, files `0600`; atomic writes (tmp + `os.replace`); per-user write lock with 5 s timeout | `store.py`: `_write_json`, `_ensure_private_dir`, `_prog_lock` |
| Passwords | Offline cracking of `users.json` | PBKDF2-HMAC-SHA256, **600,000 iterations**, 16-char per-user salt; constant-time compare; SHA-256 legacy hashes and 200k PBKDF2 hashes are re-hashed to 600k on the next successful login (transparent: nobody is locked out) | `server.py`: `hash_password`, `_record_iterations`, `verify_password`, `_needs_rehash`, `login_user` |
| Session tokens | Theft from disk or replay after logout | Only `sha256(token)` is stored; 30-day **sliding** TTL capped by a 90-day **absolute** `absolute_exp` that is never extended; logout revokes; a password change revokes **every** session including the current one and returns a fresh token | `server.py`: `_token_key`, `new_token`, `auth_from_token`, `revoke_token`, `revoke_user_sessions`, `/api/password` |
| Accounts | Brute force / credential stuffing | 5 failed logins lock the username for 15 minutes **across IPs**; **exponential backoff** of 5 s / 15 s / 60 s after the 3rd/4th/5th failure; 10 logins / 10 min / IP and 20 / h / username | `server.py`: `_login_locked`, `_login_failed`, `LOGIN_BACKOFF`, `_login_delay`, `/api/login` |
| Username privacy | User enumeration via errors or timing | Identical "Wrong username or password." for unknown user and wrong password; the unknown-user path burns a full dummy PBKDF2; `hmac.compare_digest` everywhere | `server.py`: `login_user`, `verify_password`, `_dummy_digest` |
| Per-user data | IDOR: read/write another account's data by guessing its id | The session token must belong to the requested user (otherwise `403`); proxied requests without a token always get `401`; audit events are filtered to the caller | `server.py`: `/api/progress`, `/api/audit` |
| Server filesystem | Path traversal via `?user=` or `/files/` | User ids validated against `[A-Za-z0-9._-]{1,64}` with explicit `..` rejection (`400`); file routes `realpath` and require the result to stay inside their root | `store.py`: `_safe_uid`; `server.py`: `/files/`, `/assets/` |
| AI provider key | Key theft or free-riding | The key comes only from the environment (`B2_AI_KEY`, systemd `EnvironmentFile` outside the repo); never logged, never written to disk (`settings.aiKey` is stripped before persisting progress); 32 KB request cap | `server.py`: `/api/ai/writing`, `_validate_ai_payload` |
| AI budget | Draining the shared key | 10/min and 60/h per IP; per-account plan allowance (free 3/day, pro 60/month) + 80/day per instance; user-supplied keys bypass the shared quota; 25 s upstream timeout | `server.py`: `_check_ai_rate`, `_writing_gate`, `_ai_quota_*`, `AI_TIMEOUT`; `plans.py` |
| Activation codes | Guessing or replaying a pro code | HMAC-SHA256 over `plan\\|days\\|nonce` with a 32+ byte secret that lives only in the systemd environment; the ledger stores `sha256(code)` and never the code; single use; 5 attempts/hour/account; every failure returns the same `400 {"error":"invalid_code"}` | `plans.py`: `issue_code`, `verify_code`; `server.py`: `/api/plan/redeem` |
| Availability | DoS via oversized or malformed payloads | 2 MB progress cap + schema (lists ≤ 5000 items, strings ≤ 500/4000 chars, depth ≤ 6, finite numbers) → `422`; 300 requests/min/IP on `/api/*` → `429`; busy locks answer `429` instead of stacking | `server.py`: `_validate_progress`, `_rate`, `_drain`; `store.py`: `_locked` |
| Network surface | Slowloris, connection floods, oversized requests sent by hand | 15 s socket timeout per connection; global `BoundedSemaphore(200)` answers `503 {"error":"busy","retry_after":5}` + `Retry-After: 5` and closes; URI > 2048 → `414`, > 60 headers → `431`, `Content-Length` > 3 MB → `413` before reading the body; bind defaults to `127.0.0.1` (`B2_HOST`), optional `Host` allowlist (`B2_ALLOWED_HOSTS`) → `421` | `server.py`: `H.timeout`, `_CONN_SEM`, `_handle`, `_bad_path_code`, `_host_allowed`, `B2_HOST` |
| Request smuggling / traversal surface | Path traversal, encoded slash tricks, hidden-file probing, unknown verbs | Path rejected (`400`) for NUL, backslash, `..` in any encoding (single/double percent-encoded) and empty `//` segments; hidden dot-files → `403` with no content; method allowlist → `405` + `Allow` for everything else (including `TRACE`); 404 never lists candidates | `server.py`: `_bad_path_code`, `H.__getattr__`, `_method_not_allowed` |
| Browser sessions | XSS / CSRF | CSP (`default-src 'self'`, `frame-ancestors 'none'`, `base-uri 'none'`, `form-action 'self'`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; rendered names go through `html.escape`; auth is a `Bearer` header (no cookies) and CORS is closed, so there is no ambient credential for a cross-site request | `server.py`: `SECURITY_HEADERS`, `esc`, `OPTIONS` branch |
| Audit trail | Secrets leaking into logs; users reading each other's events; silent log tampering | Access log: method, path without query, status, request id — never tokens or bodies; `data/audit.log` holds events with user + ip only (`0600`, rotates at 5 MB) and **every line carries `prev` = SHA-256 of the previous raw line** (first line `0`×64), so edits/deletions break the chain; `/api/audit` returns only the caller's own events; `tools/verify_audit.py` checks the chain | `server.py`: `_log_line`, `_audit`, `_audit_prev`, `read_audit_events`, `/api/audit`; `tools/verify_audit.py` |
| Security events | Blind spots during abuse or provider misuse | Append-only events `ai_blocked`, `rate_limited_by_user`, `pa_rejected`, `token_minted`, `session_revoked` — each with `rid`, scalar metadata only, no content and no secrets | `server.py`: `_audit` call sites in `/api/ai/writing`, `_rate_limited`, `/api/speaking/pa`, `/api/speaking/token`, `/api/logout`, `/api/password`, `/api/account` |
| Disclosure metadata | No documented way to report a vulnerability | `/.well-known/security.txt` (RFC 9116): `Contact` (GitHub advisory form + documented `TODO_OWNER_EMAIL` placeholder), `Expires`, `Canonical`, `Policy` | `server.py`: `security_txt()`, route `/.well-known/security.txt` |
| Owner data (legacy path) | Tokenless reads from a request that bypasses the proxy | The no-token owner path is accepted only when the request carries no `X-Forwarded-For`/`X-Real-IP`; on the public instance every request arrives through the TLS proxy (which sets `X-Forwarded-For`), so the answer is `401`. Self-hosted installs must not publish the app port directly | `server.py`: `/api/progress` (tokenless owner branch) |

## 3. Controls implemented

| Control | Status | Notes |
| --- | --- | --- |
| Input validation | Implemented | `_validate_progress` (shape, list/string caps, depth, finite numbers), `_safe_uid` for ids, AI request and model-output schemas, password policy (10 characters, 200 common passwords, username check), diagnostic JSON validation |
| SQL injection | N/A (no database) | Storage is JSON read with `json.load`; there is no query language and no string-built SQL anywhere |
| Password hashing | Implemented | PBKDF2-HMAC-SHA256, **600,000 iterations**, per-user salt, constant-time compare; SHA-256 and 200k PBKDF2 hashes upgraded transparently on the next login; TTL/rehash policy covered by `tests/test_security3.py` |
| Session lifetime | Implemented | 30-day sliding `exp` capped by a 90-day `absolute_exp` per token; `auth_from_token` refuses and deletes tokens past either clock |
| Audit log integrity | Implemented | SHA-256 hash chain (`prev`) on every line; `tools/verify_audit.py` exits non-zero on a broken link; pre-chain history is reported as an unverifiable prefix (see residual risks) |
| Security headers | Implemented | HSTS `max-age=63072000; includeSubDomains; preload`; CSP `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`, `form-action 'self'`, no `'unsafe-eval'`; COOP/CORP `same-origin`; `Referrer-Policy: no-referrer`; `Permissions-Policy` scoped (`microphone=(self)` only on the tracker) |
| Body limits by route | Implemented | Global 3 MB ceiling checked from `Content-Length` before the body is read; `/api/speaking/pa` and `PUT /api/progress` reject > 2 MB the same way (`413`, connection closed, nothing drained) |
| Secrets outside the repo | Implemented | The AI key comes from the environment (systemd `EnvironmentFile`, chmod 600, outside the repo); the repo ships no credentials; `settings.aiKey` is stripped before persisting; keys are never logged |
| Server-side auth | Implemented | Every data route (`/api/me`, `/api/progress`, `/api/password`, `/api/account`, `/api/export`, `/api/audit`) validates the Bearer token on every request |
| Rate limit login / reset | Implemented | Login 10/10 min/IP + 20/h/username + 5-failure lockout; registration 5/h/IP; password change 5/h/IP. There is no remote password reset flow (no email to send to); recovery is the local CLI `tools/reset_password.py` |
| External timeouts | Implemented | Upstream AI call 25 s (`AI_TIMEOUT`); store locks fail after 5 s and answer `429` busy |
| Retries only on transient errors | Implemented | Nothing retries automatically: an upstream failure returns `502` once, and the client resubmits only on user action |
| Payment idempotency | N/A | There are no payment flows |
| Transactions (equivalent) | Implemented | Per-user locks around backup + write, atomic `os.replace` (tmp + rename) for every JSON write; concurrent writes serialize or get `429` |
| Indexes | N/A (no database) | JSON documents are read whole |
| N+1 queries | N/A (no database) | No queries at all |
| Connection pool | N/A (no database) | No database connections; stdlib `ThreadingHTTPServer` |
| Versioned migrations | Implemented | `store.py` keeps `PROGRESS_SCHEMA = 2`, upgrades older progress on read and copies the original to `backups/pre-migration-<ts>.json` first |
| No dropping columns in the same deploy | N/A (no database) | No schema to drop; unknown keys in progress payloads are preserved (forward compatible) |
| Logs with request id | Implemented | Every response carries `X-Request-Id`; the access log line and every audit event store the same `rid` |
| Health check | Implemented | `GET /api/health`: data dir writable, `users.json` parses, every user dir exists → `200 {"ok": true}` / `503` otherwise; absolute paths only with `B2_PUBLIC_HEALTH=1` |
| 429, not 500 | Implemented | Rate limits and lock contention answer `429` with `Retry-After`; `500` is reserved for unexpected exceptions, never for load |
| Backups + tested restore | Implemented | Per-save rotation (20 per user) and a daily verified tarball (14 kept); every backup run performs a test restore and parses every JSON file — see section 4 |
| CORS closed | Implemented | No `Access-Control-Allow-Origin` on any response; `OPTIONS` preflights answer `204` with no `access-control-allow-*` headers |
| A user cannot read another user's data by id | Implemented | Token↔user binding answers `403` across accounts, `/api/audit` filters to the caller's events, and `/api/users` exposes only the login directory fields (id, name, color, created) — no progress, no credentials |

**External audit status.** `bash tools/audit.sh` passes **39/39** checks against the public
instance as of 2026-10-30 (TLS and HTTP/2 included; against a plain `http://` target those two
report N/A and 37/37 pass). The former open finding (the `Server` banner disclosing the runtime)
is fixed: the banner is now `Server: B2First` with no version. The one control that is *not*
claimed as PASS is the strict CSP without `'unsafe-inline'`; see section 5.

## 4. Backups and restore

Backups are made at two levels:

1. **On every save.** Before a progress file is overwritten, the previous version is copied to
   `data/users/<id>/backups/progress-<timestamp>.json`, keeping the **20** most recent per user
   (`store.py`: `put_progress` → `backup`). Pre-migration copies are kept the same way.
2. **Daily job.** The systemd timer `b2f-backup.timer` (03:30, persistent, up to 5 min jitter)
   runs `~/.hermes/scripts/b2f_backup.sh`, which creates
   `~/b2first-backups/b2f-data-YYYYmmdd-HHMMSS.tgz` — a tar.gz of the whole `data/` directory.

**Verification on every run.** The job refuses to pass unless all of the following succeed,
and prints `B2F BACKUP FAIL: ...` otherwise:

- the tarball lists cleanly (`tar -tzf`),
- a **test restore** into a temporary directory extracts cleanly,
- **every `.json` file in the restored copy parses** with `json.load` (a single corrupt file
  fails the whole run).

**Retention: 14.** The 14 newest tarballs are kept (`KEEP=14`); older ones are deleted at the
end of each run. Every run appends one line to `~/b2first-backups/backup.log`
(timestamp, archive path, size, user count) — silence in stdout means success.

**Restore, step by step** (the data-manipulation steps were executed against a scratch copy of
the 2026-10-29 backup; only the `systemctl stop/start` of the live service is not part of the
drill):

```bash
# 0) stop writes while data/ is replaced
sudo systemctl stop b2first.service

# 1) keep the current data aside — never delete it
cd /home/juan/b2first-tracker
mv data data.broken-$(date +%Y%m%d-%H%M%S)

# 2) extract the chosen backup (the archive contains data/ at its root)
tar xzf /home/juan/b2first-backups/b2f-data-YYYYmmdd-HHMMSS.tgz -C /home/juan/b2first-tracker

# 3) restore private permissions
find data -type d -exec chmod 700 {} +
find data -type f -name '*.json' -exec chmod 600 {} +

# 4) start again and verify
sudo systemctl start b2first.service
curl -s https://vps-server.tail40095b.ts.net/api/health
# → {"ok": true, "users": N, ...}
```

**Restore drill, 2026-10-30** (`b2f-data-20261029-235446.tgz`, steps 1–3 on a scratch copy,
then a second instance booted on port 8199 against the restored data):

```
$ tar xzf b2f-data-20261029-235446.tgz -C <scratch>
extracted ok
$ python3 - <<'PY'  # parse every JSON in the restored copy
parsed=34 bad=0
$ find data -type d -exec chmod 700 {} +; find data -type f -name '*.json' -exec chmod 600 {} +
$ DATA_DIR=<scratch>/data PORT=8199 python3 server.py &
$ curl -s http://127.0.0.1:8199/api/health
{"ok": true, "users": 2, "data_dir": "data", "version": "1.0.0", "uptime_s": 1}
```

## 5. Residual risks (honest status)

These are known, accepted risks. They are listed so an auditor does not have to discover them,
and so the migration work is explicit.

### 5.1 CSP still needs `'unsafe-inline'` — **FAIL, not PASS**

The single-file UI (`index.html`, ~8,400 lines) has **197 inline event-handler attributes**:
`onclick` ×179, `onchange` ×13, `oninput` ×4, `onkeydown` ×4, `onload` ×1, `onerror` ×2. It
also uses inline `style` attributes, so `style-src` keeps `'unsafe-inline'` as well. Removing
those means rewriting the UI from inline handlers to `addEventListener` wiring; that is a
multi-day refactor, not something to fake with a header.

- **Impact:** if an attacker ever gets markup injected into the page, `'unsafe-inline'` lets
  injected script run in the app origin, where the session token lives in `localStorage`.
- **Mitigations already in place:** all dynamic names go through `html.escape`; student text
  and AI output are rendered with `textContent`, never `innerHTML`; there are no third-party
  scripts; `connect-src` is restricted (`'self'` + Gemini Live); `frame-ancestors 'none'`,
  `base-uri 'none'`, `object-src 'none'`.
- **What *is* enforced:** no `'unsafe-eval'`, no `object-src`, no `<base>` injection, no
  framing, forms only post to `'self'`.
- **Migration plan:** (1) extract the inline `<script>` to an external file; (2) replace each
  `on*=` with a delegated `addEventListener` using `data-action`; (3) move inline styles to
  classes; (4) switch to `script-src 'self'` and `style-src 'self'`; (5) add a CSP regression
  check to `tools/audit.sh` that fails if `'unsafe-inline'` reappears. Until then, the checklist
  row **CSP-1 (no unsafe-inline) is FAIL**.

### 5.2 Audit history written before the hash chain

`data/audit.log` lines created before phase 24 have no `prev` field. They are an **unverifiable
prefix**: `tools/verify_audit.py` reports them as such, verifies the transition into the first
chained line, and verifies every link from there on. An attacker who edited a line *before* the
upgrade cannot be detected retroactively. Rotation at 5 MB removes that prefix over time.

### 5.3 Host and operator are trusted

Anyone with shell access to the server can read `data/` and could rewrite the whole audit log
(a fresh, internally consistent chain is possible with write access). The hash chain detects
accidental or partial tampering and tampering by a process that lacks write access to the file;
it is not a defence against a compromised host.

### 5.4 No verified disclosure mailbox

There is no verified email address for this project. `/.well-known/security.txt` publishes the
GitHub advisory URL as the working `Contact` plus the documented `TODO_OWNER_EMAIL` placeholder.
Replace the placeholder with a real mailbox before claiming a mail contact.

### 5.5 Account recovery is local only

There is no email flow, so a forgotten password requires shell access to run
`tools/reset_password.py`. This is a deliberate consequence of not collecting personal data.

### 5.6 Password policy is below the ASVS L2 baseline

ASVS 4.0.3 asks for at least 12 characters (2.1.1) and a check against the top 3,000 breached
passwords (2.1.7). This product enforces **10 characters** and a **200-entry embedded blocklist**
(a deliberate constraint of phase 24: no downloaded wordlists, no dependencies). Both checklist
rows are marked **FAIL**, not PASS. Raising `PASSWORD_MIN_LEN` to 12 and loading a larger list is
a small, isolated change; it was not made here because the product requirement fixed 10/200.

### 5.7 Rotated audit history keeps only one file

`data/audit.log.1` is the single rotated file; when a second rotation happens the oldest segment
is deleted, so its hash-chain head becomes unverifiable. The current segment and the transition
remain verifiable. Longer retention would need a different sink (append-only object storage).

## 6. Reporting a vulnerability

Report security issues privately through GitHub's vulnerability reporting for this repository:

**https://github.com/Juan-Martin-Cerezo/b2first-tracker/security/advisories/new**

Machine-readable disclosure metadata: **https://vps-server.tail40095b.ts.net/.well-known/security.txt**
(RFC 9116). The `mailto:` line in that file is the documented `TODO_OWNER_EMAIL` placeholder
until a verified mailbox exists.

(If you cannot use advisories, open an issue with no details asking for a contact channel.)

What to expect:

- An acknowledgement within a few days.
- Confirmation of the issue and, when it is understood, a fix or a documented mitigation.
- Disclosure timing agreed with you before anything is published.
- Credit in the release notes if you want it.

This is a self-hosted, no-budget project: there is no bug bounty, but every report gets a real
answer. Please do not test against other users' accounts on the public instance — a PoC against
your own account is enough.
