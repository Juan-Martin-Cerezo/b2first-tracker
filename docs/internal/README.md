# Internal Engineering & Operations Documentation

This directory contains **internal development, architecture, performance, and compliance preparation records** for B2 First Tracker. It is **not** user-facing product documentation; for product overview, policies, and setup, see [../README.md](../README.md) and [../../README.md](../../README.md).

## Engineering & operations notes

| File | Description |
| --- | --- |
| [LOADTEST-BASELINE.md](LOADTEST-BASELINE.md) | Throughput and latency baseline measurements (`tools/loadtest.py`). |
| [PATCH-LOG.md](PATCH-LOG.md) | Historical change log of operational and security patches. |
| [PROGRESSION.md](PROGRESSION.md) | Specification for study stages, diagnostic ranking, and progression gates. |
| [SDLC.md](SDLC.md) | Secure Development Life Cycle notes for this repository. |
| [SPEAKING-CONCURRENCY.md](SPEAKING-CONCURRENCY.md) | Design and measurements for bounded upstream Speaking concurrency. |
| [SPEAKING-REALTIME-PLAN.md](SPEAKING-REALTIME-PLAN.md) | Implementation plan for Speaking S1–S5 (VAD, PA, Live, turn-based fallback, report). |

## ISMS preparation (`isms/`)

Working drafts mapping a single-operator deployment to ISO/IEC 27001:2022 controls (preparation only, not a certification claim):

- [isms/00-SCOPE.md](isms/00-SCOPE.md) — ISMS scope
- [isms/01-ASSET-INVENTORY.md](isms/01-ASSET-INVENTORY.md) — Asset inventory
- [isms/02-RISK-REGISTER.md](isms/02-RISK-REGISTER.md) — Risk register
- [isms/03-ACCESS-CONTROL.md](isms/03-ACCESS-CONTROL.md) — Access control policy
- [isms/04-INCIDENT-RESPONSE.md](isms/04-INCIDENT-RESPONSE.md) — Incident response plan
- [isms/05-SUPPLIERS.md](isms/05-SUPPLIERS.md) — Suppliers and data processors
- [isms/06-BACKUP-RESTORE.md](isms/06-BACKUP-RESTORE.md) — Backup and restore procedures
- [isms/07-ANNEX-A-MAPPING.md](isms/07-ANNEX-A-MAPPING.md) — Annex A control mapping
