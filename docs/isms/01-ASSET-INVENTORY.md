# 01 — Asset Inventory

Owner: unless stated otherwise, every asset is owned by the single instance operator
(`juan` on the host described by `b2first.service`). There is no separate asset owner,
custodian or data-protection officer.

Classification scale used here:

- **Public** — intended for anyone.
- **Internal** — operational data; disclosure is inconvenient, not directly harmful.
- **Personal** — relates to an identified or identifiable person (a user).
- **Sensitive** — credentials, keys, or data whose disclosure enables account takeover or
  unauthorised spend.

Format and location are as implemented in the code; retention is the configured or
documented limit, with the enforcing code where one exists.

| ID | Asset | Owner | Location | Class | Format | Retention | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A01 | Application source code | Owner | Git repository (`origin git@github.com:Juan-Martin-Cerezo/b2first-tracker.git`), working tree | Public | Python, HTML, shell, Markdown | Indefinite (git history) | `git remote -v`; `LICENSE:1-3` (MIT) |
| A02 | Static frontend | Owner | `index.html`, `landing.html`, `assets/`, `img/` | Public | HTML/CSS/JS, images | With the release | `server.py:65-66`; `Dockerfile` |
| A03 | Reference study material | Owner | `material/` (3 JSON files: `diagnostico.json`, `speaking.json`, `writing-samples.json`) | Public/Internal | JSON | With the release | `server.py:67`; directory listing |
| A04 | Account records | Owner | `data/users.json` | Sensitive | JSON: `id`, `name`, `salt`, PBKDF2 `hash`, `algo`, `iters`, optional `email_hash` | Until account deletion | `docs/DATA-MAP.md` store table; `store.py:224-241` |
| A05 | Session tokens | Owner | `data/tokens.json` | Sensitive | JSON: `sha256(token)` → `user_id`, `exp`, `issued`, `absolute_exp`, `last_seen`, `ua_hash` | 30 days sliding, 90 days absolute | `server.py:2180-2244`; `docs/DATA-MAP.md` |
| A06 | Per-user progress | Owner + each user | `data/users/<id>/progress.json` | Personal | JSON: practice log, error log, profile, settings, plan mirror | Until account deletion | `store.py:267-290`, `417-439`; `docs/DATA-MAP.md` |
| A07 | Per-save progress backups | Owner | `data/users/<id>/backups/` | Personal | JSON copies | 20 newest versions | `store.py:293-304`, `434-438`; `BK_KEEP=20` (`store.py:45`) |
| A08 | Speaking ledger | Owner | `data/users/<id>/speaking.json` | Personal | JSON: date, seconds, tokens minted; no audio | Until account deletion | `store.py:318-354`; `docs/DATA-MAP.md` |
| A09 | Opt-in speaking transcripts | Owner + each user | `data/users/<id>/speaking/<stamp>.json` | Personal | JSON transcript | Until user deletes or account deletion | `store.py:139-153`; `docs/PRIVACY.md §2` |
| A10 | Manual password-recovery queue | Owner | `data/pwreset.jsonl` | Personal/Sensitive | JSON lines: `ts`, `name`, optional free-text `contact`, `ip_hash`, `rid` | 90 days / 500 lines | `store.py:357-414`; `docs/DATA-MAP.md` |
| A11 | Security audit log | Owner | `data/audit.log` (+ `data/audit.log.1`) | Internal/Sensitive | JSON lines with SHA-256 `prev` chain; user name or id, hashed IP, request id | 90 days; rotates at 5 MB | `server.py:3016-3090`; `tools/retention.py:87-166` |
| A12 | Application error log | Owner | `data/errors/YYYY-MM-DD.jsonl` | Internal | JSON lines: path, hashed IP, truncated traceback, `rid` | **No retention implemented** (gap) | `server.py:487-518`; `tools/retention.py` has no `errors/` branch |
| A13 | Product telemetry | Owner | `data/events/YYYY-MM-DD.jsonl` | Internal | JSON lines: whitelisted event + scalar props, salted IP hash | 7 days, pruned on write | `server.py:379-395`, `521-563` |
| A14 | Usage counters | Owner | `data/usage.json` | Internal | JSON: per-account counters, `last_seen` | 13 months | `tools/retention.py:169-189`; `docs/DATA-MAP.md` |
| A15 | Plan rows | Owner | `data/plans.json` | Internal | JSON: plan, since, until, source | Until account deletion; 13-month prune | `docs/DATA-MAP.md`; `plans.py` |
| A16 | Licence ledger | Owner | `data/licenses.json` | Sensitive | JSON: `sha256(code)` → plan, days, issue/redeem dates, user id | Until account deletion (code stays burnt/detached) | `plans.py:515-516`, `558-618`; `server.py:2764-2776` |
| A17 | Billing event ledger | Owner | `data/billing/events.json` | Internal | JSON: last 1000 processed Stripe event ids | 1000 events | `billing.py:15-16`, `68` |
| A18 | Google account links | Owner | `data/oauth.json` | Personal | JSON: Google `sub` → local user id | Until account deletion | `store.py`/`docs/DATA-MAP.md`; `server.py:2764-2776` |
| A19 | Passkey credentials | Owner | `data/webauthn/<id>.json` | Sensitive | JSON: credential id, P-256 public key (COSE), sign counter, label | Until account deletion | `docs/DATA-MAP.md`; `webauthn.py` |
| A20 | AI provider keys (shared) | Owner | Environment only, e.g. `EnvironmentFile=-/home/juan/.config/b2first/ai.env` or `/etc/b2first.env` | Sensitive | Env vars (`B2_AI_KEY`, `B2_SPK_GOOGLE_KEY`, `B2_SPK_AZURE_KEY`) | Until rotated by the owner; rotation schedule undocumented | `b2first.service:11`; `README.md:219`, `252-289`; `server.py:95-97` |
| A21 | Licence signing secret | Owner | Environment (`B2_LICENSE_SECRET`) | Sensitive | Env var, ≥32 bytes | Until rotated; rotation undocumented | `README.md:246`; `plans.py:551`; `server.py:736-742` |
| A22 | Stripe credentials | Owner | Environment (`B2_STRIPE_SECRET_KEY`, `B2_STRIPE_WEBHOOK_SECRET`) | Sensitive | Env vars | Until rotated; rotation undocumented | `README.md:296-300`; `billing.py:114-160` |
| A23 | Google OAuth client secret | Owner | Environment (`B2_GOOGLE_CLIENT_SECRET`) | Sensitive | Env var | Until rotated; rotation undocumented | `README.md:264-265`; `oauth_google.py` |
| A24 | Event IP salt | Owner | `data/.events_salt` | Sensitive | Random salt file, `0600` | Until deleted | `docs/DATA-MAP.md` |
| A25 | Host system logs | Owner | systemd journal / host logging | Internal | Text | Host policy; **unverified** | `b2first.service`; no journald configuration in the repository |
| A26 | Host backups | Owner | Location, schedule, encryption and retention **unverified** | Personal | Archive (`tar.gz` described in docs; tooling not in repository) | Docs claim 14 days | `SECURITY.md §4`; `docs/PRIVACY.md §7`; no backup script under `tools/` |
| A27 | Container image | Owner | `Dockerfile` (`python:3.13-slim`, mutable tag) | Public/Internal | OCI image | Per registry | `Dockerfile:1` |
| A28 | Disclosure metadata | Owner | `/.well-known/security.txt`, `docs/SECURITY.md` | Public | Text | Indefinite | `docs/SECURITY-CHECKLIST.md` V14 row; `server.py` `security_txt()` |

