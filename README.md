# B2 First Tracker

<p align="center">
  A study system for people preparing the Cambridge B2 First <b>on their own</b>.<br>
  It decides what to practise today, logs the session in three taps, tracks all four papers,<br>
  and marks your Writing against the official Cambridge band descriptors.
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
    <td align="center"><sub>Desktop: today view, exam countdown, streak and the Week A/B rotation</sub></td>
    <td align="center"><sub>Mobile: same tracker, quick-log button in one corner</sub></td>
  </tr>
</table>

## What it is

A self-hosted study tracker for the **Cambridge B2 First (FCE)** exam. One HTML file, one
Python server, no database: progress lives in the browser's `localStorage` and syncs per
account to JSON files on whatever machine serves it.

It covers the whole preparation loop, not one skill: intake interview, profile-driven weekly
plan, practice log, streak, exam-mode timers, per-part analytics across all four papers,
an error taxonomy, and an AI examiner for Writing scored against the official Cambridge
assessment scales.

## The problem

Preparing for the B2 First alone has three failure modes, and none of them is "not enough
material". The internet is full of practice tests.

**1. Nobody tells you whether your Writing is good.** Writing is 25% of the score and it is
the one paper whose answer key cannot exist: two essays can both be "correct" and one is a
Band 4 while the other is a Band 2. Reading and Listening practice tests come with answers,
so they tell you. Writing does not, and neither does a friend who speaks English but has never
seen a Cambridge scale. So people write essay after essay with no idea which of the four
criteria is dragging their score down — and they practise the skill where the return is
unmeasurable.

**2. Nobody tells you what to study today.** Materials come in books of ten tests and forty
exercises. The first week is easy: you start at page one. By week three the real question is
*do I do Listening Part 3 again, or Writing Part 2, or the Use of English I keep failing?*
Answering it takes ten minutes of second-guessing, and on a Tuesday night with forty minutes
free, ten minutes of doubt is enough to skip the session. Most self-study plans die from
decision fatigue, not from laziness.

**3. Progress is invisible, so consistency collapses.** A candidate who does five sessions in
sixty-seven days believes they are studying — they remember the effort, not the frequency.
Without a record, there is no way to see that the last Listening test was three weeks ago, or
that your Part 4 accuracy has not moved since March.

That is the gap this project attacks: **the feedback loop and the decision of what to do next**,
which is exactly the part a teacher normally provides and the part no PDF can.

## Who it is for

- **Self-taught candidates**, the ones with no teacher and no class: the app behaves like the
  part of a teacher that is measurable — it diagnoses, plans the week, and marks the writing.
- **People on a low budget**, who buy one or two official books and need to extract everything
  from them instead of paying for weekly corrections.
- **Candidates who already failed once**, or who studied at an academy for a year and plateaued
  at B1+ because nobody ever told them *which* part was costing them the grade.
- **Adults returning to English** after years away, who need a structure that fits two hours a
  week and does not assume a classroom or a cohort.
- **Anyone who wants their study data to stay theirs**: it runs on a Raspberry Pi in a living
  room, writes plain JSON, and only sends the text you explicitly choose to have corrected.

It is deliberately not a course. There is no content behind a paywall and no cloud to trust;
an account is just a name and a password — no email is asked for. The books you already own are
the material; the app is the coach that tells you which page of them to open tonight.


## What it does

