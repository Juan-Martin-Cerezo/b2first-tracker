# 03 — Access Control

This document describes access as implemented and as configured in the repository. Host
state that could not be inspected is marked `unverified`.

## 1. Accounts and roles

| Role | Who | What they can do | Evidence |
| --- | --- | --- | --- |
| Anonymous | Anyone with the URL | Static pages, `/api/health`, `/.well-known/security.txt`; account registration if `B2_REGISTER=open`; manual recovery request | `server.py:4713-4715`, `4737-4749`; `docs/SECURITY-CHECKLIST.md` V13 |
| User (`free`) | Any registered account | Read/write **only their own** progress, export their own data, delete their own account, use the free plan allowance | `server.py:5033-5034`, `4958-5007`; `plans.py` `LIMITS` |
| Subscriber (`pro`) | Account with an active plan row (licence code or Stripe subscription) | Same as User, with the larger plan allowance | `plans.py:233-244`; `server.py:748-756` |
| Owner | Account whose id is in `B2_OWNER_UIDS` (default `owner`) | Unlimited plan caps; aggregate audit view; `/api/metrics` | `plans.py:221-230`, `233-243`; `server.py:4973-4978`, `6229-6231` |
| Administrator / examiner | **Does not exist** | — | No role model beyond the owner check (`server.py:6229`) |

There is no tenant, organisation, team, or delegated-administration concept. Every account
is an island; the owner is the only privileged account and is also the human operator.

## 2. Authentication

### 2.1 Password accounts (default)

- Hash: PBKDF2-HMAC-SHA256, 600,000 iterations, unique 16-character salt per account
  (`server.py:2139-2142`; `store.py:51`, `2345-2349`).
- Verification is constant-time (`hmac.compare_digest`, `server.py:2172-2176`).
- Unknown usernames burn the same PBKDF2 work as a real check (`server.py:2159-2166`,
  `2380-2382`).
- Legacy SHA-256 and 200k-iteration hashes are upgraded transparently on the next
  successful login (`server.py:2356-2392`); tests `tests/test_security3.py` D1/D2.
- Password change requires the current password, re-hashes, and revokes **every** session
  including the calling one, returning a fresh token (`server.py:2741-2761`,
  `4861-4870`; test `tests/test_security3.py` J1).
- Policy: minimum 10 characters, 1,000-entry embedded common-password list, password must
  not equal the username (`server.py:2289`, `2299-2307`; `store.py:53-56`). This is below
  ASVS L2 and is recorded as FAIL (R16).

### 2.2 Sessions

- 192-bit random token (`secrets.token_hex(24)`, `server.py:2194`).
- Only `sha256(token)` is written to `data/tokens.json` (`server.py:2126-2128`, `2195`).
- Two clocks: 30-day sliding expiry and a 90-day absolute ceiling that is never extended
  (`server.py:81-82`, `2180-2201`, `2204-2244`).
- Logout revokes one token; password change and account deletion revoke all
  (`server.py:2247-2268`, `2764-2776`).
- Transport is an `Authorization: Bearer` header, never a URL or cookie
  (`server.py:3908-3909`); CORS is closed (`docs/SECURITY-CHECKLIST.md` V3/V14).
- A User-Agent change is audited but not blocked (`server.py:2238-2240`) — accepted (R25).

### 2.3 Optional federated and passkey login

- Google OAuth authorisation-code + PKCE, server-side token exchange, `id_token` verified
  against Google JWKS with `iss`, `aud`, `exp`, `nonce` (`oauth_google.py:1-13`;
  `server.py:2399-2404`; test `tests/test_auth_methods.py`).
- WebAuthn passkeys: P-256 ECDSA assertion, RP-ID hash, challenge, origin and signature
  counter checks (`webauthn.py:291-310`, `375`; test `tests/test_auth_methods.py`).
- Both are optional. TOTP MFA is now available per account (`mfa.py`, `/api/mfa/*`,
  `tests/test_mfa.py`); there is no policy that **requires** a second factor yet (R17).

## 3. Authorisation

- Every data route calls `_auth()` and refuses without a valid token (`server.py:3930-3942`;
  `docs/SECURITY-CHECKLIST.md` V4).