## Third-party data holdings (summary; details in `05-SUPPLIERS.md`)

| Provider | Data held/processed | Class |
| --- | --- | --- |
| Cloudflare (edge) | Full HTTP requests in plaintext, IP addresses, TLS termination | Personal/Sensitive |
| Google Identity | OAuth authorisation request; email hash optionally stored locally | Personal |
| Google Gemini | Microphone audio (Live speaking), examiner script, session token; submitted text | Personal |
| DeepSeek | Writing text submitted for correction, task type | Personal |
| Microsoft Azure Speech | ≤10 s pronunciation audio and optional reference sentence | Personal |
| Stripe | Customer/subscription identifiers, payment metadata (card data stays at Stripe) | Personal/Sensitive |
| GitHub | Source code, security advisories | Public/Internal |
| Tailscale / Vercel | Listed by the task statement; Tailscale is documented in `SECURITY.md`/`audit-host.sh`, Vercel is **not found in the repository** (`unverified`) | Public/Internal |

## Inventory gaps

- No formal asset owner for each row: one person owns everything.
- Host backup location, encryption, schedule and restore evidence are not in the repository.
- `data/errors/` has no retention mechanism, although it contains tracebacks and hashed IPs.
- Provider keys have no documented rotation interval or last-rotated date.
- The public edge and host identity are inconsistently documented (Pi 5 vs `vps-server`;
  Tailscale Funnel vs Cloudflare), so the physical/logical location of A06–A19 is
  **unverified**.
