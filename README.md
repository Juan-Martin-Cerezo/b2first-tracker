# B2 First Tracker

<p align="center">
  A study tracker that closes the feedback gap of preparing for the Cambridge B2 First alone.<br>
  It logs sessions in three taps, diagnoses which exam parts are weak, plans the week from that<br>
  diagnosis, and grades Writing against the official Cambridge band descriptors.
</p>

<p align="center">
  <a href="https://vps-server.tail40095b.ts.net"><b>Live demo</b></a> ·
  <a href="SUBMISSION.md">How it was built</a> ·
  <a href="#quick-start">Run locally</a>
</p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-3f3f46">
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-3f3f46">
  <img alt="Zero dependencies" src="https://img.shields.io/badge/dependencies-none-3f3f46">
  <img alt="Single file frontend" src="https://img.shields.io/badge/frontend-1%20html%20file-3f3f46">
</p>

<table>
  <tr>
    <td width="72%"><img src="docs/screenshots/desktop.webp" alt="Today view with the session log, streak and exam countdown"></td>
    <td width="28%"><img src="docs/screenshots/mobile.webp" alt="Mobile layout with the quick-log button"></td>
  </tr>
  <tr>
    <td align="center"><sub>Desktop: today view, streak and the log of every session</sub></td>
    <td align="center"><sub>Mobile: same tracker, quick-log in one corner</sub></td>
  </tr>
</table>

## What it is

A self-hosted study tracker for the **Cambridge B2 First (FCE)** exam. One HTML file, one
Python file, no database: your progress lives in the browser's `localStorage` and syncs to a
JSON file on whatever machine serves it. It covers the whole preparation loop — practice log,
streak, exam-mode timers, per-part analytics, error taxonomy, and an AI writing examiner that
scores against the official Cambridge assessment scales.

## Why it exists

Writing is **25% of the B2 First score**, and it is the one skill you cannot self-mark. Practice
tests come with answer keys for Reading and Listening; nothing tells you whether your essay is a
Band 3 or a Band 4, or which of the four criteria is dragging the score down. That gap is what
this project attacks.

The second problem is habit. A tracker that records five sessions in sixty-seven days is not a
tracker, it is a museum. Logging a session had to cost less than fifteen seconds on a phone, so
the quick-log sits one tap away from any screen, and the streak is derived from the log instead
of being a separate field that can drift out of sync.

## Who it is for

- **Candidates studying alone**, without a teacher or an examiner to mark their writing.
- **People preparing on a low budget**, who buy one or two official books and need to extract
  everything from them.
- **Anyone who wants their study data to stay theirs**: the app runs on a Raspberry Pi in a
  living room, writes to a plain JSON file, and only sends the text you choose to correct.

It is deliberately not a course. There is no content behind a paywall, no account to create,
and no cloud to trust.

## What it does

| Feature | What it actually does |
| --- | --- |
| **Quick-log** | Records type, part, score and minutes in three taps, with sane defaults per part |
| **Streak** | Derived from the log, not stored: today counts, a missed day is shielded once a week, exam days never break it |
| **Diagnostic** | 12 original items across all seven exam parts, 10 minutes, produces three ranked weaknesses |
| **Weekly plan** | Deterministic rules, not a model: three slots on your weakest parts, one Writing, one Listening, adjusted by your error taxonomy |
| **Writing examiner** | Four Cambridge criteria (Content, Communicative Achievement, Organisation, Language), 0–5 each, cited evidence, two mandatory weaknesses per criterion, three rewritten sentences |
| **Error taxonomy** | Every miss is tagged `L-GAP`, `G-ERR`, `T-MIS` or `T-LIM`, so the plan can target the cause instead of the symptom |
| **Analytics** | Four SVG panels, no chart library: progress over time, per-part accuracy, error mix, score consistency |
| **Exam mode** | Real timings for Reading & Use of English, Listening and Writing |

## The grading is calibrated, not generous

A corrector that says 19/20 to a mediocre essay is worse than no corrector: you stop studying
what is missing. The first version did exactly that. Two changes fixed it.

1. Before scoring, the model must list **two concrete weaknesses per criterion**. If it can name
   two, that criterion cannot be a 5.
