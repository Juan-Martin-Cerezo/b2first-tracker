# AGENTS.md — Guide for anyone working on this project

> Read this whole thing before touching anything. 15 minutes here save hours.

## Who the user is

**Juan**, 16 years old, secondary technical school student (ET21 Computación, CABA).
He prepares **on his own** for the Cambridge B2 First, aiming at **Grade A / C1**.
He uses the product on his phone and his PC. He is a native Spanish (rioplatense)
speaker, but the product UI is now in English: everything — UI, code comments,
and messages — is written in English.

## Hard rules of the project

1. **No piracy, ever.** Do not link to, search for, or suggest pirated copies of books
   or exams. Always: free official Cambridge material, or buy cheap
   (used on MercadoLibre / Buscalibre).
2. **No made-up data.** Prices, metrics, results: everything verified.
   If you cannot verify something, say so and leave it out.
3. **ARS prices verified on the product page** (on Buscalibre the `data-precio`
   in the listing lies by ~1.5-1.6x; the real price is on the product page).
4. **Warn before deleting/restarting** system things (the user explicitly asked
   for this). Deploying with `systemctl restart b2first` is safe and expected.
5. **Do not touch** fcc-claude's `.env`/config or other people's services
   (docker-proxy on 8080).

## Stack (deliberately, the bare minimum)

- **Frontend**: a single `index.html` (vanilla HTML+CSS+JS). **Zero frameworks,
  zero build, zero node_modules.** This way it opens on any device and can be
  tested with Playwright without a compilation chain.
- **Backend**: `server.py`, Python **stdlib only** (http.server). No need for
  pip install. Do not add dependencies without discussing it first.
- **Data**: everything in the browser's `localStorage` (key `b2first_tracker_v1_<userId>`,
  the pre-multiuser key `b2first_tracker_v1` is still read as a fallback) and
  **synced with the server**: `data/users/<id>/progress.json` + rotated backups in
  `data/users/<id>/backups/`. Every `save()` pushes to `/api/progress` (PUT) and opening
  the page pulls (GET). Rule: **last write wins** — the server backs up the previous
  version. There is no database: JSON files under `data/` (gitignored).

## Data model (summary)

The `D` object persists in localStorage. See the `<script>` header in `index.html`
for the full reference with examples:

- `D.log[]` — practice history: `{type, date, part?, correct?, total?, min?, score?, kind?, s1?, s2?, p2?, note?}`
  - types: `ue` (UoE parts 1-7) · `w` (Writing with `kind`) · `l` (full Listening /30, `p2`=Part 2 mistakes) · `lp` (Listening by part) · `sp` (Speaking) · `rue` (full R&UoE, exam mode) · `fw` (Full Writing)
- `D.errs[]` — errors with taxonomy: `L-GAP` / `G-ERR` / `T-MIS` / `T-LIM`
- `D.profile` — the intake profile (first-run wizard): `{examDate, targetGrade (A|B|C), skills {rue,w,l,sp} 1-5, hoursWeek (2|4|6|10), days [mon..sun], struggles [taxonomy codes], strugglesDeclared [labels], declaredAt}`
- `D.diag` — diagnostic result (or `null`); `diag.weakest` is the ranked list of weak parts (1-7) that seeds the weekly plan
- `D.stage` — stage 0..2 · `D.overrides` — gates manually marked · `D.weekOverrides` — manually chosen rotation
- `D.onboarded` — intake done · `D.sessionOffset` — sessions shifted with "Fast-forward (+1)" · `D.mat` — material index · `D.updated_at` — last save timestamp
- `D.settings` — everything configurable (SETTINGS_DEFAULT in the JS): schedules, timers,
  rotation cycles (`rueCycle`/`wCycle`/`lCycle`/`spCycle`), gate thresholds (`e0`/`e1`/`e2`)

The synced progress document carries `schema_version` (currently `2`, `store.py`:
`PROGRESS_SCHEMA`). A document without it is migrated on read and the original is copied to
`backups/pre-migration-<ts>.json` first.

