# 05 — Suppliers and Data Processors

Scope: third parties that receive data from this deployment. No signed Data Processing
Agreement (DPA), region guarantee, or sub-processor list exists in the repository; those
cells are marked `unverified`. "Free alternative" means a no-cost option available in the
repository or a standard self-hosted component, not a legal opinion that it removes the
supplier risk.

| Supplier | Service | Data sent | Legal basis asserted | Region | Retention at supplier | Dependency | Mitigation in place | Free / self-hosted alternative |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Cloudflare, Inc.** | TLS edge / tunnel (`firsttracker.app`) | Full HTTP request **in plaintext** at the edge: headers, path, cookies, bodies, IP address (`docs/PRIVACY.md §4`) | Service delivery (contract / legitimate interest) — asserted in the privacy policy; DPA `unverified` | Global edge network; localisation `unverified` | Per Cloudflare configuration; log retention `unverified` | High when it is the public edge (all traffic) | CSP blocks the Cloudflare Web Analytics beacon; owner expected to disable Web Analytics (`docs/PRIVACY.md §3`); no third-party analytics SDK | Tailscale Funnel (also documented) or a self-hosted reverse proxy with Let's Encrypt |
| **Google Identity (OAuth)** | Sign-in only when the user presses “Continue with Google” | Authorisation request (`openid email profile`), the chosen Google account, the authorisation code; code exchanged server-side and not stored; optional `sha256(normalised email)` stored **locally** (`docs/PRIVACY.md §2`; `oauth_google.py:1-13`) | Consent (user initiates); policy disclosure | Google infrastructure outside Argentina; exact region `unverified` | Per Google account terms; `unverified` | Optional (password and passkey login work without it) | PKCE; `id_token` verified against Google JWKS with `iss`/`aud`/`exp`/`nonce`; no client secret in the browser; test `tests/test_auth_methods.py` | Local password + WebAuthn passkey (already implemented) |
| **Google (Gemini API)** | Text provider option; speaking-report generation | The text submitted for correction or the transcript the user chose to analyse (`docs/PRIVACY.md §4`) | Service delivery; policy disclosure | Google infrastructure; `unverified` | Per Gemini API terms; free tier may be used to improve products, paid tier excluded — as stated in `docs/PRIVACY.md §4` | Optional (DeepSeek is the default; BYO key possible) | Keys in env only; 25 s timeout; request caps; no logging of content (`server.py:168`, `5064-5068`) | DeepSeek (also a supplier), a user-supplied key, or disable AI |
| **Google (Gemini Live)** | Live examiner/partner voices, Speaking Parts 1–4 | Microphone audio (16 kHz PCM), examiner script, ephemeral session token; the browser connects directly to Google (`docs/PRIVACY.md §3-4`; `server.py:211-266`) | Consent by starting the exam; policy disclosure | Google infrastructure; `unverified` | Per Gemini Live terms; `unverified` | Optional feature | Audio does not pass through this server; ephemeral token minted per session; per-user/instance minute caps (`server.py:215-217`, `1042-1095`); `tests/test_speaking_*` | Browser `SpeechRecognition` keeps text local; turn-based examiner; disable Speaking voice features |
| **DeepSeek** | Default text model for writing corrections | The text explicitly submitted for correction plus the task type; no account identifier (`docs/PRIVACY.md §4`) | Service delivery; policy disclosure | DeepSeek infrastructure; API region `unverified` | May retain under its API terms; `unverified` | Default text provider, but configurable (`B2_AI_PROVIDER`, `B2_AI_BASE`, `B2_AI_MODEL`, `README.md:252-255`) | Input fence + injection/output guards (`server.py:1646`, `1870`); per-plan and per-instance quotas; 25 s timeout; no content in logs (`tests/test_ai_guard.py`) | Gemini provider, a user-supplied key, or disable writing correction |
| **Microsoft Azure AI Speech** | Pronunciation assessment | At most 10 seconds of audio per turn and, optionally, the reference sentence (`docs/PRIVACY.md §4`; `speech.py:1-20`) | Consent by using pronunciation; policy disclosure | Azure region set by `B2_SPK_AZURE_REGION`; actual value `unverified` | Per Azure terms; `unverified` | Optional (pronunciation only) | Clip held in memory and discarded; container/duration validation before the call (`speech.py:1-80`); absent key reports “not measured” instead of inventing a score | Report the band as “not measured”; no equivalent free hosted service in the repository |
| **Stripe, Inc.** | Optional Checkout and subscriptions (`B2_BILLING_MODE=off` by default) | Customer/subscription/checkout identifiers (`cus_`, `sub_`, `cs_`); payment metadata; card data stays with Stripe (`billing.py:5-16`) | Contract (paid plan); policy disclosure | Stripe infrastructure (US/global); `unverified` | Per Stripe terms; idempotency ledger keeps the last 1000 event ids locally (`billing.py:15-16`, `68`) | Optional; billing off by default | Hosted Checkout (no card data on this server); signed webhooks with HMAC-SHA256 and ±300 s window (`billing.py:332-368`); test `tests/test_billing.py` | Manual licence codes signed with `B2_LICENSE_SECRET` (`plans.py:558-618`), already implemented |
| **GitHub, Inc.** | Source hosting, private vulnerability advisories | Source code; advisory text the reporter submits | Service delivery / legitimate interest; DPA `unverified` | GitHub infrastructure (US/global); `unverified` | Per GitHub terms; repository history indefinite | High for source and the only disclosure channel | No secrets committed; `data/` and keys gitignored; advisory URL published (`docs/SECURITY.md §2`) | Self-hosted Git plus a monitored mailbox (`unverified`, none exists) |
| **Tailscale, Inc.** | Alternative public edge (Tailscale Funnel) documented in `SECURITY.md` and `tools/audit-host.sh` | Network metadata and request traffic if this is the active edge | Service delivery; `unverified` | Tailscale infrastructure; `unverified` | Per Tailscale terms; `unverified` | Conditional: only if Funnel is the active edge. The active edge is **unverified** (Cloudflare is documented elsewhere) | Funnel is proxied to `127.0.0.1:8088`; `audit-host.sh` checks that only one public URL is exposed | Cloudflare tunnel or a self-hosted TLS terminator |
| **Vercel** | Listed in the task statement | **Not found anywhere in the repository.** No domain, configuration or mention | — | — | — | **Not applicable / `unverified`** | — | — |

