# 07 — Annex A Mapping (ISO/IEC 27001:2022)

Scope: the controls of Annex A that are applicable to this system and this one-person
organisation. Status is one of:

- **Implementado** — a verifiable artefact exists (code, test, script, or recorded run).
- **Parcial** — something real exists, but a required part is missing or unverified.
- **Gap** — no verifiable artefact; or the only evidence is prose that cannot be checked.

Rule applied: if the evidence is only a statement in a document that cannot be reproduced,
the row is **Gap**, not Parcial. No row claims conformity. `unverified` in the evidence
column means the item could not be checked from this repository or host.

## Summary

| Status | Count |
| --- | --- |
| Implementado | 4 |
| Parcial | 35 |
| Gap | 27 |
| **Total applicable** | **66** |

Non-applicable controls are listed separately in §4; they are excluded from the counts.

## 1. Organisational controls (A.5)

| Control | Status | Evidence | Missing action |
| --- | --- | --- | --- |
| A.5.1 Policies for information security | Parcial | `SECURITY.md`, `docs/SECURITY.md`, `docs/PRIVACY.md`, this ISMS directory | No approved policy set, version control of approvals, or management sign-off; no review cadence |
| A.5.2 Roles and responsibilities | Parcial | Single-owner model documented in `00-SCOPE.md §2`, `03-ACCESS-CONTROL.md §2` | No written role assignment or acknowledgement; no segregation of duties |
| A.5.5 Contact with authorities | Gap | None | No authority contacts or notification procedure |
| A.5.7 Threat intelligence | Gap | None | No threat-intel source or review |
| A.5.9 Inventory of assets | Parcial | `01-ASSET-INVENTORY.md` now lists assets, classes and retention | No per-asset custodian, no periodic verification; host backup location `unverified` |
| A.5.10 Acceptable use | Gap | None | No acceptable-use policy for the host, keys, or data |
| A.5.12 Classification of information | Parcial | Classification scale and per-asset class in `01-ASSET-INVENTORY.md` | Not applied at runtime or to logs; no labelling |
| A.5.13 Labelling of information | Gap | None | No labels in files, logs, or exports |
| A.5.14 Information transfer | Parcial | TLS-only upstreams; privacy disclosure of transfers (`docs/PRIVACY.md §4`; `server.py:168`) | No transfer policy, DPA, or approved-channel list |
| A.5.15 Access control | Parcial | Enforced token↔user check (`server.py:5033-5034`), owner-only routes (`server.py:6229-6231`); quarterly procedure plus a review **executed on production data 2026-11-19** (34 accounts, none inactive 90+ d) in `03-ACCESS-CONTROL.md` (Review #1); read-only report `tools/access_review.py`; storage at 0700/0600 verified by `tools/check_perms.sh` (73 dirs, 263 files, exit 0) | No formal approval signature and no independent reviewer; the operator reviews their own accounts |
| A.5.16 Identity management | Parcial | Account creation/deletion (`server.py:2327-2353`, `2764-2776`), unique ids, revocation | No identity lifecycle review; no joiner/mover/leaver process |
| A.5.17 Authentication information | Parcial | PBKDF2-HMAC-SHA256 600k + per-account salt (`server.py:2139-2142`), hashed tokens (`server.py:2126-2128`), rehash on login (`server.py:2356-2392`), TOTP secrets and hashed recovery codes (`mfa.py:64-112`, `server.py:957-1082`), tests D1/D2 and `tests/test_mfa.py` | No key/secret rotation schedule for provider keys, licence secret or OAuth secret |
| A.5.18 Access rights | Parcial | Password change and deletion revoke sessions (`server.py:2247-2268`, `2764-2776`); tests J1; quarterly rights report with inactive-account action (`03-ACCESS-CONTROL.md §7`, `tools/access_review.py:35-36`) | No completed production review or record of a disabled account yet |
| A.5.19 Supplier relationships | Parcial | `05-SUPPLIERS.md`; technical mitigations (webhook HMAC, JWKS, PKCE) | No DPA, security questionnaire, or supplier review cadence |
| A.5.20 Supplier agreements | Gap | None in the repository | No contracts or security clauses recorded |
| A.5.21 ICT supply-chain security | Gap | None | No supply-chain policy; base image tag is mutable |
| A.5.22 Monitoring/review of suppliers | Gap | None | No supplier monitoring |
| A.5.23 Cloud services security | Parcial | Edge and provider data flows documented (`00-SCOPE.md`, `05-SUPPLIERS.md`) | No cloud security policy; active edge `unverified` |
| A.5.24 IR planning | Parcial | `04-INCIDENT-RESPONSE.md` (severities, playbooks, evidence) | Never exercised; no on-call or deputy |
| A.5.25 Assessment of security events | Parcial | Severity table and evidence sources in `04-INCIDENT-RESPONSE.md` | No practice or recorded assessment |
| A.5.26 Response to incidents | Parcial | Playbooks in `04-INCIDENT-RESPONSE.md` | No tested response; roles concentrated in one person |
| A.5.27 Learning from incidents | Gap | Only a template in `04-INCIDENT-RESPONSE.md §8` | No completed post-mortem or corrective-action tracking |
| A.5.28 Collection of evidence | Parcial | Hash-chained audit (`server.py:3021-3090`) + verifier (`tools/verify_audit.py`) + tests G1–G3 | Host root can forge the chain (`SECURITY.md §5.3`); no forensic procedure tested |
| A.5.29 Continuity of operations | Gap | None | No BCP/DR plan; RTO untested (`06-BACKUP-RESTORE.md`) |
| A.5.30 ICT readiness for continuity | Gap | None | No readiness test or plan |
| A.5.31 Legal requirements | Parcial | `docs/PRIVACY.md`, `docs/TERMS.md`, `legal.py`; Ley 25.326 referenced | Legal review and jurisdiction analysis `unverified` |
| A.5.32 Intellectual property rights | Gap | `LICENSE` is MIT, but provenance of study `material/` is `unverified` | No IP inventory or licence review for third-party content |
| A.5.33 Protection of records | Parcial | `0600`/`0700` files (`store.py:160-195`) verified by `tools/check_perms.sh` (exit 0 on 2026-11-18), encrypted archive (`tools/backup_offsite.sh:58`), retention tool (`tools/retention.py`) | Off-host copy still pending; host backup retention has no purge tool; `data/errors/` has no retention |
| A.5.34 Privacy and PII protection | Parcial | Data minimisation, export and deletion (`docs/PRIVACY.md §3, §7`; `server.py:4914-5007`); tests `test_multiuser.py` #15/#16 | No DPA, DPIA, or verified legal basis; recovery contact is free text |
| A.5.36 Compliance review | Gap | None | No periodic compliance review |

## 2. People controls (A.6)

| Control | Status | Evidence | Missing action |
| --- | --- | --- | --- |
| A.6.1 Screening | Gap | One-person project; no screening record | Document the absence or apply a proportionate check |
| A.6.3 Awareness and training | Gap | None | No security training material or record |
| A.6.5 Responsibilities after termination | Gap | None | No offboarding checklist for keys/access |
| A.6.8 Reporting of security events | Gap | External advisory URL exists (`docs/SECURITY.md §2`), but no internal reporting procedure | Define and record an internal event-reporting path |

## 3. Technological controls (A.8)

| Control | Status | Evidence | Missing action |
| --- | --- | --- | --- |
| A.8.1 User endpoint devices | Gap | None; endpoints are out of scope | State the endpoint responsibility or provide guidance |
| A.8.2 Privileged access rights | Gap | Service runs as `juan` (`b2first.service:7-8`); no disk encryption; no sudo review | Dedicated service account, `ProtectSystem`, disk encryption, sudo inventory |
| A.8.3 Information access restriction | Implementado | Token↔user 403 (`server.py:5033-5034`), audit/export filtered (`server.py:4968-4971`, `4992-4994`), owner-only metrics (`server.py:6229-6231`), `realpath` containment (`server.py:4062-4112`); tests `test_multiuser.py` #6/#7, `test_legacy_guard.py` | Keep the check on every new data route; add a regression test for each |
| A.8.5 Secure authentication | Implementado | PBKDF2 600k, hashed tokens, 30/90-day TTL, passkeys and OAuth (`server.py:2126-2244`, `oauth_google.py`, `webauthn.py`); TOTP RFC 6238 with ±1 step, single-use 5-minute login ticket and one-time recovery codes (`mfa.py:64-112`, `server.py:951-1082`, `server.py:5622-5755`); tests E1–E4, J1, `test_auth_methods.py`, `tests/test_mfa.py` (31 checks) | MFA is per-account, not enforced: requiring it for the owner is an open decision under R17 |
| A.8.6 Capacity management | Parcial | Connection semaphore and backlog (`server.py:107-109`), rate limits (`server.py:279-345`), body caps (`server.py:116`, `3964-3981`) | No resource monitoring or capacity review |
| A.8.7 Protection against malware | Gap | None on the host; application is stdlib-only but that is not a malware control | Host malware/EDR posture `unverified`; define one |
| A.8.8 Technical vulnerability management | Parcial | Patch procedure and register (`docs/internal/SDLC.md §4`, `docs/internal/PATCH-LOG.md` with real commits and tests); release gate `tools/preflight.sh:109-114` | No scheduled CVE scan, no dependency/base-image rebuild cadence |
| A.8.9 Configuration management | Parcial | Units (`b2first.service`, `b2first-demo.service`), env documented (`README.md:225-300`), `.gitignore` | No configuration baseline; production unit lacks `ProtectSystem`/`ProtectHome` |
| A.8.10 Information deletion | Parcial | Account deletion removes user dir, tokens, plan, OAuth, passkeys (`server.py:2764-2776`, `4935-4954`); tests `test_multiuser.py` #15 | Host backups retain deleted data for up to 14 days (`unverified`); `data/errors/` never pruned; no secure-erase procedure |
| A.8.11 Data masking | Parcial | Hashed IP (`server.py:367-369`), hashed UA (`server.py:2131-2133`), hashed email option (`docs/PRIVACY.md §2`), `sha256(code)` for licences (`plans.py:515-516`) | Submitted writing/transcript content is not masked before leaving to suppliers |
| A.8.12 Data leakage prevention | Parcial | No content in audit/events (`server.py:3051-3069`; tests `test_security3.py` H5, `test_telemetry.py`); CSP restricts sources; no third-party scripts | No DLP tooling; CSP still allows `'unsafe-inline'` (R03) |
| A.8.13 Information backup | Parcial | Per-save rotation (`store.py:293-304`, `417-439`); encrypted archive + checksum (`tools/backup_offsite.sh`, retention 14 d); weekly decrypt/checksum gate (`tools/backup_verify.sh`); **scheduled** by `b2first-backup.timer` (daily 04:30, persistent) and `b2first-backup-verify.timer` (Sun 05:30); drill 2026-11-19 PASS in `06-BACKUP-RESTORE.md` (Drill log) | No off-host copy yet (R08): destination is still a local path, so the 3-2-1 rule is not met |
| A.8.14 Redundancy | Gap | Single host (`b2first.service`) | No redundant host or database |
| A.8.15 Logging | Implementado | Access log with `rid`, path without query (`SECURITY.md §3`); hash-chained audit (`server.py:3051-3090`); error log (`server.py:487-518`); retention (`tools/retention.py:87-166`); verifier (`tools/verify_audit.py`); tests G1–G3, H1–H5 | Central shipping and log-integrity protection against root remain gaps (R14/R15) |
| A.8.16 Monitoring activities | Gap | None; no alerting or scheduled check | Add monitoring/alerting (R15) |
| A.8.17 Clock synchronisation | Gap | Application uses host time (`time.gmtime`, `server.py:3059`); NTP configuration `unverified` | Document and verify NTP |
| A.8.18 Privileged utility programs | Gap | None | Inventory and restrict privileged utilities |
| A.8.19 Software installation on operational systems | Gap | No installation policy; `Dockerfile` builds an image | Define who may install what and how it is recorded |
| A.8.20 Networks security | Parcial | Loopback default bind (`server.py:95`), TLS at the edge, HSTS (`server.py:3274`), `audit-host.sh` checks nftables | Host firewall state `unverified`; other workloads share the host |
| A.8.21 Security of network services | Parcial | HSTS, closed CORS, no version banner (`server.py:3273-3295`; tests A1–A5, `test_server_hardening.py`) | TLS terminates at the edge, which sees plaintext; edge identity `unverified` |
| A.8.22 Segregation of networks | Gap | Single host shared with other services (`tools/audit-host.sh` mentions Coolify/Immich) | No verified network segregation for this workload |
| A.8.23 Web filtering | Gap | None | No egress/web filtering policy |
| A.8.24 Use of cryptography | Parcial | PBKDF2-HMAC-SHA256, SHA-256, HMAC-SHA256, `secrets` (`server.py:2126-2142`, `plans.py:551`), TOTP HMAC-SHA1 (`mfa.py:52-60`), AES-256-CBC/PBKDF2 backup (`tools/backup_offsite.sh:58`); stdlib only; tests D/G, `tests/test_mfa.py` | No cryptographic inventory or key-management/rotation policy; no full-disk encryption (R12) |
| A.8.25 Secure development life cycle | Parcial | `docs/internal/SDLC.md` (branch per change, mandatory gate, evidence rule, patch procedure) and executable gate `tools/preflight.sh:109-114` | No CI service and no separate approval; the same person writes and approves |
| A.8.26 Application security requirements | Parcial | ASVS 4.0.3 L2 checklist (`docs/SECURITY-CHECKLIST.md`) and threat model (`SECURITY.md §2`); release gate includes `tools/pentest.py --spawn` (`tools/preflight.sh:114`) | Requirements are not mapped to every gate step; 3 documented FAIL rows |
| A.8.27 Secure system architecture | Parcial | Single process, no database, documented trust boundary (`00-SCOPE.md §4`) | No formal architecture review or threat-model update cadence |
| A.8.28 Secure coding | Parcial | Input validation (`server.py:3211`, `1646`), escaping, path containment (`server.py:3337-3362`), tests `test_hardening.py`, `test_server_hardening.py`; gate checks inline handlers and JS syntax (`tools/preflight.sh:37-76`) | `'unsafe-inline'` remains (R03); no secure-coding standard document |
| A.8.29 Security testing in development | Parcial | 123 test files (`tests/`), `tools/audit.sh`, `tools/audit-host.sh`, `tools/verify_audit.py`; ordered release gate (compile, JS syntax, inline handlers, purchase copy, core suites, pentest) `tools/preflight.sh:109-114` | No CI configuration in the repository; the gate is run manually by the operator |
| A.8.31 Separation of development/test/production | Gap | Demo unit exists (`b2first-demo.service`), but no staging environment | Define environments and separation |
| A.8.32 Change management | Parcial | Git history with conventional commits; atomic writes and schema migration (`store.py:244-290`); branch-per-change and rollback policy (`docs/internal/SDLC.md §1, §5`); real patch register (`docs/internal/PATCH-LOG.md`) | No separate change approval and no deployment record with approver |
| A.8.33 Test information | Implementado | Every suite uses a throwaway `B2_DATA_DIR` and stubs (`tests/test_security3.py:31-38`, `tests/helpers.py:99-120`; `test_auth_methods.py`, `test_billing.py` use local stubs) | Keep the rule; add a check that no test writes to the repository `data/` |
| A.8.34 Protection of information systems during audit testing | Parcial | `tools/audit.sh` is read-only by construction and probes the public instance | No audit-testing agreement or pre-notification |

## 4. Non-applicable controls (excluded from counts)

| Control | Reason |
| --- | --- |
| A.5.11 Return of assets | No employees or issued assets are defined |
| A.5.35 Independent review of information security | Would require an independent reviewer; not present |
| A.7.1–A.7.13 (physical and environmental) | Physical site and its controls are not observable from the repository; `unverified` |
| A.7.14 Secure disposal of equipment | No media disposal procedure; applicable in principle but deferred until hardware disposal — currently a Gap if media leaves the host |
| A.8.4 Access to source code | Repository access is managed by GitHub; not configured in this repository |
| A.8.30 Outsourced development | No outsourced development |
| A.8.35–A.8.37 | Not part of ISO/IEC 27001:2022 Annex A numbering |

## 5. Reading of the result

- Verification runs on 2026-11-18 (all exit 0): `tests/test_security3.py`,
  `tests/test_sync.py`, `tests/test_password_reset_request.py`,
  `tests/test_server_hardening.py`, `tests/test_hardening.py`, `tests/test_register.py`,
  `tests/test_multiuser.py` (run through `uv` with playwright), and
  `bash tools/restore_drill.sh`.
- Additional runs for this phase (2026-11-18, all exit 0): `tests/test_mfa.py`
  (31 checks), `tests/test_auth_gate.py`, `tests/test_spike.py`,
  `B2_BACKUP_PASSPHRASE=test-pass bash tools/backup_offsite.sh` followed by
  `bash tools/backup_verify.sh`, `python3 tools/access_review.py`, and
  `bash tools/check_perms.sh`.
- The backup run used this worktree's empty `data/` (it is gitignored): it proves
  encryption, checksum and decryption, not an off-host copy or production volume.
  The access review likewise saw zero accounts. Neither is claimed as production
  evidence.
- MFA and the backup scripts are real artefacts with tests or recorded runs, but the
  organisation-dependent rows remain `Gap`: authority contacts, threat intelligence,
  supplier agreements, staff training, independent review and a real BCP/DR exercise
  cannot be produced by this repository.
- One documentation inconsistency was found while verifying: `docs/SECURITY-CHECKLIST.md`
  says the password blocklist has 200 entries, while `store.py:53-56` loads 1,000
  (`wordlist.COMMON_PASSWORDS`, counted on 2026-11-18). The code is the source of truth;
  the checklist should be corrected.
- The strongest verified areas are access restriction (A.8.3), logging (A.8.15) and test
  data isolation (A.8.33). Each has code plus a test or an executed script.
- Most organisational controls are **Parcial**: a document now exists, but there is no
  approval, review cadence, independent check, or exercised process behind it.
- The **Gaps** are dominated by one structural fact: a single host, a single person and no
  monitoring/backup automation in the repository. They cannot be closed by documentation
  alone.
