# 04 — Incident Response

This is a single-operator plan. It defines what to do and where the evidence is; it does
not promise a response SLA. No incident has been exercised end-to-end in this phase.

## 1. Severity levels

| Level | Definition | Examples | Target first action |
| --- | --- | --- | --- |
| S1 Critical | Confirmed or likely unauthorised access to another person's data, credential compromise, or service-wide outage | Cross-account progress disclosure; owner password/token leaked; host root compromise; data directory deleted | Immediate (same day) |
| S2 High | A control is bypassed but no confirmed personal-data access; sustained abuse | Brute force succeeding on a weak account; AI key drained; audit chain broken; repeated 500s | Within 1 day |
| S3 Medium | Limited abuse or degradation with a workaround | Single-user rate-limit abuse; one provider down; backup job failed | Within 3 days |
| S4 Low | Hygiene or informational finding | Missing header; log rotation warning; dependency advisory without exploit path | Next maintenance window |

Severity is raised, never lowered, when personal data may have left the host. No numerical
SLA is claimed because there is one person; the target above is the internal goal.

## 2. Roles

| Function | Who | Notes |
| --- | --- | --- |
| Incident commander | Instance owner | Single person; no deputy |
| Investigator | Instance owner | Same person; no independent review |
| Communications | Instance owner | Advisory thread only; no press or regulator contact is defined |
| Legal / DPO | **Nobody** | No lawyer or DPO is named in the repository |
| Host administrator | Instance owner (`juan`) | Confirmed by `b2first.service:7-8`; actual sudo/SSH state `unverified` |

This concentration is a documented weakness (R12/R15): the person who can fix the incident
is also the person who could have caused it.

## 3. Evidence sources

Preserve evidence **before** fixing. Work on a copy; do not rewrite `data/` in place until
the copy is secured.

| Source | What it proves | How to collect |
| --- | --- | --- |
| `data/audit.log` (+ `.1`) | Security events with timestamp, request id, user, hashed IP, and a SHA-256 `prev` chain | Copy the files byte-for-byte; run `python3 tools/verify_audit.py <dir>`; record the output and the file hashes |
| Audit chain verifier | Whether a line was edited, deleted or reordered | `tools/verify_audit.py` exits 0 intact, 1 broken, 2 no log (`tools/verify_audit.py:1-20`) |
| `data/errors/YYYY-MM-DD.jsonl` | Unhandled exceptions with `rid`, path, truncated traceback, hashed IP | Copy the day files; correlate `rid` with the access log and audit |
| Access log (stdout / journal) | Method, path without query, status, duration, `rid`, truncated IP hash | `journalctl -u b2first` (unit name `b2first` per `b2first.service`); exact journal configuration `unverified` |
| `data/events/*.jsonl` | Whitelisted product events, salted IP hash | Copy; 7-day window only (`server.py:379-395`, `521-563`) |
| `data/tokens.json` | Which hashed sessions existed and when they expired | Copy; never print raw tokens (they are not stored) |
| `data/users/*/backups/` | Prior states of a progress document | Copy the account directory |
| Host backups | Pre-incident state | Location/retention `unverified` (`SECURITY.md §4`) |
| Git history | Which code version ran | `git log`, `git describe`; no signed tags or release attestations |
| Provider dashboards | Supplier-side access, spend, key use | Google, DeepSeek, Azure, Stripe, Cloudflare, Tailscale consoles — access is owner-held and `unverified` |

The audit chain detects partial tampering and tampering by a process without write access.
It **cannot** prove integrity against a compromised root user on the same host
(`SECURITY.md §5.3`) — treat host-root compromise as "evidence may be forged".

## 4. Playbooks

### 4.1 Suspected brute force / credential stuffing

1. Confirm the pattern in `data/audit.log`: `login_fail`, `login_ok`, `rate_limited_by_user`,
   source IP hashes (`server.py:4803`, `4808`).
2. If an account may be taken over: reset it locally with `tools/reset_password.py`, which
   revokes all sessions (`tools/reset_password.py`), and notify the user through the channel
   they used in a recovery request.
3. If the owner account is involved: rotate `B2_OWNER_PASSWORD`, all provider keys and the
   licence secret; restart the unit.
4. Consider raising rate limits/tightening `B2_REGISTER=closed` until the source stops.

### 4.2 Suspected token theft / session abuse

1. Identify the token by `sha256` prefix in `data/tokens.json` (never copy the raw token).
2. `session_revoked` and `ua_changed` events show rotation and client changes
   (`server.py:2240`, `4824`).
3. Revoke every session for that user (password change or account-level revocation).
4. If XSS is suspected, treat the CSP `'unsafe-inline'` gap (R02/R03) as the likely vector
   and search `data/errors/` and the UI for injected markup.

### 4.3 Suspected cross-user data exposure (IDOR)