## Accounts and auth (multi-user)

- `data/users.json` — one record per account: `{id, name, color, created, salt, hash, algo, iters}`;
  passwords are PBKDF2-HMAC-SHA256 (600,000 iterations; SHA-256 and 200k PBKDF2 hashes are
  re-hashed transparently on the next successful login). Policy: 10+ characters, the 200 common
  passwords embedded in `store.py`, not equal to the username.
- `data/tokens.json` — keys are `sha256(token)`, never the token; values carry
  `{user_id, exp, issued, absolute_exp, last_seen, ua_hash}`. 30-day sliding TTL capped by a
  90-day `absolute_exp` that is never extended.
- The frontend keeps its session in `localStorage.b2first_user = {id, name, color, token}`
  and sends `Authorization: Bearer <token>`; a password change revokes **every** session
  (including the current one) and returns a fresh token that the UI stores.
- Per-account storage: `data/users/<id>/progress.json` + `backups/` (20 kept), directories
  `0700`, files `0600`. A token can only touch its own account (`403` otherwise).
- Limits (server-side, `server.py`): register 5/h/IP, login 10/10min/IP + 20/h/username,
  exponential backoff 5/15/60 s after the 3rd/4th/5th failure, lockout 15 min after 5 failures,
  progress writes 2 MB + 60/min, AI corrections 10/min + 60/h per IP and 8/day/account +
  80/day/instance (`B2_AI_DAILY_*`).
- `data/audit.log` (0600, rotates at 5 MB) records auth/security events in a SHA-256 hash chain
  (`prev` per line); `tools/verify_audit.py` exits non-zero if a line was edited or deleted;
  `/api/audit` returns only the caller's own events. `GET /api/health` is the liveness probe.
  `/.well-known/security.txt` is the RFC 9116 disclosure file.
- Registration is open by default; `B2_REGISTER=closed` freezes new accounts.
- Password recovery is local only: `tools/reset_password.py`. There is no email flow.

**Golden rule when adding features**: anything new the user wants to
"be able to change" goes into `D.settings` + inputs in the PLAN tab, with a sane default.

## Code structure (order inside the `<script>`)

```
header (architecture + data model)
AUTH OVERLAY / ACCOUNT  → login + register, export, change password, delete account
ONBOARDING + TOUR       → 6-step intake wizard (writes D.profile) + 3 coach marks
SESSION INIT            → LOAD / SAVE (per user, userKey()) + sanitize on load
SERVER SYNC             → syncPush/syncPull + footer badge (save() triggers the push)
TIMER + SESSION STUDIO  → makeTimer, interactive steppers, solo/single-part modal
LIVE STUDIO (S1)        → mic + AudioWorklet VAD (from a Blob) + rAF HUD
                          (liveOpen / liveStop / liveDiscard; window.LIVE state)
SAVE HANDLERS           → saveUE / saveWR / saveL / saveSP / saveFull
GATES / PLAN / WEEKLY   → calcGates, renderPlan, buildWeeklyPlan(D) (pure, no AI)
EXAM + PARTS            → exam mode (EX_DUR, real timings) + PARTS[] (15 exercises)
LOG TABLE + STATS       → renderLog + inline editing + renderStats
ERRORS                  → renderErrs + taxonomy logging
BOOKS + MATERIAL / MAT  → BUY_BOOKS (30 books) + material index (libros.json)
CHARTS                  → renderGrafEvol/Part/Err/Cons (pure SVG, no dependencies)
TODAY VIEW / STREAK     → renderToday (rotation + banner) / streak maths / setOv
QUICK-LOG               → 3-tap modal (FAB) + toast
METRICS                 → weekly / progress / analytics panels
IA WRITING CORRECTOR    → AI corrector proxy calls + result panel
INITIAL DIAGNOSTIC      → 12 cold-start items (material/diagnostico.json)
NAV + INIT              → central refreshAll / loadMaterial
DARK MODE / DEMO MODE   → theme toggle (b2first_theme) + demo guards
```

