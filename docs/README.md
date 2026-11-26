# Documentation Index

This directory holds the public policies, configuration reference, security documentation, and internal engineering notes for **B2 First Tracker**.

## User-facing policies (served live on firsttracker.app)

| Document | Live route | When to read it |
| --- | --- | --- |
| [PRIVACY.md](PRIVACY.md) | `/privacy` | What account, study, and event data is stored, what is sent to AI providers, retention periods, and self-service export/deletion. |
| [TERMS.md](TERMS.md) | `/terms` | Terms of use, fair-use daily limits, bring-your-own-key responsibilities, and disclaimers. |
| [SECURITY.md](SECURITY.md) | `/security` | Short public security policy, data protection summary, scope, and how to report a vulnerability. |

## Technical & operator documentation

| Document | Purpose | When to read it |
| --- | --- | --- |
| [../README.md](../README.md) | Product overview, AI architecture, quick start, limits, and test suites. | Start here to understand or run the project. |
| [CONFIGURATION.md](CONFIGURATION.md) | Complete environment variable reference with defaults and effects. | When configuring a local or hosted instance (AI keys, Speaking Live, daily/monthly caps, OAuth, passkeys). |
| [../SECURITY.md](../SECURITY.md) | Detailed threat model, implemented controls, backups, residual risks, and disclosure process. | When auditing the server or evaluating security guarantees. |
| [DATA-MAP.md](DATA-MAP.md) | Concrete map of every stored data category, retention rule, and account deletion sequence. | When verifying data minimization and GDPR/Ley 25.326 deletion behavior. |
| [SECURITY-CHECKLIST.md](SECURITY-CHECKLIST.md) | OWASP ASVS 4.0.3 Level 2 verification checklist mapped to code and tests. | When reviewing control coverage and reproducing audit checks. |
| [HACKATHON.md](HACKATHON.md) | Devpost submission pack for Build Your First AI App 2026 (summary, AI architecture, 2–3 min demo script, honest limitations, credits). | When reviewing or presenting the hackathon submission. |
| [REPO-ABOUT.md](REPO-ABOUT.md) | GitHub repository About panel copy (description, website, topics). | When updating repository metadata on GitHub. |

## Internal documentation (not product docs)

| Directory | Purpose |
| --- | --- |
| [internal/README.md](internal/README.md) | Engineering specs, load-test baselines, SDLC notes, and ISO 27001 ISMS preparation records. |
| [../delegacion/README.md](../delegacion/README.md) | Internal development briefs and phase prompts used during implementation. |