| Feature | What it actually does |
| --- | --- |
| **Onboarding intake** | Six-step intake before the first session: exam date, target grade, self-rated skills, hours per week, available days, and what is hard. The answers seed the weekly plan, so the app is useful before you have logged anything |
| **Quick-log** | Records type, part, score and minutes in three taps, with sane defaults per part |
| **Streak** | Derived from the log, not stored: today counts, a missed day is shielded once a week, exam days never break it |
| **Diagnostic** | 12 items across the seven Reading & Use of English parts, 10 minutes, ranks the weakest parts and feeds the error taxonomy |
| **Weekly plan** | Deterministic rules, not a model: slots on your 3 weakest parts (diagnostic) or lowest-rated skills (intake), slot count from hours per week (2h→3, 10+h→6), days from your intake, one reinforcement slot per flagged struggle — each with its reason |
| **Writing examiner** | Four Cambridge criteria (Content, Communicative Achievement, Organisation, Language), 0–5 each, cited evidence, two mandatory weaknesses per criterion, three rewritten sentences |
| **Error taxonomy** | Every miss is tagged `L-GAP`, `G-ERR`, `T-MIS` or `T-LIM`, so the plan can target the cause instead of the symptom |
| **Analytics** | Four SVG panels, no chart library: progress over time, per-part accuracy, error mix, score consistency |
| **Exam mode** | Real timings for Reading & Use of English, Listening and Writing |
| **Recent activity** | Your account's security log (logins, password changes, deletion) in the Account view, straight from the server's audit log — only your own events |
| **Accounts** | Multi-user: register with a name and a password, sync across devices, and export, change password or delete your account |
| **Interface** | English UI with light and dark themes; the choice is saved per device |

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

Every setting is optional and lives in `B2_*` environment variables — the complete list the code
reads:

| Variable | Default | Effect |
| --- | --- | --- |
| `B2_DEMO` | `0` | `1` = demo mode: account and sync routes answer `403`, state stays in `localStorage` |
| `B2_REGISTER` | `open` | `closed` = no new accounts (existing ones still log in) |
| `B2_OWNER_PASSWORD` | `b2first` | Password given to the owner account created when migrating old single-user data |
| `B2_PUBLIC_HEALTH` | `0` | `1` = `GET /api/health` may expose absolute paths |
| `B2_HOST` | `127.0.0.1` | Bind address. The public entrypoint is the local TLS proxy (Tailscale Funnel → `127.0.0.1:8088`); LAN access requires `B2_HOST=0.0.0.0`, and even then the nftables firewall is the real barrier — not this bind |
| `B2_ALLOWED_HOSTS` | (empty) | Comma-separated `Host` allowlist. Empty = no check; a request with an unlisted `Host` gets `421` |
| `B2_RATE_USER_API` | `600` | Requests/min per authenticated account (bucketed by `user_id`, not by IP) |
| `B2_RATE_IP_AUTH` | `30` | Requests/min per IP for `login`, `register` and `password` |
| `B2_RATE_IP_ANON` | `300` | Requests/min per IP for the API without a valid token (`B2_RATE_IP_API` is accepted as an alias; `0` disables the bucket) |
| `B2_NO_CACHE` | `0` | `1` disables the static gzip/ETag cache, for measuring the uncached baseline only |
| `B2_CONNECTION_LIMIT` | `512` | Simultaneous sockets; above it the server answers `503` + `Retry-After: 1` |
| `B2_AI_PROVIDER` | `deepseek` | Provider used by the writing corrector |
| `B2_AI_BASE` | (empty) | Override the provider base URL |
| `B2_AI_MODEL` | (empty) | Override the model name |
| `B2_AI_KEY` | (empty) | Server-side provider key; users can still bring their own |
| `B2_AI_DAILY_TOTAL` | `80` | LLM calls per day for the whole instance (the ceiling that protects the Pi) |
| `B2_LICENSE_SECRET` | (empty) | 32+ byte secret that signs pro activation codes. Without it `POST /api/plan/redeem` answers `503`. Keep it out of the repo (systemd drop-in); generate with `python3 tools/issue_license.py --gen-secret` |
| `B2_AI_DAILY_PER_USER` | (unset) | **Legacy** emergency cap. Leave it unset: when set it overrides the plan allowance and responds with the old `daily AI quota reached` body |
| `B2_TEST_USER` | `test-runner` | Account the Playwright suites register (`tests/helpers.py`) |
| `B2_TEST_PASS` | `test-runner-pass-9` | Password for that account (`tests/helpers.py`) |