**refreshAll()** is the central render: it is called after every data change.
If you add a new render, add it to refreshAll().

## How to test

Every suite is a standalone script. `tests/helpers.py` registers a throwaway `test-runner`
account (`B2_TEST_USER` / `B2_TEST_PASS`) and logs in via the API, so nothing depends on the
owner's password.

```bash
cd tests
uv run --with playwright python test_final.py    # main suite
```

Two groups:

- **Live service** (must be running on `http://127.0.0.1:8088`): `test_final`, `test_layout`,
  `test_mobile`, `test_tracker`, `test_personalization`, `test_plan`, `test_streak`,
  `test_schedule_advance`, `test_rot`, `test_exam`, `test_speaking_metrics` (fake mic, 90 s real-time run).
- **Own server + temporary `data/`** (safe anywhere, never touch real data): `test_sync`,
  `test_graf`, `test_demo`, `test_register`, `test_multiuser`, `test_ai`, `test_ai_guard`,
  `test_onboard`, `test_diag`, `test_hardening`, `test_legacy_guard`, `test_security2`,
  `test_security3`, `test_server_hardening`, `test_telemetry`.

The delegation runner gates each phase with `RUN_TESTS` (default `test_sync.py
test_personalization.py`) — see [delegacion/README.md](delegacion/README.md).

## Known pitfalls (do not repeat them)

- **Proxied requests carry `X-Forwarded-For`** (Tailscale Funnel / the TLS proxy in front):
  the tokenless legacy owner path is refused there (`401`); only a direct local request may
  use it. Anything auth-related must send a Bearer token.
- **Tokens are stored hashed** (`sha256(token)` in `data/tokens.json`): you cannot recover a
  session from disk; get a fresh one from `/api/login` the way `tests/helpers.py` does.
- **Backup timer**: `b2f-backup.timer` runs `~/.hermes/scripts/b2f_backup.sh` daily at 03:30
  (verified tarball, keeps 14). Do not schedule heavy jobs in that window and never edit that
  script without re-running a backup — every run must keep passing its test restore.
- **Writing 2022 PDFs = image-only** (no text layer): prompts cannot be extracted
  with pypdf. The workaround is direct links + approximate location in the guide.
- **Port 8080 taken** by docker-proxy → the service runs on **8088**.
- **MercadoLibre blocks by IP** from the Pi/VPS (wall + 403). The only legitimate route
  is the user's real Chrome via CDP (see skill `linux-desktop-control`).
- **Buscalibre**: real price = product page, not the listing's.
- Material file names contain spaces → use `quote()` in URLs.
- `node --check` to validate the JS extracted from the HTML (never deploy with a syntax error).
- The test suites that import `server.py` via `sys.path` change its `DATA_DIR`/`PORT`
  BEFORE starting the server — never let them touch the real `data/`.
- Per-save backup rotation: the first PUT creates no backup (there is nothing previous to
  back up), and the last 20 per user are kept (`BK_KEEP`).

## Deploy

The repo is the single source of truth: `systemd` runs `server.py` from here
(WorkingDirectory=/home/juan/b2first-tracker). After editing:

```bash
python3 -c "import re;open('/tmp/app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/app.js
sudo systemctl restart b2first
```

## Roadmap / pending ideas (talk to Juan first)

- Speaking Parts 3-4 simulation with the AI as a partner.
- SQLite storage behind the `store.py` seam for instances that outgrow JSON files.
- More material (purchased books → scan/add PDFs to ~/Descargas/b2-first).
- ~~Remote repo (GitHub)~~ **DONE** (github.com/Juan-Martin-Cerezo/b2first-tracker).
- ~~Automatic Writing correction~~ **DONE** (AI tab, calibrated Cambridge bands).
- ~~Progress persistence across devices~~ **DONE** (per-account `progress.json` + backups).
- ~~Charts section~~ **DONE** (CHARTS tab, 4 SVG panels).
