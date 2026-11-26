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
- **4-part AI Speaking examiner:** Runs a single part or the full 14-minute B2 First oral exam (Part 1: 2 min, Part 2: 4 min with Wikimedia Commons photo pairs, Part 3: 4 min collaborative card, Part 4: 4 min discussion), including a second-candidate **partner** role from Part 2 onward and custom prompt support (*Use my own task*).
- **Local VAD Live Studio:** Browser-only `AudioWorklet` voice activity detection (`assets/spk-vad.js`) measures speech ratio, pauses, and longest silence locally without recording or uploading audio.
- **Real Mocks & Practice Library:** Guided full-mock start inside **Exam → Real mocks** (materials to timer in one screen), a searchable Library of local sample papers, answer keys, audio, tapescripts, checklists, and 26 verified online practice sources, plus private user-uploaded Listening practice files.
- **Honest progress tracking:** Three zero-dependency SVG charts (*Evolution over time*, *Weakest parts*, *Weekly consistency*), a stage Progression Matrix, and a separate Error Taxonomy view (*L-GAP*, *G-ERR*, *T-MIS*, *T-LIM*).

---

## How AI is implemented

The backend (`server.py`) acts as a strict, rate-limited proxy and validator — API keys stay server-side (or optionally in the user's browser via bring-your-own-key).

### 1. Writing grading (`prompts.py` + `POST /api/ai`)
- **Model:** DeepSeek (`deepseek-chat`) by default, or Google Gemini (`gemini-2.0-flash`).
- **Prompting & validation:** Prompts embed the four published Cambridge B2 First assessment criteria and require a strict JSON schema (capped at 8 KB) with integer bands (0–5), quoted evidence from the candidate's draft, concrete weaknesses, and three rewrites. Server-side guards enforce input size limits, injection/prompt-leak filtering, and schema validation before returning results to the browser.

### 2. Speaking examiner — turn-based STT/TTS (`speaking_prompts.py` + `POST /api/speaking/turn`)
- **Capture:** Browser captures one spoken turn as 16 kHz PCM via an `AudioWorklet` (`assets/spk-tx.js`).
- **Single-call understanding + reply:** `server.py` forwards the turn to `gemini-2.5-flash` with a structured JSON output schema returning `{transcript, reply}` in a single upstream call, keeping examiner prompts constrained to the active Cambridge part and clock (never teaching, praising, or inventing speech when silence is received).
- **Voice reply (TTS):** The examiner or partner line is synthesized with `gemini-2.5-flash-preview-tts` (distinct voices for examiner and partner) and returned to the browser. Turn audio is held in memory only for that request and discarded immediately — never written to disk.
- **Optional real-time mode & zero-key fallback:** Operators can opt into direct browser ↔ Google WebSocket sessions via `gemini-3.8-live` using single-use ephemeral tokens (`POST /api/speaking/token`). When no Google key is configured, the Speaking exam still runs end-to-end using the browser's Web Speech API (`speechSynthesis` and `SpeechRecognition`).

### 3. Grounded Speaking partner & end-of-session report (`POST /api/speaking/partner`, `POST /api/speaking/report`, `speaking_report.py`)
- **Partner grounding:** From Part 2 onward, the candidate's latest utterance is sent to the text model (`deepseek-chat` or Gemini) so the partner replies with one natural sentence tied to what the candidate actually said; if no key is configured, scripted lines from `material/speaking.json` are used.
- **Report & anti-hallucination rule:** `speaking_report.py` grades only the candidate's turns on *Grammar & Vocabulary*, *Discourse Management*, and (when a partner participated) *Interactive Communication*. The prompt explicitly forbids grading Pronunciation (`DO NOT GRADE PRONUNCIATION`), and the server strips any pronunciation score invented by the LLM. Pronunciation is populated only from optional Azure Pronunciation Assessment (`POST /api/speaking/pa`); otherwise the UI displays **`not measured`**.

### 4. Privacy & cost guards
- **No speaking audio or transcripts stored:** Speaking audio is never written to disk, and the web client always sends `store_transcript: false` when generating a report — only the summary score row is saved to progress when the user clicks **Save report**.
- **Quotas:** Per-account UTC daily caps (`plans.py`: 5 Writing evaluations, 3 Speaking mocks / 45 min per day), instance-wide daily caps, a hard monthly Live minute guard, and per-IP/per-account rate limits. Users can also supply their own provider key in **Settings → AI provider** (stored only in browser `localStorage`).

---

## Tech stack

- **Backend:** Python 3.11+ standard library only (`http.server.ThreadingHTTPServer`, `urllib.request`, `hashlib`, `hmac`, `secrets`, `json`) — zero third-party Python runtime dependencies, zero external database.
- **Frontend:** Vanilla HTML, CSS (`oklch` light/dark tokens), and JavaScript in a single-file app (`index.html`) plus public landing page (`landing.html`) and two `AudioWorklet` scripts (`assets/spk-vad.js`, `assets/spk-tx.js`). Zero build step, zero JS frameworks, zero external font/JS CDNs.
- **Storage & auth:** Atomic per-account JSON files (`0600`/`0700`) with 20-version backup rotation (`store.py`), PBKDF2-HMAC-SHA256 (600,000 iterations), SHA-256 hashed session tokens, SHA-256 hash-chained audit log, optional Google OAuth 2.0 + PKCE (`oauth_google.py`), WebAuthn passkeys (`webauthn.py`), and RFC 6238 TOTP MFA (`mfa.py`).
- **Verification:** 160 standalone automated test suites under `tests/` using Playwright and HTTPX against isolated temporary servers with offline provider stubs.

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
4. **1:40–2:25 — AI Speaking examiner (`Speaking`)**
   - Launch Speaking Part 2 (2 Wikimedia Commons photos + official timer) or Part 1.
   - Speak one turn to show turn-based AI examiner response (STT + contextual reply + natural TTS voice) and partner handoff.
   - Open the end-of-part report and point out the honest **`Pronunciation: not measured`** badge when no pronunciation assessment provider is configured.
5. **2:25–2:55 — Progress & Real Mocks (`Progress` & `Exam`)**
   - Open **Progress**: show the 4 KPIs, per-skill bars, and the three clean zero-dependency SVG charts (*Evolution over time*, *Weakest parts*, *Weekly consistency*) plus the Progression Matrix.
   - Briefly show **Exam → Real mocks** (full 4-paper mock sequence in one block) and **Account → Export / Delete** self-service privacy controls.

---

## What is real vs. current limitations

| Area | Shipped today | Known limitation / honest boundary |
| --- | --- | --- |
| **Writing feedback** | 4 Cambridge bands (0–5), quoted text evidence, weaknesses, 3 rewrites, strict JSON validation | Band estimates are practice guidance, not official Cambridge scores. |
| **Speaking voice** | Full Parts 1–4 with official timings, turn-based Gemini STT/TTS, optional Gemini Live, partner grounding, custom tasks | Without an operator Google key, falls back to browser Web Speech API (`SpeechRecognition` / `speechSynthesis`), whose quality and availability vary by browser. |
| **Pronunciation score** | Optional Azure Pronunciation Assessment (`POST /api/speaking/pa`) | When no Azure key is configured, returns `503 speech_not_configured` and displays **`not measured`** (`no medida`) — never guessed by the LLM. |
| **Daily AI quotas** | 5 Writing evaluations and 3 Speaking mocks (45 min) per UTC day per standard account + instance-wide monthly cap | Shared hosted keys are budgeted; users can add their own provider key in Settings to bypass shared limits. |
| **Accounts** | Username + 12-char password, Google OAuth, passkeys, TOTP MFA | An account is required (no anonymous/local-only mode). Password resets without Google OAuth are manual requests because no email is required. |
| **Exam materials** | Original Speaking task bank (`material/speaking.json`), 12-item diagnostic, writing samples, 26 verified online sources, private user Listening uploads | Official copyrighted Cambridge past papers are not redistributed in the repository; users open official external links or upload personal files privately. |

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

- **Core runtime & web standards:** Python 3.11+ standard library, vanilla HTML/CSS/JS, Web Audio API (`AudioWorklet`), and browser Web Speech API (`SpeechRecognition`, `speechSynthesis`).
- **AI APIs & pretrained models:**
  - [DeepSeek API](https://platform.deepseek.com/) (`deepseek-chat`) — Writing 4-band grading, Speaking partner grounding, Speaking reports.
  - [Google Gemini API](https://ai.google.dev/) (`gemini-2.5-flash`, `gemini-2.5-flash-preview-tts`, optional `gemini-3.8-live`) — turn-based Speaking STT/reply/TTS and optional Live voice.
  - [Microsoft Azure AI Speech](https://azure.microsoft.com/en-us/products/ai-services/ai-speech) *(optional)* — Pronunciation Assessment when operator-configured.
- **Open-licensed media:** Speaking Part 2 photographs are sourced from Wikimedia Commons; per-image author, source page, and license metadata are documented in [`assets/speaking/CREDITS.json`](../assets/speaking/CREDITS.json).
- **Development & test tooling (dev-only):** [Playwright](https://playwright.dev/python/) (Apache-2.0) and [HTTPX](https://www.python-httpx.org/) (BSD-3-Clause), run via `uv`.
- **AI coding assistants:** AI coding assistants (Claude and Gemini) were used during development for implementation, refactoring, automated test writing, and documentation editing, with all code reviewed, tested, and verified by the author.
- **Trademarks:** Cambridge and B2 First are trademarks of Cambridge University Press & Assessment. B2 First Tracker is an independent educational project and is not affiliated with or endorsed by Cambridge.