- The token→user binding is enforced on `/api/progress`: a token belonging to another
  account gets 403 (`server.py:5033-5034`; `tests/test_multiuser.py` #6, #7).
- `/api/audit` and `/api/export` filter events to the caller's own id/name
  (`server.py:4968-4971`, `4992-4994`).
- `/api/metrics` and the aggregate audit block require uid `owner` (`server.py:6229-6231`,
  `4973`).
- The tokenless owner branch of `/api/progress` is accepted only for a direct, non-proxied
  loopback request; any `X-Forwarded-For`/`X-Real-IP` forces authentication
  (`server.py:5020-5034`; `tools/audit.sh` probes this).
- User ids are validated against `[A-Za-z0-9._-]{1,64}` with explicit `..` rejection
  (`store.py:58-75`); file routes use `realpath` containment (`server.py:4062-4112`).

## 4. Registration and recovery

- Registration is controlled by `B2_REGISTER` (`open` by default; `closed` returns 403) and
  limited to 5 attempts/hour/IP (`server.py:85`, `142-147`, `4741-4749`; test
  `tests/test_register.py`).
- There is no email address on file, so there is no self-service reset link.
- The login screen can file a manual request (name + optional contact), rate-limited to
  5/hour/IP, stored with a 16-character IP hash, capped at 500 lines / 90 days
  (`server.py:4879-4911`; `store.py:357-414`; test `tests/test_password_reset_request.py`).
- The operator resets the password from the host with `tools/reset_password.py`, which
  invokes the same hashing path and revokes all sessions. It never prints the hash.
- The request endpoint answers the same `200 {"ok": true}` for known and unknown names
  (no enumeration, `server.py:4910-4911`).

## 5. Host access (repository configuration and real status)

| Item | Documented / configured | Status |
| --- | --- | --- |
| Service user | `User=juan`, `WorkingDirectory=/home/juan/b2first-tracker` | Configured in `b2first.service:7-8`; actual host `unverified` |
| Privilege restriction | `NoNewPrivileges=true`, `PrivateTmp=true` | `b2first.service:14-15` |
| Filesystem sandbox | Production unit has **no** `ProtectSystem`, `ProtectHome` or `ReadWritePaths`; the demo unit has all three | Gap: production service can write anywhere juan can (`b2first.service` vs `b2first-demo.service:17-21`) |
| SSH | `passwordauthentication no`, `pubkeyauthentication yes`, `permitrootlogin without-password`, `maxauthtries 3`, `logingracetime 20`, `AllowUsers juan` | Asserted as expected by `tools/audit-host.sh`; the host was **not** audited in this phase (`unverified`) |
| Root SSH | Expected `root@10.0.1.*` only (Coolify bridge exception) | Encoded in `tools/audit-host.sh`; `unverified` |
| Brute-force protection | fail2ban `sshd` jail, maxretry 4, bantime 1 h | Expected by `tools/audit-host.sh`; `unverified` |
| Firewall | nftables `inet hardened` with `policy drop`; SSH source-qualified; Docker `DOCKER-USER` filter | Expected by `tools/audit-host.sh`; `unverified` |
| sudo | No `sudoers` policy or review is in the repository | `unverified` |
| Disk encryption | Explicitly **not enabled** (`docs/SECURITY.md §4`, `SECURITY.md §5.3`) | Confirmed gap |
| Secret files | `EnvironmentFile=-/home/juan/.config/b2first/ai.env` (service) or `/etc/b2first.env` (README), described as `chmod 600` | `b2first.service:11`; `README.md:219`; permissions `unverified` |
| Patching | Manual; `audit-host.sh` expects `unattended-upgrades` **off** | `tools/audit-host.sh` service block; `unverified` |

## 6. Least privilege — what exists and what is missing

**Exists**

- Application-level ownership checks on every data route.
- Hashed tokens and hashed IP addresses; no raw credentials on disk.
- Systemd `NoNewPrivileges` and `PrivateTmp` for the service.
- Key material kept in environment files outside the repository; `settings.aiKey` is
  stripped before progress is stored (`server.py:5064-5068`).
- Metrics and aggregate audit restricted to uid `owner`.
- `.gitignore` excludes `data/`, `*.key`, `*.crt` (`.gitignore`).

**Missing (documented gaps)**

- No MFA requirement; no hardware-key enforcement for the owner.
- No separate `admin` or `examiner` role; no delegated support access.
- No periodic access review, no joiner/mover/leaver process, no account inventory review.
- No production `ProtectSystem`/`ProtectHome` hardening in the systemd unit.
- The service runs as the same Unix user `juan` used for interactive login; no dedicated
  `b2first` system account.
- No documented sudo policy, SSH key inventory, or rotation record.
- No disk encryption; root on the host reads everything (R12).
- No documented rotation schedule for provider keys, licence secret, or OAuth secret.
- Account recovery relies on the operator's judgement with no recorded identity check (R24).

## 7. Periodic access review (quarterly)

**Who reviews:** the single owner/operator. There is no delegated reviewer (A.5.2).

**What is reviewed, every quarter:**

1. Every account in `data/users.json`: creation date, last recorded access, whether
   TOTP MFA is enabled, number of live sessions and internal plan.
2. Every token expiring within 7 days.
3. Every account with no recorded access in 90 days.

**Tool:** `tools/access_review.py` (read-only). It prints user ids as
`sha256(id)[:12]`, never the token, the full id, the password hash, the salt or
another account's progress. `--json` produces a deterministic snapshot for diffing:

```bash
python3 tools/access_review.py > review-$(date -u +%Y-%m-%d).md
python3 tools/access_review.py --json > review-$(date -u +%Y-%m-%d).json
python3 tools/access_review.py --json --diff review-previous.json
```

**What is done with a finding:**

- **Inactive account (90 days without access):** disable it for login by removing
  its sessions and marking the record; do **not** delete it without notice. Account
  deletion is irreversible and destroys progress, plan and backups, so it requires
  the owner's explicit decision and, where possible, contact with the account holder.
- **Token expiring within 7 days:** expected for idle sessions; no action unless the
  account is inactive.
- **MFA missing on an account that holds privileged access (the owner):** enable MFA
  or record an accepted risk with a date.
- **Unknown account:** investigate `data/audit.log` before changing anything.

**First review — 2026-11-18 (real run in this worktree):**

```
$ python3 tools/access_review.py
# Access review

Generated (UTC): 2026-11-18T21:06:28Z

| Account (id hash) | Created | Last access | MFA | Sessions | Plan | Inactive (d) |
| --- | --- | --- | --- | --- | --- | --- |

- Accounts: 0; MFA enabled: 0; inactive >= 90 days: 0.
- Tokens expiring within 7 days: 0.
```

This worktree has no production `data/` directory (it is gitignored), so the first
review found zero accounts. It proves the report runs and prints only hashed ids; it
does **not** constitute a review of the live instance. The next quarterly review must
run on the host's real `B2_DATA_DIR` and its output must be attached here.
