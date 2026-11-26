# B2 First Tracker — Hackathon Submission (Build Your First AI App 2026)

Ready-to-paste submission pack for **Build Your First AI App 2026** (Devpost, deadline December 9, 2026). Every claim below reflects the code shipped in this repository.

---

## Project name

**B2 First Tracker**

## Tagline

Practice the Cambridge B2 First with a 4-band AI Writing corrector, a timed 4-part AI Speaking examiner, and a daily study plan derived from your log.

## Links

- **Live app:** https://firsttracker.app
- **Source code:** https://github.com/Juan-Martin-Cerezo/b2first-tracker
- **Privacy Policy:** https://firsttracker.app/privacy ([`docs/PRIVACY.md`](PRIVACY.md))
- **Terms of Use:** https://firsttracker.app/terms ([`docs/TERMS.md`](TERMS.md))
- **Security Policy:** https://firsttracker.app/security ([`docs/SECURITY.md`](SECURITY.md))
- **Configuration reference:** [`docs/CONFIGURATION.md`](CONFIGURATION.md)

---

## The problem

Self-study learners preparing for the Cambridge B2 First exam face two practical bottlenecks:

1. **Answer keys stop working on Writing and Speaking.** You can score Reading, Use of English, and Listening yourself with a key, but Writing (Essays, Articles, Reports, Reviews, Emails) and Speaking (a 14-minute, 4-part oral exam with an examiner and a second candidate) require structured, rubric-grounded feedback that most learners cannot afford every day.
2. **Unstructured practice wastes exam weeks.** With 17 distinct parts across 4 papers, self-study candidates tend to repeat comfortable parts and neglect weak ones until exam week.

## The solution

**B2 First Tracker** combines a deterministic daily study scheduler with focused AI feedback where answer keys cannot help:

- **Adaptive daily plan & 3-step session coach:** An optional 12-question baseline diagnostic ranks weak Reading & Use of English parts. Two rotation modes (*By part* and *Full paper each session*) derive today's session directly from the sessions already logged, paired with a mobile-friendly 3-step session coach and official Cambridge timings.
- **4-band Cambridge Writing corrector:** Grades Essays, Articles, Reports, Reviews, and Emails from 0 to 5 on *Content*, *Communicative Achievement*, *Organisation*, and *Language*, quoting exact sentences from the user's draft, naming two concrete weaknesses, and proposing three targeted rewrites.
- **4-part Cambridge Speaking exam:** Four complete Cambridge sample exams (*B2 First Sample Paper 1 & 2*, *B2 First for Schools Sample Paper 1 & 2*) plus **Use my own task** (multipart form + image upload). Runs a single part or the full 14-minute oral exam with mandatory formal British examiner introduction, AI candidate partner, push-to-talk audio, Part 2 photo pairs, Part 3 task cards with 15-second preparation, and a 3-band report (no transcripts, no pronunciation scoring).
- **Real Mocks & Practice Library:** Guided full-mock start inside **Exam → Real mocks** (materials to timer in one screen, handing straight into Speaking), a searchable Library of local sample papers, answer keys, audio, tapescripts, checklists, and 74 verified online practice sources, plus private user-uploaded Listening practice files.
- **Honest progress tracking:** Three zero-dependency SVG charts (*Evolution over time*, *Weakest parts*, *Weekly consistency*), a stage Progression Matrix, and a separate Error Taxonomy view (*L-GAP*, *G-ERR*, *T-MIS*, *T-LIM*).

---

## How AI is implemented

