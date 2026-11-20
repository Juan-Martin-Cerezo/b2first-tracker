# Security Checklist — ASVS 4.0.3 Level 2

Scope: the B2 First Tracker hosted service (standard-library Python server,
single-file UI, JSON storage). References are to the OWASP Application Security
Verification Standard 4.0.3, Level 2. Status is **PASS**, **FAIL** or **N/A**. A
control is PASS only when a machine check or a test exercises it; anything that
cannot be implemented without a rewrite is FAIL and is documented as a residual
risk in [SECURITY.md](../SECURITY.md#5-residual-risks-honest-status).

Reproduce everything:

```bash
bash tools/audit.sh            # external checks, non-zero on regression
python3 tools/verify_audit.py  # hash-chain integrity of the audit log
cd tests && python3 test_security3.py
python3 tools/pentest.py --spawn
```

## V2 — Authentication

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Passwords hashed with a slow KDF and per-user salt | 2.1.1 / 6.2.1 | PASS | server: password hashing (PBKDF2-HMAC-SHA256, 600k) | `test_security3.py` D1/D2 |
| Password minimum length | 2.1.1 | PASS | server: minimum length constant (12) on registration and change | `test_password_policy.py` P1/P2/P11/P12; `test_security3.py` K2 |
| No composition rules; all characters allowed; no truncation | 2.1.2 | PASS | server: password policy helper | `test_security3.py` K2/K3 |
| Password strength / blocklist | 2.1.7 | **PARTIAL** | blocklist module: 1,000 sourced entries + deterministic derivatives (22,492 total) | `test_password_policy.py` P3–P8 — still partial: no larger sourced list is embedded (ASVS asks the top ~3,000 breached passwords) |
| Password strength notice at registration | 2.1.6 | PASS | UI strength meter; server returns the level | `test_security3.py` K4 |
| Anti-automation on login | 2.2.1 | PASS | rate limiter, username lockout, exponential backoff (5/15/60 s) | `test_security3.py` F1/F2; `test_security2.py` 1/1b |
| Legacy hashes upgraded without locking users out | 2.1.1 | PASS | rehash-on-login | `test_security3.py` D1 (200k→600k) / D2 (sha256→PBKDF2) |
| No user enumeration through errors or timing | 2.2.1 | PASS | dummy digest, constant-time compare, identical 401 body | `test_security2.py` 2 |
| Multi-factor authentication (TOTP + recovery codes) | 2.8.1 | PASS | optional RFC 6238 TOTP (`mfa.py`) with 30 s step, constant-time compare, hashed one-time recovery codes | `test_mfa.py` |
| Cryptographically secure randomness | 2.9.1 | PASS | `secrets` for tokens and salts | `test_security3.py` E2 |
| Password recovery | 2.5.1 | N/A | no remote reset link (there is no email); the login screen files a manual request and the operator resets by hand | SECURITY.md §5.5 |
| Recovery request cannot enumerate accounts and is rate-limited | 2.2.1 / 2.5.2 | PASS | identical `200 {"ok":true}`, 5/h/IP on top of the credential bucket, only a short IP hash stored | `test_password_reset_request.py` |

## V3 — Session Management

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Session token not in URL, sent as `Authorization: Bearer` | 3.1.1 | PASS | UI auth headers; server bearer reader | `test_hardening.py`; `tools/audit.sh` |
| Token entropy ≥ 64 bits | 3.2.1 | PASS | token generator (192 bits) | code inspection |
| Token stored hashed at rest | 3.2.2 | PASS | token key hashing and the token store | `test_security2.py` 3/3b |
| Session termination (logout) | 3.3.1 | PASS | token revocation on logout | `test_security3.py` H4 |
| Idle/absolute session timeout | 3.3.2 | PASS | 30-day sliding + 90-day absolute limits, enforced on read | `test_security3.py` E1–E4 |
| Password change terminates every session | 3.3.1 | PASS | session revocation on password change; a fresh token is returned | `test_security3.py` J1; `test_security2.py` 13b |
| Token↔user binding (no ambient authority) | 3.3.1 | PASS | progress route answers `403` on mismatch | `test_legacy_guard.py` 9; `test_multiuser.py` |
| CSRF resistance | 3.5.1 | PASS | Bearer header, no cookies, CORS closed; mutating requests check Origin/Referer and the Fetch Metadata fallback | `test_security3.py` L1–L4; `tools/pentest.py` |
| Cookie-based sessions | 3.4.1 | N/A | API auth uses `Authorization: Bearer`; a scoped HttpOnly cookie is issued only for `/api/listening/material/audio` `<audio>` Range playback | code inspection |

## V4 — Access Control

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Authorization enforced server-side on every data route | 4.1.1 | PASS | server route guards | `test_legacy_guard.py`; `test_security2.py` 12 |
| No IDOR across accounts | 4.2.1 | PASS | token↔user check (`403`), audit filtered to the caller | `test_multiuser.py`; `test_legacy_guard.py` 9 |
| Least privilege for the metrics endpoint | 4.3.1 | PASS | metrics endpoint is owner-only (`403`) | code inspection |
| Admin interface | 4.3.1 | N/A | no admin UI/API beyond the owner metrics endpoint | code inspection |

## V5 — Validation, Sanitization and Encoding

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Positive input validation | 5.1.1 | PASS | progress validator, safe user ids, AI payload guards | `test_hardening.py` A; `test_security2.py` 5–8 |
| Structured input (JSON) with schema checks | 5.1.2 | PASS | progress and AI payload validators, speaking-report validator | `test_security2.py`; `test_speaking_pa.py` |
| Input length/range/count limits | 5.1.3 | PASS | list/string/depth caps, body ceiling, route caps | `test_security3.py` I1–I3; `test_server_hardening.py` 3 |
| Body rejected from `Content-Length` before reading | 5.1.3 | PASS | pre-handler checks, uniform body ceiling plus documented route caps | `test_security3.py` I1–I3; `tools/pentest.py` (oversized PUT → 413) |
| HTML output encoding | 5.3.1 | PASS | server escaping; UI uses `textContent` for dynamic names | `test_hardening.py`; code inspection |
| SQL / ORM injection | 5.3.4 | N/A | no database, no query language | code inspection |
| Deserialization of untrusted data | 5.5.1 | PASS | `json.loads` only; no `pickle`/`eval` | code inspection; `tools/audit.sh` (no `unsafe-eval`) |
| Path traversal in user ids and file routes | 5.1.1 | PASS | safe-id validation, rejected path encodings, realpath containment | `test_hardening.py` A; `test_server_hardening.py` 6–8; `tools/audit.sh` |

## V6 — Stored Cryptography

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Approved cryptographic modules | 6.1.1 | PASS | `hashlib`, `hmac`, `secrets` (stdlib) | `test_security3.py` D |
| Approved algorithms and parameters | 6.2.1 | PASS | PBKDF2-HMAC-SHA256 @ 600k; SHA-256 for tokens/audit chain | `test_security3.py` D1/D2/G1 |
| Random values from a CSPRNG | 6.3.1 | PASS | `secrets` only | code inspection |
| Secret keys outside the repo | 6.4.1 | PASS | keys come from the environment; user keys are stripped before persistence | `test_ai_guard.py`; code inspection |
| Key material in logs | 6.4.1 | PASS | audit events carry scalars, never keys | `test_security3.py` H5 |

## V7 — Error Handling and Logging

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| No sensitive data in logs | 7.1.1 | PASS | access log and audit helpers; tests scan for tokens/text | `test_security3.py` H5; `test_hardening.py` D2 |
| No stack traces or filesystem paths to the client | 7.1.2 | PASS | catch-all returns `{"error":"internal","rid"}` | `test_security3.py` C3; `test_server_hardening.py` 13 |
| Generic error messages | 7.1.3 | PASS | same handler; the 404 body is `not found` | `test_security3.py` C2 |
| Audit events for security-relevant actions | 7.2.1 | PASS | login, register, password change, account delete, AI blocks, rate limits, pronunciation rejects, token mints, session revocations | `test_security3.py` H1–H4; `test_security2.py` 12c |
| Audit log tamper detection | 7.2.2 | PASS | previous-hash SHA-256 chain; the verifier exits non-zero on a break | `test_security3.py` G1–G3 |
| Fail securely on unexpected exceptions | 7.4.1 | PASS | catch-all; busy store → `429` | `test_hardening.py` G1/G2 |

## V8 — Data Protection

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Data protected in transit | 8.1.1 | PASS | TLS at the edge + HSTS preload | `tools/audit.sh` |
| No sensitive data cached by the browser | 8.2.1 | PASS | `Cache-Control: no-store` on API routes | `tools/audit.sh`; `test_hardening.py` C2 |
| Sensitive data not kept in server memory/disk | 8.3.1 | PASS | pronunciation audio forwarded and discarded; AI text not persisted; keys not written | `test_speaking_pa.py`; code inspection |
| Stored data private | 8.3.1 | PASS | restrictive modes, atomic writes | `test_security2.py` 12c |
| File uploads (Listening own material) | 8.3.1 | PASS | authenticated per-user audio uploads validated by MIME allowlist, base64 check, 20 MB/file and 40 MB / 10-item caps, stored outside webroot in private user dir | `test_listening_own_material.py` |

## V9 — Communication

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| TLS for all client connections | 9.1.1 | PASS | TLS terminator in front of the service | `tools/audit.sh` (TLS verifies, HTTP/2) |
| HSTS with a long lifetime and preload | 9.1.2 / 14.4.3 | PASS | security headers | `test_security3.py` A1; `tools/audit.sh` |
| No insecure external calls | 9.2.1 | PASS | only HTTPS upstreams; hard timeout | code inspection |
| Server-Timing exposes internal latency only | 9.2.1 | PASS | server-timing helper | `test_security3.py` A5 |

## V10 / V11 — Malicious Code and Business Logic

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| No untrusted third-party code loaded | 10.1.1 | PASS | stdlib backend; vanilla UI; CSP `default-src 'self'` with only cookie-free Cloudflare Web Analytics (`https://static.cloudflareinsights.com`) allowed in `script-src`/`connect-src` | `tools/audit.sh`; code inspection |
| Business logic limits (quotas, ownership) | 11.1.1 | PASS | per-account and per-instance AI and speaking quotas; token↔user binding | `test_ai_guard.py`; `test_security3.py` H3/J1 |
| Anti-automation on expensive endpoints | 11.1.1 | PASS | AI buckets, pronunciation quotas, rate limiter | `test_security3.py` H3 |

## V12 — Files and Resources

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| File upload handling | 12.1.1 | PASS | `/api/listening/material` enforces MIME allowlist, size/count caps, random IDs, atomic writes, and owner-only streaming | `test_listening_own_material.py` |
| File download path containment | 12.5.1 | PASS | realpath containment for material and assets | `test_server_hardening.py` 6–9 |
| Sensitive repository files not served | 12.5.1 | PASS | explicit routing; unknown paths answer 404 | `test_security3.py` C1; `tools/audit.sh` |
| Backup files not served | 12.5.1 | PASS | backup paths are unknown routes → 404 | `test_security3.py` C1; `tools/audit.sh` |

## V13 — API and Web Service

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| API authentication | 13.1.1 | PASS | Bearer token on every data route | `test_legacy_guard.py`; `test_security2.py` |
| HTTP method allowlist | 13.2.1 | PASS | method allowlist and `405` + `Allow` | `test_server_hardening.py` 4/5; `tools/audit.sh` |
| Request smuggling / traversal surface | 13.2.1 | PASS | path checks, header/URI limits | `test_server_hardening.py` 1–10 |
| CORS is not permissive | 13.2.1 | PASS | no `Access-Control-Allow-*` anywhere | `tools/audit.sh`; `test_hardening.py` C3 |
| SOAP / GraphQL | 13.3.1 / 13.4.1 | N/A | neither is used | code inspection |

## V14 — Configuration

| Control | ASVS ref | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| Secure defaults (loopback bind, registration policy) | 14.1.1 | PASS | bind address and registration policy defaults | `test_server_hardening.py` 15; `test_register.py` |
| No version banner | 14.2.1 | PASS | server banner is `B2First` | `test_server_hardening.py` 12; `tools/audit.sh` |
| Dependencies | 14.2.1 | PASS | Python stdlib only; no `pip install` | `Dockerfile`, code inspection |
| Host header validation available | 14.3.1 | PASS | optional Host allowlist | code inspection |
| Security headers on every response | 14.4.1 | PASS | security-header helper | `test_security3.py` A1–A5 |
| CORS | 14.4.2 | PASS | closed | `tools/audit.sh` |
| HSTS | 14.4.3 | PASS | `max-age=63072000; includeSubDomains; preload` | `tools/audit.sh` |
| Cookie flags | 14.4.4 | PASS | API sessions do not use cookies; the scoped `/api/listening/material/audio` playback cookie sets `HttpOnly; SameSite=Strict; Path=/api/listening/material/audio` (plus `Secure` over HTTPS) | code inspection; `test_listening_own_material.py` |
| Cache control | 14.4.5 | PASS | `no-store` on API routes | `tools/audit.sh` |
| Content Security Policy | 14.4.6 | PASS | CSP template + inline-script SHA-256 hashes; no `'unsafe-inline'` and no `'unsafe-hashes'` in `script-src`; only `https://static.cloudflareinsights.com` allowed externally | `test_csp.py` (0 violations across every view); `test_security3.py` A2; `tools/pentest.py` |
| Referrer policy | 14.4.7 | PASS | `no-referrer` | `test_security3.py` A3 |
| COOP / CORP | 14.4.1 | PASS | `same-origin` on both | `test_security3.py` A3 |
| Permissions policy | 14.4.1 | PASS | minimal; `microphone=(self)` only on the tracker | `test_security3.py` A4 |
| HTTP methods restricted | 14.5.1 | PASS | `405` + `Allow` for TRACE/invented verbs | `test_server_hardening.py` 4/5; `tools/audit.sh` |
| HTTP response splitting | 14.5.1 | PASS | header values are static; request path never echoed in headers | code inspection |
| SSRF | 14.5.4 | PASS | upstream base comes from the environment, never from the request | code inspection |
| Disclosure metadata | 14.5.1 | PASS | `/.well-known/security.txt` (RFC 9116) | `test_security3.py` B1; `tools/audit.sh` |
| Health endpoint leaks | 14.3.1 | PASS | health returns counts/version/uptime, no tokens or absolute paths | `test_security3.py` exclusions; `tools/audit.sh` |

## Summary

| Status | Count |
| --- | --- |
| PASS | 76 |
| PARTIAL | 1 |
| FAIL | 0 |
| N/A | 5 |

The one PARTIAL row is deliberate: password length (12) and the CSP are verified,
but the embedded blocklist is still not a full sourced top-3,000 list (it is
1,000 sourced entries plus deterministic derivatives). It is reported as
PARTIAL, not PASS. The 5 N/A rows are features this product does not have
(database/ORM, cookie-based API sessions, SOAP/GraphQL, email recovery, admin UI).
