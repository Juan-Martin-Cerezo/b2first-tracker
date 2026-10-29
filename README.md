# B2 First Tracker

A study portal and exam tracker built to prepare for the **Cambridge B2 First (FCE)** exam.

## What it is

B2 First Tracker is a single-file web application (`index.html`, 5,380 lines) paired with a pure Python standard-library HTTP server (`server.py`). It covers the full preparation workflow for Cambridge B2 First:

- **Scheduled study sessions & timers** — weekly rotation across all 15 exam parts with official Cambridge time limits (Reading & Use of English, Writing, Listening, Speaking) and a 3-tap mobile quick-log.
- **Daily streak & weekly goal** — derived directly from logged sessions in local time, including a weekly 1-day streak freeze shield (`🛡`) and a 5-day weekly target ring.
- **12-item cold-start diagnostic** — a 10-minute placement quiz covering all 7 parts of Reading & Use of English that populates the error log (`L-GAP`, `G-ERR`, `T-MIS`, `T-LIM`) and highlights the 3 weakest parts on day one.
- **Stage gates & progress charts** — 3 preparation stages (Foundations, Precision, Mastery) with automated metric gates and 4 SVG charts (Writing evolution, accuracy by part, error taxonomy breakdown, and weekly consistency).
- **AI Writing examiner** — grades Essays, Articles, Reports, Reviews, and Emails against the official Cambridge B2 First Writing assessment rubric (Content, Communicative Achievement, Organisation, Language, 0–5 each), quoting exact student sentences, listing 2 actionable weaknesses per criterion, and rewriting 3 weak sentences at B2+/C1 level.

## Why it's built this way

| Decision | Reason |
|---|---|
| Single-file `index.html` (5,380 lines, vanilla HTML/CSS/JS, no build step) | Opens instantly on desktop and mobile with zero bundler, transpiler, or `node_modules` maintenance overhead. |
| `server.py` using only the Python 3 standard library | Runs out of the box on a Raspberry Pi, VPS, or container without `pip install` or dependency drift. |
| Atomic JSON storage on disk (`store.py` + rotating backups) | Keeps user progress human-readable and easy to back up while isolating filesystem access behind a 6-function seam ready for SQLite. |
| Hardcoded Cambridge rubric + strict server-side schema validation | The LLM scores against fixed assessment descriptors in `prompts.py`, and `server.py` rejects any malformed or out-of-range JSON (`422`) before it reaches the UI. |

## Quick start

No `npm install`, no virtualenv, and no build step required (Python 3.10+):

```bash
git clone https://github.com/Juan-Martin-Cerezo/b2first-tracker.git
cd b2first-tracker
python3 server.py
```

Open `http://127.0.0.1:8088` in your browser.

## AI writing correction (bring your own key)

**This repository does not include any API key or token.**

To use the AI Writing examiner:
1. Open the **PLAN** tab (or follow the link from the **✨ AI** tab) and paste your API key (DeepSeek or Gemini) into the API key field.
2. Your key is stored **only in your browser's `localStorage`** (`D.settings.aiKey`) and is stripped before any progress sync.
3. When you submit a Writing task in the **✨ AI** tab, the browser sends the key in the request body to `/api/ai/writing`. `server.py` acts strictly as a stateless proxy to the upstream provider and **never logs, caches, or persists your key on disk**.

For personal self-hosted setups, you can also pass `B2_AI_KEY` and `B2_AI_PROVIDER` (`deepseek` or `gemini`) as environment variables to `server.py`.

## Demo mode

To expose the tracker publicly without user accounts or server-side persistence:

```bash
B2_DEMO=1 python3 server.py
```

When `B2_DEMO=1` is set:
- `GET /api/config` returns `{"demo": true, "version": "1.0.0", "ai": true}`.
- `/api/register`, `/api/login`, `/api/logout`, `/api/me`, `/api/users`, and `/api/progress` (GET and PUT) all return `403 {"error": "modo demo: sin cuentas ni sincronización"}`.
- The frontend skips authentication and server sync, displays an amber demo banner at the top, and stores all sessions, diagnostics, and charts exclusively in the visitor's `localStorage`.

## Docker

```bash
docker build -t b2first . && docker run -p 8088:8088 -e B2_DEMO=1 b2first
```

The container uses `python:3.13-slim`, copies only the application code and static assets (`data/` is excluded via `.dockerignore`), and listens on `PORT` (default `8088`). `DATA_DIR` can also be overridden via environment variable.

## Tests

End-to-end and API regression tests live in `tests/` and run with Playwright (headless Chromium):

| Suite | Coverage |
|---|---|
| `test_final.py` | Mobile viewport (`390×844`) layout, zero horizontal overflow, session cards, weekly rotation, 15 exam parts, stage gates, and zero JS errors. |
| `test_sync.py` | Multi-user auth, PBKDF2 password hashing, `GET`/`PUT /api/progress`, and automatic backup rotation in `store.py`. |
| `test_graf.py` | All 4 SVG chart panels (empty states and populated rendering) plus mobile responsiveness. |
| `test_personalization.py` | Per-user schedules, dynamic session labels, onboarding flow, and profile modal. |
| `test_streak.py` | Derived streak logic: empty log, consecutive days, 1-day freeze shield (`🛡`), 2-day gap reset, future date filtering, longest record, and 3-tap quick-log. |
| `test_ai.py` | `/api/ai/writing` validation (`400`/`422`/`429`/`502`), DeepSeek & Gemini wire formats, 8 criterion weaknesses, zero key leakage in logs/errors, and ✨ AI tab E2E flow. |
| `test_diag.py` | `/diagnostico.json` schema (12 items across Parts 1–7), no `explain` leakage in DOM during quiz, 12/12 and 0/12 scoring, error taxonomy injection, and weakest-part navigation. |
| `test_demo.py` | `B2_DEMO=1` lockdown (`403` on auth and progress endpoints), `/api/config` detection, demo banner rendering, `B2_DEMO=0` fallback, and zero JS errors in Playwright. |

Run any suite from `tests/`:

```bash
cd tests && uv run --with playwright python test_demo.py
```

## Data & privacy

- In self-hosted mode, data lives in your browser's `localStorage` and in the local `data/` directory on your machine (gitignored and excluded from Docker builds).
- In demo mode (`B2_DEMO=1`), data lives exclusively in the visitor's browser `localStorage`.
- No analytics, telemetry, or third-party scripts are loaded. Nothing leaves your machine except the Writing text you explicitly submit for AI grading using your own API key.

## License

Released under the [MIT License](LICENSE). Copyright (c) 2026 Juan Martín Cerezo.
