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
- **Data**: everything in the browser's `localStorage` (key `b2first_tracker_v1`) and
  **synced with the Pi** (`data/progress.json` + backups in `data/backups/`).
  Every `save()` pushes to `/api/progress` (PUT) and opening the page pulls
  (GET). Rule: **last write wins** — the server backs up the previous version.
  There is no database: it is a JSON file in the repo.

## Data model (summary)

The `D` object persists in localStorage. See the `<script>` header in `index.html`
for the full reference with examples:

- `D.log[]` — practice history: `{type, date, part?, correct?, total?, min?, score?, kind?, s1?, s2?, p2?, note?}`
  - types: `ue` (UoE parts 1-7) · `w` (Writing with `kind`) · `l` (full Listening /30, `p2`=Part 2 mistakes) · `lp` (Listening by part) · `sp` (Speaking) · `rue` (full R&UoE, exam mode) · `fw` (Full Writing)
- `D.errs[]` — errors with taxonomy: `L-GAP` / `G-ERR` / `T-MIS` / `T-LIM`
- `D.stage` — stage 0..2 · `D.overrides` — gates manually marked · `D.weekOverrides` — manually chosen rotation
- `D.settings` — everything configurable (SETTINGS_DEFAULT in the JS): schedules, timers,
  rotation cycles (`rueCycle`/`wCycle`/`lCycle`/`spCycle`), gate thresholds (`e0`/`e1`/`e2`)

**Golden rule when adding features**: anything new the user wants to
"be able to change" goes into `D.settings` + inputs in the PLAN tab, with a sane default.

## Code structure (order inside the `<script>`)

```
header (architecture + data model)
SETTINGS_DEFAULT / load / save / helpers
SYNC             → syncPush/syncPull + footer badge (save() triggers the push)
TIMER          → makeTimer + session timers (read D.settings)
SAVE HANDLERS  → saveUE / saveWR / saveL / saveSP / saveFull
LOG TABLE      → renderLog + inline editing + renderStats
GATES          → calcGates (reads D.settings) / renderGates / advanceStage
ERRORS         → renderErrs + taxonomy logging
BOOKS          → BUY_BOOKS (25 books, verified prices) + MATERIAL (libros.json)
CHARTS       → renderGrafEvol/Part/Err/Cons (pure SVG, no dependencies)
PLAN           → renderPlan / savePlan / resetPlan / applyTimers
EXAM+PARTS  → exam mode (EX_DUR, real timings) + PARTS[] (15 exercises)
TODAY VIEW     → renderToday (rotation + banner) / setOv
NAV + INIT     → central refreshAll / loadMaterial
```

**refreshAll()** is the central render: it is called after every data change.
If you add a new render, add it to refreshAll().

## How to test

```bash
# The service must be running (http://127.0.0.1:8088)
cd tests
uv run --with playwright python test_final.py    # main suite
uv run --with playwright python test_sync.py     # persistence + backups (own server on 8099)
uv run --with playwright python test_graf.py     # charts (own server on 8100)
# test_exam.py and test_rot.py cover exam mode and rotation
```

The sync/graf tests spin up their own test server on an alternative port
with a temporary `data/`: they do not touch the real service or your progress.
The rest run against the active service on 8088.

## Known pitfalls (do not repeat them)

- **Writing 2022 PDFs = image-only** (no text layer): prompts cannot be extracted
  with pypdf. The workaround is direct links + approximate location in the guide.
- **Port 8080 taken** by docker-proxy → the service runs on **8088**.
- **Tailscale MagicDNS is off** → use the direct IP `100.112.213.66` (the Pi is named `vps-server`).
- **MercadoLibre blocks by IP** from the Pi/VPS (wall + 403). The only legitimate route
  is the user's real Chrome via CDP (see skill `linux-desktop-control`).
- **Buscalibre**: real price = product page, not the listing's.
- Material file names contain spaces → use `quote()` in URLs.
- `node --check` to validate the JS extracted from the HTML (never deploy with a syntax error).
- The sync/graf tests import `server.py` via `sys.path` and change its `DATA_DIR`/
  `PORT` BEFORE starting the server — never let them touch the real `data/`.
- The backup is made by copying the previous file: the first PUT creates no backup
  (there is nothing previous to back up), and the last 20 are kept (`BK_KEEP`).

## Deploy

The repo is the single source of truth: `systemd` runs `server.py` from here
(WorkingDirectory=/home/juan/b2first-tracker). After editing:

```bash
python3 -c "import re;open('/tmp/app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/app.js
sudo systemctl restart b2first
```

## Roadmap / pending ideas (talk to Juan first)

- Remote repo (GitHub) so another agent can work from their own machine.
- Automatic Writing correction by the assistant (Senior Cambridge examiner role).
- Speaking Parts 3-4 simulation with the AI as a partner.
- More material (purchased books → scan/add PDFs to ~/Descargas/b2-first).
- ~~Progress persistence across devices~~ **DONE** (data/progress.json + backups).
- ~~Charts section~~ **DONE** (CHARTS tab, 4 SVG panels).