2. For any criterion scored 4 or 5 it must explain **why it is not one band higher**.

Measured on three graded samples of different quality:

| Sample | Before | After |
| --- | --- | --- |
| Weak (A2, frequent basic errors) | 19/20 | **9/20** |
| Typical B2 | 19/20 | **14/20** |
| Strong (C1-leaning, inversions, passives) | 19/20 | **20/20** |

The rubric itself is not invented: it is transcribed from the official *B2 First Handbook*
(pages 32–35), with the page number recorded next to every band descriptor in `prompts.py`.

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | One `index.html`, vanilla JS and CSS | No build step, no `node_modules`; it opens on any phone and Playwright can drive it directly |
| Backend | `server.py`, Python standard library only | No pip install, no framework, no version drift on a small server |
| Storage | JSON files on disk, with rotated backups | Readable, diffable, trivial to back up; a database would add a dependency without adding a feature |
| AI | Provider-agnostic proxy, bring your own key | The key never leaves your device except to reach the proxy; the repository ships no credentials |

## Quick start

```bash
git clone https://github.com/Juan-Martin-Cerezo/b2first-tracker.git
cd b2first-tracker
python3 server.py
```

Open `http://127.0.0.1:8088`. That is the whole installation: no database, no migrations, no
environment file required.

Optional exam material can be dropped into `~/Descargas/b2-first/`; the tracker indexes whatever
it finds and hides the section when the directory is empty.

## AI writing correction (bring your own key)

The corrector needs a provider key, and the key is yours:

1. Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (Gemini) or
   [platform.deepseek.com](https://platform.deepseek.com) (DeepSeek).
2. Paste it in the **PLAN** tab; it is stored in `localStorage` on that device only.
3. On the server side the key can also come from the environment:

```bash
# outside the repository, chmod 600
B2_AI_PROVIDER=deepseek
B2_AI_MODEL=deepseek-chat
B2_AI_KEY=...
```

`POST /api/ai/writing` is a proxy: it validates the request, enforces a 25-second timeout, rate
limits to 10 requests per minute and 60 per hour per IP, validates the model's JSON against a
strict schema, and returns `422` when the shape is wrong. Keys are never logged and never written
to disk. **The repository contains no keys.**

## Demo mode

```bash
B2_DEMO=1 python3 server.py
```

In demo mode registration, login and progress sync all return `403`; the tracker runs entirely on
`localStorage`. This is how the public instance is served: a visitor can use every feature without
being able to read or write the owner's data.

## Docker

```bash
docker build -t b2first .
docker run -p 8088:8088 -e B2_DEMO=1 b2first
```

## Tests

No mocks of the app itself: the suites drive a real browser against a real server.

| Suite | Covers |
| --- | --- |
| `test_final.py` | Main UI: all views render, no JS errors |
| `test_sync.py` | Progress persistence, backup rotation, invalid payloads |
| `test_personalization.py` | Per-user data isolation |
| `test_ai.py` | The writing proxy: validation, schema rejection, rate limit, no key leakage |
| `test_diag.py` | Diagnostic flow end to end, error taxonomy writes, result maths |
| `test_demo.py` | Demo mode returns `403` on every write route |
| `test_streak.py` | Streak rules: shield, gaps, future dates, records |
| `test_graf.py`, `test_exam.py`, `test_rot.py` | Analytics, exam mode, rotation |

```bash
cd tests
uv run --with playwright python test_final.py
```

## Data and privacy

- Progress lives in `localStorage` and in `data/progress.json` on your machine, with the previous
  version kept as a rotated backup.
- `data/` is gitignored: no personal progress is ever committed.
- The only outbound call is the text you paste into the corrector, sent with your own key.
- The public demo cannot write to `data/`; those routes answer `403`.

## Project layout

```
index.html          the entire frontend: views, timers, charts, quick-log, streak
server.py           standard-library HTTP server, auth, sync API, AI proxy
store.py            storage seam (swap JSON for SQLite without touching the API)
prompts.py          Cambridge band descriptors transcribed from the official handbook
material/           diagnostic items and local exam material index
tests/              Playwright suites
docs/               submission notes, video script, screenshots
```

## License

MIT © 2026 Juan Martín Cerezo