1. Search `data/audit.log` for repeated `rid` values with 403s on `/api/progress`.
2. Confirm the build enforces the token↔user check (`server.py:5033-5034`); test with
   `tests/test_multiuser.py`.
3. Export the affected users' own audit events (`/api/audit`) and compare with the access
   log.
4. Notify affected users if any document was returned to the wrong account.

### 4.4 Data loss or corruption

1. Stop writes: `sudo systemctl stop b2first.service`.
2. Move `data/` aside; never delete it (`mv data data.broken-$(date +%Y%m%d-%H%M%S)`).
3. Restore per `06-BACKUP-RESTORE.md` and run `tools/restore_drill.sh` against the restored
   copy before starting.
4. Verify `/api/health` and a known account's progress; record the archive name used.

### 4.5 Host compromise

1. Isolate the host from the public edge (disable the tunnel/Funnel; the active edge is
   `unverified`, so document which one was disabled).
2. Treat all credentials as burned: AI keys, OAuth secret, Stripe keys, licence secret,
   owner password, SSH keys.
3. Preserve a disk image if possible; otherwise copy `data/`, the journal and the unit
   files before reinstalling.
4. Rebuild from a known-good image; do not trust a rewritten audit chain.

### 4.6 Supplier breach or unexpected supplier behaviour

1. Identify what the supplier held: writing text, speaking audio, email hash, billing ids
   (`05-SUPPLIERS.md`).
2. Revoke the provider key; disable the feature with its env switch (e.g. unset
   `B2_AI_KEY`, `B2_SPK_AZURE_KEY`, `B2_BILLING_MODE=off`).
3. Preserve the supplier's notice and the local request logs (`rid`, timestamps).
4. Assess whether personal data was involved and whether notification is required (legal
   advice `unverified`).

## 5. Preservation rules

- Do not run `tools/retention.py` during an incident: it deletes old audit lines and
  rewrites the chain (`tools/retention.py:87-166`).
- Do not delete an account during an incident: `_scrub_audit_user` rewrites the chain and
  removes the username (`server.py:3114-3134`).
- Record SHA-256 of every copied file, the tool versions, and the UTC timestamps of each
  action in the post-mortem.
- `data/audit.log` and `data/errors/` are `0600`; keep copies `0600` and outside the web
  root (the application never serves `data/`, `server.py:3337-3362`).

## 6. Disclosure

- Private advisory form (the only published channel):
  `https://github.com/Juan-Martin-Cerezo/b2first-tracker/security/advisories/new`
  (`docs/SECURITY.md §2`; `SECURITY.md §6`).
- Machine-readable metadata: `/.well-known/security.txt` (RFC 9116). It currently carries
  a `TODO_OWNER_EMAIL` placeholder — there is **no verified mailbox** (`SECURITY.md §5.4`).
- Do not publish exploit details or another user's data in an advisory.
- A reporter may request credit; the owner decides disclosure timing.

## 7. Regulatory and user notification

- The privacy policy names Argentina's Ley 25.326 and offers export/deletion
  (`docs/PRIVACY.md §11`); it makes no GDPR conformity claim.
- Any notification deadline (for example a 72-hour regulator window) requires legal advice
  that this repository does not contain. Marked `unverified`.
- User notification, if required, goes through whatever contact the user supplied in a
  recovery request or the advisory thread; there is no bulk email channel.

## 8. Post-mortem template

```
Incident ID:                IR-YYYYMMDD-NN
Severity:                   S1 / S2 / S3 / S4
Detected at (UTC):          ...
Detected by:                owner / user report / audit / monitoring (none) / supplier
Closed at (UTC):            ...
Summary (3 lines):

Affected assets:            A04 / A06 / ... (see 01-ASSET-INVENTORY.md)
Affected people (count):    ...
Data categories involved:   credentials / progress / transcripts / billing / none
Root cause:

Timeline (UTC, one line per action, with evidence path):

Evidence preserved:         files + sha256 + verify_audit.py output
Controls that worked:
Controls that failed:
Risk register updates:      R__ (new score / residual)
Corrective actions:         owner, due date, verification
User / regulator notice:    not required / sent YYYY-MM-DD / pending legal review
Lessons learned:
```

## 9. Contact register

| Party | Channel | Verified |
| --- | --- | --- |
| Instance owner | GitHub account `Juan-Martin-Cerezo` (repository owner) | Repository metadata only |
| Security reports | GitHub private advisory URL | Published in `docs/SECURITY.md` and `security.txt` |
| GitHub | `https://github.com/.../security/advisories/new` | Reachable by definition of the repository |
| Google / DeepSeek / Azure / Stripe / Cloudflare / Tailscale | Provider support consoles | Owner-held; contact details `unverified` |
| Hosting provider | Not identified in the repository | `unverified` |
| Users | Optional contact text in `data/pwreset.jsonl` | Only if the user chose to supply it |