Optional exam material can be dropped into `~/Descargas/b2-first/`; the tracker indexes whatever
it finds and hides the section when the directory is empty.

## Capacity (measured, not estimated)

Measured on **2026-10-30** on the target host — **Raspberry Pi 5, 8 GB** (`free -m`: 8062 MB
total; `nproc`: 4) — with [`tests/test_capacity.py`](tests/test_capacity.py): the real
`server.py`, 100 concurrent clients, 10 seconds per pass. The IP buckets are disabled during the
capacity run (`B2_RATE_IP_ANON=0`) so the numbers show CPU/socket capacity, not the abuse guard.

| Pass | Requests in 10 s | Throughput | p95 | 503/429 |
| --- | --- | --- | --- | --- |
| `GET /`, static cache ON | 4,742 | 474 req/s | 270 ms | 0 |
| `GET /`, `B2_NO_CACHE=1` (previous behaviour) | 1,608 | 161 req/s | 790 ms | 0 |
| `GET /`, cache ON, **300 concurrent** | 4,175 | 418 req/s | 843 ms | 0 |

At 300 concurrent connections the server peaked at **45.2 MB RSS and 301 threads**, so the
512-connection cap stays. The cache is 2.9x better at p95 than re-gzipping on every request, and a
revalidating pass (`If-None-Match`) returns only `304`s with an empty body. The access log line is
included in all of the above.

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

## Accounts

Registration is open on the public instance, and every account gets its own progress file
and backup history under `data/users/<id>/` (directory `0700`, files `0600`).

| Protection | Limit |
| --- | --- |
| Registration | 5 / hour / IP |
| Login | 10 / 10 min / IP and 20 / hour / username |
| Authenticated API | 600 requests / min / **account** — a shared school/CGNAT IP cannot rate-limit other students |
| Anonymous API | 300 requests / min / IP |
| Login / register / password | 30 requests / min / IP |
| Progress write | 2 MB per save, 60 saves / min |
| AI calls (free plan) | 3 / day per account |
| AI calls (pro plan) | 60 / month per account |
| Speaking mocks (free / pro) | 1 / week (5 min) / 6 per month (90 min) |
| Instance ceiling | 80 LLM calls / day (`B2_AI_DAILY_TOTAL`) |
| Session token | 30 days, sliding |

### Plans

Every account starts on **free**. There are three effective plans:

| Plan | How you get it | AI corrections & reports | Speaking mocks | Pronunciation |
| --- | --- | --- | --- | --- |
| `free` | default | 3 / day | 1 / week (5 min) | preview |
| `byo` | paste your own provider key (Settings → AI provider) | unlimited for this app | whatever your key pays for* | preview |
| `pro` | activation code (or, later, a subscription) | 60 / month | 6 / month (90 min) | full |

\* the Gemini Live token still comes from the server, so mocks on a BYO key stay on the
free/pro allowance. Writing corrections and speaking reports go to the user's key and are
not metered.

Users who paste their own provider key are not charged against the instance quota — the
owner's key stays for people who just want to try it. Plan state lives in `data/plans.json`
and the meters in `data/usage.json` (both `0600`, gitignored); the progress document only
carries a read-only mirror so the UI can render it.

**Issuing a pro code** (stdlib only, run on the Pi):

```bash
# once: generate the signing secret and store it OUTSIDE the repo
python3 tools/issue_license.py --gen-secret   # copy the value into ~/.config/b2first/ai.env
# from a shell that carries the same secret as the server:
export B2_LICENSE_SECRET=...                  # never commit it
python3 tools/issue_license.py pro 30         # prints FT-PRO-1M-XXXX-XXXX-XXXX (single use)
python3 tools/issue_license.py --list         # issued codes as hashes + who redeemed them
```