The backend (`server.py`) acts as a strict, rate-limited proxy and validator — API keys stay server-side (or optionally in the user's browser via bring-your-own-key).

### 1. Writing grading (`prompts.py` + `POST /api/ai`)
- **Model:** DeepSeek (`deepseek-chat`) by default, or Google Gemini (`gemini-2.0-flash`).
- **Prompting & validation:** Prompts embed the four published Cambridge B2 First assessment criteria and require a strict JSON schema (capped at 8 KB) with integer bands (0–5), quoted evidence from the candidate's draft, concrete weaknesses, and three rewrites. Server-side guards enforce input size limits, injection/prompt-leak filtering, and schema validation before returning results to the browser.

### 2. Speaking v3 exam engine (`speaking_v3/` + `/api/speaking/v3/...`)
- **Capture & audio-only exam room:** Browser records one push-to-talk turn via `MediaRecorder` and plays examiner/partner audio sequences via Web Audio API. No question text, chat bubbles, or transcripts ever appear on screen.
- **In-memory STT + formal British TTS:** `speaking_v3/voice.py` transcribes the candidate turn in memory using `gemini-2.5-flash`, validates semantic relevance (re-prompting formally in British English on silence, non-English, or off-topic answers), generates a contextual AI partner response, and synthesises distinct British examiner and partner voices with `gemini-2.5-flash-preview-tts`. Audio is never written to disk; when `B2_SPK_GOOGLE_KEY` is unset, the server returns `503 speech_not_configured` clearly instead of simulating voices.
- **3-band report & privacy contract:** `speaking_v3/engine.py` computes estimated Cambridge B2 First bands (0–5) across *Grammar & Vocabulary*, *Discourse Management*, and *Interactive Communication* from in-session numeric micro-scores and flags — no pronunciation scoring and no transcripts persisted or returned.

### 3. Privacy & cost guards
- **No speaking audio or transcripts stored:** Speaking audio is held in memory only for the single turn and discarded immediately; session files store only exam state, flags, and numeric micro-scores (24-hour expiry). Only compact 3-band summaries are saved to progress when the user clicks **Save report**. Own-task images uploaded under **Use my own task** stay private to the user's account until deleted.
- **Quotas:** Per-account UTC daily caps (`plans.py`: 5 Writing evaluations, 3 Speaking mocks / 45 min per day — single part or full mock consumes 1 mock), instance-wide daily caps, a hard monthly voice minute guard, and per-IP/per-account rate limits. Users can also supply their own provider key in **Settings → AI provider** (stored only in browser `localStorage`).

---

## Tech stack

- **Backend:** Python 3.11+ standard library only (`http.server.ThreadingHTTPServer`, `urllib.request`, `hashlib`, `hmac`, `secrets`, `json`) — zero third-party Python runtime dependencies, zero external database.
- **Frontend:** Vanilla HTML, CSS (`oklch` light/dark tokens), and JavaScript in a single-file app (`index.html`) plus public landing page (`landing.html`), using browser `MediaRecorder` and Web Audio API. Zero build step, zero JS frameworks, zero external font/JS CDNs.
- **Storage & auth:** Atomic per-account JSON files (`0600`/`0700`) with 20-version backup rotation (`store.py`), PBKDF2-HMAC-SHA256 (600,000 iterations), SHA-256 hashed session tokens, SHA-256 hash-chained audit log, optional Google OAuth 2.0 + PKCE (`oauth_google.py`), WebAuthn passkeys (`webauthn.py`), and RFC 6238 TOTP MFA (`mfa.py`).
- **Verification:** 143 standalone automated test suites under `tests/` using Playwright and HTTPX against isolated temporary servers with offline provider stubs.

---

## Demo script (2–3 minutes)

Works directly on https://firsttracker.app or locally at `http://127.0.0.1:8088` with no special setup steps.

1. **0:00–0:25 — Landing & instant account (`/` → `/app`)**
   - Show the landing page (`/`, light/dark toggle, EN/ES switch, honest "Practice, not a certificate" framing).
   - Open `/app`, sign in (or create a fresh username + 12-char password — no email or credit card needed), and skip or complete the quick onboarding.
2. **0:25–0:55 — Today view & 3-step session coach**
   - Show today's scheduled unit derived automatically from the user's rotation and log.
   - Start the session to show the 3-step coach, built-in timer, and inline materials ready without hunting across folders.
3. **0:55–1:40 — AI Writing corrector (`AI Writing`)**
   - Pick *Essay* (or paste a sample 150-word draft) and click **Correct**.
   - Highlight the live step-by-step grading progress bar, then walk through the 4 Cambridge bands (0–5), quoted evidence from the draft, concrete weaknesses, and 3 targeted rewrites.
4. **1:40–2:25 — Speaking v3 exam room (`Speaking`)**
   - Open Speaking to show the 4 Cambridge sample exams plus **Use my own task**.
   - Launch Part 2 (mandatory formal British examiner intro, AI partner, side-by-side photographs, official timer, push-to-talk **Hold to speak** button, and zero on-screen scripts).
   - Finish the part to show the 3-band Cambridge report (*Grammar & Vocabulary*, *Discourse Management*, *Interactive Communication*) and **Save report**.
5. **2:25–2:55 — Progress & Real Mocks (`Progress` & `Exam`)**
   - Open **Progress**: show the 4 KPIs, per-skill bars, and the three clean zero-dependency SVG charts (*Evolution over time*, *Weakest parts*, *Weekly consistency*) plus the Progression Matrix.
   - Briefly show **Exam → Real mocks** (full 4-paper mock sequence in one block) and **Account → Export / Delete** self-service privacy controls.

---

## What is real vs. current limitations

| Area | Shipped today | Known limitation / honest boundary |
| --- | --- | --- |
| **Writing feedback** | 4 Cambridge bands (0–5), quoted text evidence, weaknesses, 3 rewrites, strict JSON validation | Band estimates are practice guidance, not official Cambridge scores. |
| **Speaking voice** | 4 Cambridge sample papers + multipart own tasks, mandatory intro, push-to-talk Gemini STT/TTS, AI partner, 3-band report | Requires server `B2_SPK_GOOGLE_KEY` (returns `503 speech_not_configured` when unset — never simulates voices). Pronunciation is not scored. |
| **Daily AI quotas** | 5 Writing evaluations and 3 Speaking mocks (45 min) per UTC day per standard account + instance-wide monthly cap | Shared hosted keys are budgeted; users can add their own provider key in Settings to bypass shared limits. |
| **Accounts** | Username + 12-char password, Google OAuth, passkeys, TOTP MFA | An account is required (no anonymous/local-only mode). Password resets without Google OAuth are manual requests because no email is required. |
| **Exam materials** | 4 Speaking sample papers for personal practice (`assets/speaking/exams/CREDITS.md`), 12-item diagnostic, writing samples, 74 verified online sources, private user Listening & Speaking own-task uploads | Official copyrighted Cambridge past papers are not redistributed as downloadable files; users open official external links or upload personal files privately. |

---

## Local setup

Requires Python 3.11+ only (no `pip install`, no Node.js):

```bash
git clone https://github.com/Juan-Martin-Cerezo/b2first-tracker.git
cd b2first-tracker
python3 server.py
```

Open `http://127.0.0.1:8088` (`/` is the landing page, `/app` is the tracker) and create a local account.

To enable AI locally, either export provider keys before running `server.py` (see [`docs/CONFIGURATION.md`](CONFIGURATION.md) for all environment variables) or paste your own API key in **Settings → AI provider** inside the browser.

Docker option:

```bash
docker build -t b2first .
docker run -p 8088:8088 -v b2data:/app/data b2first
```

---

## Credits & attribution

- **Core runtime & web standards:** Python 3.11+ standard library, vanilla HTML/CSS/JS, `MediaRecorder`, and Web Audio API.
- **AI APIs & pretrained models:**
  - [DeepSeek API](https://platform.deepseek.com/) (`deepseek-chat`) — Writing 4-band grading and Speaking partner replies.
  - [Google Gemini API](https://ai.google.dev/) (`gemini-2.5-flash`, `gemini-2.5-flash-preview-tts`) — push-to-talk Speaking STT and British examiner/partner TTS.
- **Media & sample-paper credits:** Speaking sample paper visuals are credited for personal study in [`assets/speaking/exams/CREDITS.md`](../assets/speaking/exams/CREDITS.md); Wikimedia Commons photograph credits remain in [`assets/speaking/CREDITS.json`](../assets/speaking/CREDITS.json).
- **Development & test tooling (dev-only):** [Playwright](https://playwright.dev/python/) (Apache-2.0) and [HTTPX](https://www.python-httpx.org/) (BSD-3-Clause), run via `uv`.
- **AI coding assistants:** AI coding assistants (Claude and Gemini) were used during development for implementation, refactoring, automated test writing, and documentation editing, with all code reviewed, tested, and verified by the author.
- **Trademarks:** Cambridge and B2 First are trademarks of Cambridge University Press & Assessment. B2 First Tracker is an independent educational project and is not affiliated with or endorsed by Cambridge.
