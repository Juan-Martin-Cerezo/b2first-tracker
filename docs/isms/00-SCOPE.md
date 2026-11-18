# 00 — ISMS Scope

Status: preparation only. This document defines the scope of an Information Security
Management System (ISMS) for the B2 First Tracker. It does **not** claim ISO/IEC 27001
certification or conformity. Gaps are listed in `07-ANNEX-A-MAPPING.md` and
`02-RISK-REGISTER.md`.

## 1. System in scope

| Element | Description | Evidence |
| --- | --- | --- |
| Application | `server.py`, Python standard library HTTP server, no framework, no database; JSON documents on disk | `server.py:69-97`; `store.py:1-56` |
| Static frontend | Single-file `index.html` plus `landing.html`, served by the same process | `server.py:65-66`; `Dockerfile` |
| Data store | `data/` (default `B2_DATA_DIR`/`DATA_DIR`): accounts, hashed sessions, per-user progress, backups, speaking ledger, audit, events, plans, licences, recovery requests | `server.py:71-80`; `docs/DATA-MAP.md` |
| Host | One Linux host. Repository and `b2first.service` describe a Raspberry Pi 5 (`User=juan`, `WorkingDirectory=/home/juan/b2first-tracker`; the server is tuned for “one Pi 5”); `tools/audit-host.sh` targets a host named `vps-server`. The actual deployed host is **unverified** from inside this repository. | `b2first.service:6-8`; `server.py:6260`; `tools/audit-host.sh:2` |
| Public edge | The repository documents two mutually exclusive edge designs: Tailscale Funnel to `127.0.0.1:8088` (root `SECURITY.md`, `server.py:92-94`) and a Cloudflare tunnel terminating TLS (`docs/SECURITY.md §1`, `docs/PRIVACY.md §4`). The active edge is **unverified**. | `server.py:92-95`; `docs/SECURITY.md:7-12`; `SECURITY.md:1-10`; `tools/audit-host.sh` ingress checks |
| AI providers | DeepSeek (default text provider), Google Gemini (text and Live speaking), Microsoft Azure AI Speech (pronunciation), optional user-supplied providers | `server.py:150-168`, `195-234`; `speech.py`; `docs/PRIVACY.md §4` |
| Identity providers | Local password accounts, optional Google OAuth, optional WebAuthn passkeys | `server.py:2327-2404`; `oauth_google.py`; `webauthn.py` |
| Payments | Optional Stripe Checkout and signed webhooks (`B2_BILLING_MODE=off` by default) | `billing.py:1-23`, `296-300`; `README.md:296-300` |

Default bind address is loopback (`B2_HOST=127.0.0.1`, `server.py:95`). Accounts are
user-chosen display names; the product does not collect email, phone, address or birth
date (`docs/PRIVACY.md §2-3`).

## 2. Organisational scope

- **Roles.** A single instance owner (operator) is also the developer, host administrator
  and data controller. There is no second administrator, no security team and no
  independent reviewer. See `03-ACCESS-CONTROL.md`.
- **Locations.** One production host plus the public edge and third-party AI/payment
  providers. No separate staging environment is defined in the repository; the demo
  instance (`b2first-demo.service`) is an isolated public demo, not a staging copy.
- **People.** The owner; end users with local accounts. No employees or contractors are
  defined in the repository.

## 3. Excluded from scope, with reason

| Excluded | Reason |
| --- | --- |
| Physical security of the hosting site | No evidence in the repository about the room, locks, or access logs. Cannot be assessed or controlled from this codebase. `unverified`. |
| The owner's laptop/workstation and personal accounts | Not part of the service; no configuration or MDM evidence in the repository. |
| Cloudflare/Tailscale/Google/DeepSeek/Azure/Stripe internal infrastructure | Shared responsibility; only the contractual and data-flow surface is covered in `05-SUPPLIERS.md`. |
| End-user devices and browsers | Outside the operator's control; the application makes no client-hardening claim. |
| Payment card data | Stripe-hosted Checkout; the server stores only `cus_`, `sub_` and `cs_` identifiers (`billing.py:5-16`). PCI scope is asserted as SAQ A but is **not verified** here. |
| Other workloads on the same host (Coolify, Immich, etc., referenced by `tools/audit-host.sh`) | Separate services; sharing the host is a risk (see `02-RISK-REGISTER.md`) but their controls are out of scope. |

## 4. ISMS boundaries and interfaces

- Boundary: the application process, its `data/` directory, the systemd unit, the host's
  network ingress and egress, and the configured supplier endpoints.
- Interfaces: HTTPS from browsers through the edge; HTTPS/WebSocket from the server to AI
  and payment providers; SSH/systemd on the host; GitHub for source and vulnerability
  disclosure.
- Trust boundary: the host and its root user. Anyone with root can read `data/` and rewrite
  the audit log (`SECURITY.md §5.3`; `docs/SECURITY.md §4`).

## 5. What this phase does not do

- It does not modify `server.py`, the UI, or runtime behaviour.
- It does not certify, attest, or assert ISO/IEC 27001 conformity.
- It does not create a legal opinion on GDPR, Ley 25.326, or supplier contracts.
- Where a claim could not be checked in the repository or on the host, this package writes
  `unverified` and carries the item into the risk register.