The code is signed with HMAC-SHA256 and the server stores only `sha256(code)` in
`data/licenses.json`, so the ledger cannot be used to redeem anything. Redemption
(`POST /api/plan/redeem`) is limited to 5 attempts / hour / account and answers the same
`400 {"error":"invalid_code"}` for a wrong, reused or unknown code (no oracle). Expiry is
evaluated on read: once `until` passes, the next request is `free` again.

Every account can **export its data** as JSON, **change its password** (which invalidates the
other sessions) and **delete itself**, which removes the files from disk.

To lock an instance to a fixed set of accounts after you have created yours:

```bash
B2_REGISTER=closed python3 server.py
```

Requests that arrive through a proxy (Tailscale Funnel, Cloudflare) always carry
`X-Forwarded-For`, and the progress API requires a session token for those. Only a direct
local request may use the legacy no-token owner path.

## Demo mode

```bash
B2_DEMO=1 python3 server.py
```

In demo mode registration, login and progress sync all return `403`; the tracker runs entirely on
`localStorage`. The public instance does not use it: `GET /api/config` reports
`{"demo": false, "register": "open"}` and visitors create real accounts. Demo mode is for
installs where nobody should write data at all.

## Docker

```bash
docker build -t b2first .
docker run -p 8088:8088 -e B2_DEMO=1 b2first
```

## Tests

No mocks of the app itself: the suites drive a real browser against a real server. Every suite is
a standalone script; `tests/helpers.py` registers a throwaway account (`B2_TEST_USER`/
`B2_TEST_PASS`) so nothing depends on the owner's password.

| Suite | Covers |
| --- | --- |
| `test_final.py` | Main UI: every view renders, dark mode persists, contrast and focus rings, no JS errors |
| `test_layout.py` | Phase 27 layout gate: every view at 360/768/1440 px in English and Spanish — no horizontal scroll, no overlapping cards, no button under 40 px, nothing past the viewport, zero console errors |
| `test_mobile.py` | 390x844 layout: no horizontal overflow, bottom nav, quick-log button |
| `test_tracker.py` | Books and material views: cards, filters, links, audio players |
| `test_onboard.py` | Six-step intake wizard, `D.profile`, profile-driven plan, feature tour, empty states |
| `test_plan.py` | Deterministic weekly plan (`buildWeeklyPlan`) and its PLAN card |
| `test_diag.py` | Diagnostic end to end: item fetch, error taxonomy writes, result maths |
| `test_streak.py` | Streak rules: freeze shield, gaps, future dates, records, weekly goal |
| `test_schedule_advance.py` | Schedule rows and shifting sessions (`sessionOffset`) |
| `test_rot.py` | Week A/B rotation, per-skill cycles and manual overrides |
| `test_exam.py` | Exam-mode timers, pause, guides, exam-mode logging |
| `test_graf.py` | The four SVG charts and their empty states |
| `test_sync.py` | Progress persistence, backup rotation, invalid payloads |
| `test_personalization.py` | Per-account data isolation |
| `test_register.py` | Registration (open and closed), login, password change |
| `test_multiuser.py` | Accounts end to end: quotas, limits, export and delete |
| `test_ai.py` | Writing proxy against a mock provider: validation, `422` schema rejection, rate limits, no key leakage |
| `test_demo.py` | Demo mode returns `403` on every account and sync route |
| `test_hardening.py` | Id validation, concurrent writes, security headers, request ids, `/api/health`, schema migration, password reset |
| `test_legacy_guard.py` | The tokenless legacy owner path is unreachable through a proxied request |
| `test_security2.py` | Login lockout, constant-time compares, hashed tokens, payload schema, audit log |
| `test_server_hardening.py` | Raw-HTTP surface: URI/header/body limits, method allowlist (`405` + `Allow`), traversal and hidden-file guards, HSTS/COOP/CORP, banner hygiene, 500 without leaks |
| `test_capacity.py` | Measured capacity, not estimates: cached gzip + ETag/`304`, `touch` invalidation, 100-concurrent p95 against the `B2_NO_CACHE=1` baseline, per-user rate limits behind one IP |

