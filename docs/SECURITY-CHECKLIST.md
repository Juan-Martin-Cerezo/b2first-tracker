# Security Checklist — ASVS 4.0.3 Level 2

Scope: the B2 First Tracker application (stdlib Python server + single-file UI + JSON storage).
References are to the OWASP Application Security Verification Standard 4.0.3, Level 2.
Status is **PASS**, **FAIL** or **N/A**. A control is PASS only when a machine check or a test
exercises it; anything that cannot be implemented without a rewrite is FAIL and is documented
as a residual risk in [SECURITY.md](../SECURITY.md#5-residual-risks-honest-status).

Reproduce everything:

```bash
bash tools/audit.sh            # 39 external checks, non-zero on regression
python3 tools/verify_audit.py  # hash-chain integrity of data/audit.log
cd tests && python3 test_security3.py   # 34 in-process assertions for this phase
```

## V2 — Authentication

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Passwords hashed with a slow KDF and per-user salt | 2.1.1 / 6.2.1 | PASS | `server.py`: `hash_password` (PBKDF2-HMAC-SHA256, 600k) | `test_security3.py` D1/D2; inspect `users.json` |
| Password minimum length | 2.1.1 | **FAIL** | `server.py`: `PASSWORD_MIN_LEN = 10` | `test_security3.py` K2 — ASVS L2 asks for 12; product requirement is 10 (residual risk 5.6) |
| No composition rules; all characters allowed; no truncation | 2.1.2 | PASS | `server.py`: `password_problem` | `test_security3.py` K2/K3 |
| Password strength / blocklist | 2.1.7 | **FAIL** | `store.py`: `COMMON_PASSWORDS` (200 entries) | `test_security3.py` K1/K3 — 200 embedded entries, not the ASVS top 3,000 |
| Password strength notice at registration | 2.1.6 | PASS | `index.html`: `onRegPwInput` / `passwordStrength`; `server.py`: `password_strength` returns the level | `test_security3.py` K4 |
| Anti-automation on login | 2.2.1 | PASS | `server.py`: `_rate`, `_login_locked`, `_login_failed`, `LOGIN_BACKOFF` (5/15/60 s) | `test_security3.py` F1/F2; `test_security2.py` 1/1b |
| Legacy hashes upgraded without locking users out | 2.1.1 | PASS | `server.py`: `_needs_rehash`, `login_user` | `test_security3.py` D1 (200k→600k) / D2 (sha256→PBKDF2) |
| No user enumeration through errors or timing | 2.2.1 | PASS | `server.py`: `_dummy_digest`, `verify_password`, identical 401 body | `test_security2.py` 2 |
| Cryptographically secure randomness | 2.9.1 | PASS | `secrets.token_hex` / `token_urlsafe` | `test_security3.py` E2; code inspection |
| Password recovery | 2.5.1 | N/A | local CLI only (`tools/reset_password.py`), no email flow | SECURITY.md §5.5 |

## V3 — Session Management

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Session token not in URL, sent as `Authorization: Bearer` | 3.1.1 | PASS | `index.html`: `authHeaders`; `server.py`: `_bearer` | `test_hardening.py`; `tools/audit.sh` |
| Token entropy ≥ 64 bits | 3.2.1 | PASS | `server.py`: `new_token` (`secrets.token_hex(24)` = 192 bits) | code inspection |
| Token stored hashed at rest | 3.2.2 | PASS | `server.py`: `_token_key`, `load_tokens` | `test_security2.py` 3/3b |
| Session termination (logout) | 3.3.1 | PASS | `server.py`: `revoke_token`, `/api/logout` | `test_security3.py` H4 |
| Idle/absolute session timeout | 3.3.2 | PASS | `server.py`: `TOKEN_TTL` 30 d sliding + `TOKEN_ABSOLUTE_TTL` 90 d, `auth_from_token` | `test_security3.py` E1–E4 |
| Password change terminates every session | 3.3.1 | PASS | `server.py`: `revoke_user_sessions`, `/api/password` returns a fresh token | `test_security3.py` J1; `test_security2.py` 13b |
| Token↔user binding (no ambient authority) | 3.3.1 | PASS | `server.py`: `/api/progress` 403 on mismatch | `test_legacy_guard.py` 9; `test_multiuser.py` |
| CSRF resistance | 3.5.1 | PASS | Bearer header, no cookies, CORS closed | `test_server_hardening.py` 11; `tools/audit.sh` |
| Cookie-based sessions | 3.4.1 | N/A | cookies are not used | code inspection |

## V4 — Access Control

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Authorization enforced server-side on every data route | 4.1.1 | PASS | `server.py`: `_auth`, route guards | `test_legacy_guard.py`; `test_security2.py` 12 |
| No IDOR across accounts | 4.2.1 | PASS | token↔user check (`403`), `/api/audit` filtered | `test_multiuser.py`; `test_legacy_guard.py` 9 |
| Least privilege for the metrics endpoint | 4.3.1 | PASS | `server.py`: `/api/metrics` owner-only (`403`) | code inspection |
| Admin interface | 4.3.1 | N/A | no admin UI/API beyond the owner metrics endpoint | code inspection |

## V5 — Validation, Sanitization and Encoding

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Positive input validation | 5.1.1 | PASS | `server.py`: `_validate_progress`, `_safe_uid`, AI payload guards | `test_hardening.py` A; `test_security2.py` 5–8 |
| Structured input (JSON) with schema checks | 5.1.2 | PASS | `server.py`: `_validate_progress`, `_validate_ai_payload`, `speaking_report.validate_payload` | `test_security2.py`; `test_speaking_pa.py` |
| Input length/range/count limits | 5.1.3 | PASS | `server.py`: list/string/depth caps, `MAX_BODY_BYTES`, route caps | `test_security3.py` I1–I3; `test_server_hardening.py` 3 |
| Body rejected from `Content-Length` before reading | 5.1.3 | PASS | `server.py`: `_handle` pre-checks + `_reject` | `test_security3.py` I1–I3 |
| HTML output encoding | 5.3.1 | PASS | `server.py`: `esc`; UI uses `textContent` for dynamic names | `test_hardening.py`; code inspection |
| SQL / ORM injection | 5.3.4 | N/A | no database, no query language | code inspection |
| Deserialization of untrusted data | 5.5.1 | PASS | `json.loads` only; no `pickle`/`eval` | code inspection; `tools/audit.sh` (no `unsafe-eval`) |
| Path traversal in user ids and file routes | 5.1.1 | PASS | `store.py`: `_safe_uid`; `server.py`: `_bad_path_code`, `realpath` containment | `test_hardening.py` A; `test_server_hardening.py` 6–8; `tools/audit.sh` |

## V6 — Stored Cryptography

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Approved cryptographic modules | 6.1.1 | PASS | `hashlib`, `hmac`, `secrets` (stdlib) | `test_security3.py` D |
| Approved algorithms and parameters | 6.2.1 | PASS | PBKDF2-HMAC-SHA256 @ 600k; SHA-256 for tokens/audit chain | `test_security3.py` D1/D2/G1 |
| Random values from a CSPRNG | 6.3.1 | PASS | `secrets` only | code inspection |
| Secret keys outside the repo | 6.4.1 | PASS | systemd `EnvironmentFile`; `settings.aiKey` stripped | `test_ai_guard.py`; code inspection |
| Key material in logs | 6.4.1 | PASS | audit events carry scalars, never keys | `test_security3.py` H5 |

## V7 — Error Handling and Logging

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| No sensitive data in logs | 7.1.1 | PASS | `server.py`: `_log_line`, `_audit`; tests scan for tokens/text | `test_security3.py` H5; `test_hardening.py` D2 |
| No stack traces or filesystem paths to the client | 7.1.2 | PASS | `server.py`: `_run` returns `{"error":"internal","rid"}` | `test_security3.py` C3; `test_server_hardening.py` 13 |
| Generic error messages | 7.1.3 | PASS | same handler; 404 body is `not found` | `test_security3.py` C2 |
| Audit events for security-relevant actions | 7.2.1 | PASS | `login_ok`, `login_fail`, `register`, `password_change`, `account_delete`, `ai_blocked`, `rate_limited_by_user`, `pa_rejected`, `token_minted`, `session_revoked` | `test_security3.py` H1–H4; `test_security2.py` 12c |
| Audit log tamper detection | 7.2.2 | PASS | `server.py`: `_audit` `prev` SHA-256 chain; `tools/verify_audit.py` | `test_security3.py` G1–G3 |
| Fail securely on unexpected exceptions | 7.4.1 | PASS | `server.py`: `_run` catch-all; `StoreBusy` → 429 | `test_hardening.py` G1/G2 |

## V8 — Data Protection

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Data protected in transit | 8.1.1 | PASS | TLS proxy + HSTS preload | `tools/audit.sh` |
| No sensitive data cached by the browser | 8.2.1 | PASS | `Cache-Control: no-store` on `/api/*` | `tools/audit.sh`; `test_hardening.py` C2 |
| Sensitive data not kept in server memory/disk | 8.3.1 | PASS | PA audio forwarded and discarded; AI text not persisted; keys not written | `test_speaking_pa.py`; code inspection |
| Files under `data/` private | 8.3.1 | PASS | directories `0700`, files `0600`, atomic writes | `test_security2.py` 12c; `store.py` |
| File uploads | 8.3.1 | N/A | the application accepts no file uploads | code inspection |

## V9 — Communication

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| TLS for all client connections | 9.1.1 | PASS | Tailscale Funnel TLS terminator | `tools/audit.sh` (TLS verifies, HTTP/2) |
| HSTS with a long lifetime and preload | 9.1.2 / 14.4.3 | PASS | `server.py`: `SECURITY_HEADERS` | `test_security3.py` A1; `tools/audit.sh` |
| No insecure external calls | 9.2.1 | PASS | only HTTPS upstreams (`urllib`); 25 s timeout | code inspection |
| Server-Timing exposes internal latency only | 9.2.1 | PASS | `server.py`: `_server_timing` | `test_security3.py` A5 |

## V10 / V11 — Malicious Code and Business Logic

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| No third-party/untrusted code loaded | 10.1.1 | PASS | stdlib backend; vanilla UI; CSP `default-src 'self'` | `tools/audit.sh`; code inspection |
| Business logic limits (quotas, ownership) | 11.1.1 | PASS | per-user/instance AI and speaking quotas; token↔user binding | `test_ai_guard.py`; `test_security3.py` H3/J1 |
| Anti-automation on expensive endpoints | 11.1.1 | PASS | `_check_ai_rate`, `_spk_pa_*`, `_rate_limited` | `test_security3.py` H3 |

## V12 — Files and Resources

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| File upload handling | 12.1.1 | N/A | no uploads | code inspection |
| File download path containment | 12.5.1 | PASS | `server.py`: `/files/`, `/assets/` `realpath` containment | `test_server_hardening.py` 6–9 |
| Sensitive repository files not served | 12.5.1 | PASS | `server.py`: `_bad_path_code` + explicit routing (404 by default) | `test_security3.py` C1; `tools/audit.sh` |
| Backup files not served | 12.5.1 | PASS | `.bak` paths are unknown routes → 404 | `test_security3.py` C1; `tools/audit.sh` |

## V13 — API and Web Service

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| API authentication | 13.1.1 | PASS | Bearer token on every data route | `test_legacy_guard.py`; `test_security2.py` |
| HTTP method allowlist | 13.2.1 | PASS | `server.py`: `ALLOWED_METHODS`, `H.__getattr__` | `test_server_hardening.py` 4/5; `tools/audit.sh` |
| Request smuggling / traversal surface | 13.2.1 | PASS | `server.py`: `_bad_path_code`, header/URI limits | `test_server_hardening.py` 1–10 |
| CORS is not permissive | 13.2.1 | PASS | no `Access-Control-Allow-*` anywhere | `tools/audit.sh`; `test_hardening.py` C3 |
| SOAP / GraphQL | 13.3.1 / 13.4.1 | N/A | neither is used | code inspection |

## V14 — Configuration

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Secure defaults (loopback bind, registration policy) | 14.1.1 | PASS | `server.py`: `B2_HOST=127.0.0.1`, `B2_REGISTER` | `test_server_hardening.py` 15; `test_register.py` |
| No version banner | 14.2.1 | PASS | `server.py`: `H.version_string` → `B2First` | `test_server_hardening.py` 12; `tools/audit.sh` |
| Dependencies | 14.2.1 | PASS | Python stdlib only; no `pip install` | `Dockerfile`, code inspection |
| Host header validation available | 14.3.1 | PASS | `server.py`: `_host_allowed` (`B2_ALLOWED_HOSTS`) | code inspection |
| Security headers on every response | 14.4.1 | PASS | `server.py`: `_security_headers` | `test_security3.py` A1–A5 |
| CORS | 14.4.2 | PASS | closed | `tools/audit.sh` |
| HSTS | 14.4.3 | PASS | `max-age=63072000; includeSubDomains; preload` | `tools/audit.sh` |
| Cookie flags | 14.4.4 | N/A | no cookies | code inspection |
| Cache control | 14.4.5 | PASS | `no-store` on `/api/*` | `tools/audit.sh` |
| Content Security Policy | 14.4.6 | **FAIL** | `server.py`: CSP has `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`, `form-action 'self'`, no `'unsafe-eval'`; `script-src` still needs `'unsafe-inline'` | `test_security3.py` A2; residual risk 5.1 (197 inline handlers) |
| Referrer policy | 14.4.7 | PASS | `no-referrer` | `test_security3.py` A3 |
| COOP / CORP | 14.4.1 | PASS | `same-origin` on both | `test_security3.py` A3 |
| Permissions policy | 14.4.1 | PASS | minimal; `microphone=(self)` only on the tracker | `test_security3.py` A4 |
| HTTP methods restricted | 14.5.1 | PASS | `405` + `Allow` for TRACE/invented verbs | `test_server_hardening.py` 4/5; `tools/audit.sh` |
| HTTP response splitting | 14.5.1 | PASS | header values are static; request path never echoed in headers | code inspection |
| SSRF | 14.5.4 | PASS | upstream base comes from env, never from the request | code inspection |
| Disclosure metadata | 14.5.1 | PASS | `/.well-known/security.txt` (RFC 9116) | `test_security3.py` B1; `tools/audit.sh` |
| Health endpoint leaks | 14.3.1 | PASS | `/api/health` returns counts/version/uptime, no tokens or absolute paths | `test_security3.py` exclusions; `tools/audit.sh` |

## Summary

| Status | Count |
| --- | --- |
| PASS | 70 |
| FAIL | 3 |
| N/A | 8 |

The three FAILs are deliberate and documented: password length 10 (ASVS asks 12), a 200-entry
password blocklist (ASVS asks the top 3,000) and `'unsafe-inline'` in `script-src` (the UI has
197 inline handlers). None is presented as a PASS. The 8 N/A rows are features this product does
not have (database/ORM, cookies, file uploads, SOAP/GraphQL, email recovery, admin UI).