## Dependency assessment

- **Single points of failure.** The public edge (Cloudflare or Tailscale, whichever is
  active) and the single host are hard dependencies for availability. DNS and TLS
  certificates are supplied by the edge; no fallback origin is defined.
- **Optional features degrade, but are not all tested end-to-end.** Billing answers
  `503 billing_not_configured` when unset (`billing.py:17-18`); Azure absence is reported as
  “not measured”; AI absence returns an error. The repository does not define a documented
  fallback provider per feature (R11).
- **Data minimisation.** No email, phone, address, birth date or card data is stored by
  this application (`docs/PRIVACY.md §3`; `billing.py:5-16`). The free-text recovery
  contact is the only arbitrary string a user can store (`store.py:383-414`).
- **Providers that can read content.** Cloudflare sees plaintext requests at the edge;
  Google and DeepSeek receive submitted text/audio. This is disclosed, not eliminated
  (`docs/PRIVACY.md §4`; R10).

## Supplier management gaps

- No DPA, sub-processor list, security questionnaire, or audit right is recorded for any
  supplier.
- No region pinning is proven; Azure region is environment-dependent and the others are
  `unverified`.
- No supplier review cadence, incident-notification clause, or exit plan is documented.
- No contract or billing relationship is verifiable from the repository for Cloudflare,
  Tailscale, DeepSeek, Google, Azure, Stripe, or GitHub.