```bash
cd tests
uv run --with playwright python test_final.py
uv run --with httpx python test_capacity.py
```

Thirteen suites (`test_ai`, `test_capacity`, `test_demo`, `test_diag`, `test_graf`, `test_hardening`,
`test_legacy_guard`, `test_multiuser`, `test_onboard`, `test_register`, `test_security2`,
`test_server_hardening`, `test_sync`) boot their own server on a temporary `data/` and never
touch the real one; the other nine run against the live service on `127.0.0.1:8088`.

## Security

- **Accounts are isolated**: each one gets its own `data/users/<id>/` (directories `0700`, files
  `0600`), and a session token for one account can never read another's data (`403`).
- **Limits and quotas**: 5 failed logins lock a username for 15 minutes, with exponential backoff
  (5/15/60 s) after the 3rd/4th/5th failure; authenticated API traffic is limited per account
  (600/min), anonymous traffic and credential endpoints per IP; the plans cap AI calls (3/day
  free, 60/month pro, 80/day across the instance) and activation codes are single-use,
  stored only as `sha256`, with 5 redemption attempts/hour/account.
- **Tokens hashed at rest**: `data/tokens.json` stores `sha256(token)`, never the token; sessions
  use a 30-day sliding TTL capped by a 90-day absolute limit; passwords are
  PBKDF2-HMAC-SHA256 with 600,000 iterations (older hashes are upgraded on login).
- **Audit log**: authentication and security events land in `data/audit.log` (never tokens,
  passwords or student text) in a SHA-256 hash chain; `tools/verify_audit.py` detects tampering
  and each account can see its own **Recent activity**.
- **Backups verified**: per-save rotation plus a daily tarball whose every run does a test
  restore and parses every JSON file before it counts.
- **Health check**: `GET /api/health` reports the data dir writable, `users.json` parsing and
  every account directory present (`200 {"ok": true}` / `503`).

Threat model, control checklist and the tested restore runbook: [SECURITY.md](SECURITY.md).
Reproducible external audit of the live instance: `bash tools/audit.sh` — 14/14 checks passed on
2026-10-30.

## Data and privacy

- **Privacy policy**: the app serves it at [`GET /privacy`](docs/PRIVACY.md) (linked from the
  footer and from the registration form). It documents exactly what is stored, retention
  windows, your export/delete rights, the AI data flow and Do Not Track support.
- The contact address ships as the explicit `TODO_OWNER_EMAIL` placeholder in `server.py`
  (`privacy_page()`) and `docs/PRIVACY.md`: replace that literal string with the real owner
  email in both files before deploying publicly. No email is invented anywhere.
- Progress lives in `localStorage` and in `data/users/<id>/progress.json` on your machine, with
  the previous version kept as a rotated backup.
- `data/` is gitignored: no personal progress is ever committed.
- **Product telemetry is privacy-first**: `POST /api/events` stores whitelisted usage events
  (never content, never free text) as JSONL in `data/events/` for 7 days, with the client IP
  stored only as a salted hash. Owner-only aggregates live at `GET /api/metrics`. Browsers
  sending `Do Not Track: 1` emit nothing at all.
- The only outbound call is the text you paste into the corrector, sent with your own key.
- Demo mode cannot write to `data/`; those routes answer `403`.

## Project layout

```
index.html          the entire frontend: views, timers, charts, quick-log, streak
server.py           standard-library HTTP server, auth, sync API, AI proxy
store.py            storage seam (swap JSON for SQLite without touching the API)
prompts.py          Cambridge band descriptors transcribed from the official handbook
material/           diagnostic items and local exam material index
tests/              Playwright suites
tools/              external audit script, password reset, rubric extractor
docs/               submission notes, video script, screenshots
```

## License

MIT © 2026 Juan Martín Cerezo
