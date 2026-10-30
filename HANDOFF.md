# HANDOFF

> Written 2026-10-30 by Hermes (agent) for whoever picks this up next: a human, or another agent.
> Read it top to bottom once. It is written to be enough on its own — every command in it was run
> on this machine on that date.

---

## 1. What this project is

**B2 First Tracker** — a self-hosted study system for people preparing the Cambridge B2 First
(FCE) exam on their own. It is a real product, deployed, with real accounts, not a demo.

- **Repo:** `~/b2first-tracker` · branch `feat/ia-hackathon` · public on GitHub as
  `Juan-Martin-Cerezo/b2first-tracker`
- **HEAD at handoff:** `f65c1c8` (docs: problem/audience rewrite + speaking plan)
- **Live URL:** `https://vps-server.tail40095b.ts.net` (Tailscale Funnel → `127.0.0.1:8088`)
- **Host:** Raspberry Pi, 4 GB, ARM, at home. Runs under systemd. No cloud, no database.
- **Context:** built for the Devpost hackathon "Build Your First AI App 2026". The submission
  video is **not recorded yet** and the Devpost form is **not submitted yet** — see §12.

The product answers three problems for a self-taught candidate: nobody marks the Writing (25% of
the score, unmarkable from an answer key), nobody decides what to practise today (decision
fatigue kills self-study plans), and progress is invisible (so consistency collapses). Read
`README.md` §"The problem" for the long version.

---

## 2. The user

**Juan**, 16, technical secondary school in CABA, Argentina. Preparing the B2 First alone,
targeting Grade A / C1. Native Spanish (rioplatense); the product UI, code comments, commits and
docs are **English** by his explicit choice. He uses the product on his phone and PC.

Hard rules he has stated, all still in force:

1. **No piracy.** Never link to or suggest pirated books/exams.
2. **No invented data.** Prices, metrics, results: verified or omitted. This handoff follows it —
   anything unverified is marked *(verify)*.
3. **Warn before destructive system actions** (reboot, mkfs, deleting other people's services).
   `systemctl restart b2first` is expected and safe.
4. **Do not touch** fcc-claude's `.env` or the docker-proxy on port 8080.
5. **UI/UX bar is high**: real dark mode (never `#000`, uses oklch), contrast ≥ 4.5:1 measured,
   44×44 hit areas, responsive, full English.

---

## 3. Architecture

### Stack, deliberately minimal

| Layer | What | Why |
| --- | --- | --- |
| Frontend | **one** `index.html` (~360 KB, vanilla HTML+CSS+JS, zero build, zero node_modules) | opens anywhere, testable with Playwright without a compiler |
| Backend | `server.py`, **Python stdlib only** (`ThreadingHTTPServer`) | no pip, no venv, no supply chain |
| Auth | PBKDF2-HMAC-SHA256 200k, per-user salt, `store.py` | stdlib `hashlib` |
| Data | JSON files under `data/`, no database | inspectable, backupable with tar |
| AI | server-side proxy to DeepSeek (`deepseek-chat`) | key never reaches the browser |

### Request path

```
browser ──HTTPS──> Tailscale Funnel (TLS, public) ──> 127.0.0.1:8088 ──> server.py
                                                          │
                        data/users/<id>/progress.json <────┘ (+ backups/, 20 rotations)
```

The server binds **`127.0.0.1` only** (phase 16). Nothing listens on the LAN interface. If someone
needs LAN access, `Environment=B2_HOST=0.0.0.0` in the systemd drop-in — but the Funnel is the
intended path and nftables (`nft-hardened.service`) is the real outer barrier.

### Storage layout

```
data/
├── users.json                  # index: {id, name, color, created, salt, hash, algo}
├── tokens.json                 # keys are sha256(token); values {user_id, exp, issued, last_seen, ua_hash}
├── audit.log                   # auth events, 0600, rotates at 5 MB
├── events/YYYY-MM-DD.jsonl     # product telemetry, 7-day retention, IP only as truncated hash
└── users/<uid>/
    ├── progress.json           # schema_version 2
    └── backups/                # 20 rotations + pre-migration copies
```

Permissions: directories `0700`, files `0600`. `data/` is gitignored and must never be committed.

### Progress document

`progress.json` carries `schema_version` (current `2`, `store.py:PROGRESS_SCHEMA`). A document
without it is migrated on read, and the original is copied to `backups/pre-migration-<ts>.json`
first. Last write wins between devices; the server rotates the previous version.

Frontend keeps a mirror in `localStorage` under `b2first_tracker_v1_<userId>` (the pre-multiuser
key `b2first_tracker_v1` is still read as a fallback). Session lives in
`localStorage.b2first_user = {id, name, color, token}` and is sent as
`Authorization: Bearer <token>`.

---

## 4. Running it

```bash
sudo systemctl status b2first        # main service (Restart=always)
sudo systemctl restart b2first       # deploy: after any change to server.py/index.html/prompts.py
curl -s http://127.0.0.1:8088/api/health   # {"ok":true,"users":N,"version":"1.0.0","uptime_s":N}
```

Configuration lives in a systemd drop-in, not in the repo:

```
/etc/systemd/system/b2first.service.d/override.conf
  EnvironmentFile=/home/juan/.config/b2first/ai.env
  Environment=B2_DEMO=0
  Environment=B2_REGISTER=open
  Environment=B2_AI_DAILY_PER_USER=8
  Environment=B2_AI_DAILY_TOTAL=80
```

`~/.config/b2first/ai.env` holds `B2_AI_KEY`, `B2_AI_PROVIDER`, `B2_AI_MODEL`. **Never print the
key, never commit the file.** It is a DeepSeek key on the same account as Hermes' old fallback —
see §11 for the billing split.

### Environment variables the code reads

`B2_AI_KEY` · `B2_AI_MODEL` · `B2_AI_PROVIDER` · `B2_AI_BASE` · `B2_AI_DAILY_PER_USER` ·
`B2_AI_DAILY_TOTAL` · `B2_DEMO` · `B2_REGISTER` · `B2_HOST` · `B2_PUBLIC_HEALTH` ·
`B2_SPK_AZURE_KEY` · `B2_SPK_AZURE_REGION` · `B2_SPK_AZURE_ENDPOINT` ·
`B2_SPK_PA_DAILY_PER_USER` ·
`B2_OWNER_PASSWORD` (first-boot bootstrap only) · `B2_TEST_USER` / `B2_TEST_PASS` (tests only).

### Public ingress

Tailscale Funnel: `tailscale funnel status` on the Pi. It maps
`https://vps-server.tail40095b.ts.net` → `http://127.0.0.1:8088`. Funnel only serves `*.ts.net`
names — a custom domain requires Cloudflare Tunnel instead (§12.1).

---

## 5. Testing — 23 suites

Every file is a standalone script; there is no pytest. `tests/helpers.py` registers a throwaway
`test-runner` account (override with `B2_TEST_USER` / `B2_TEST_PASS`) and logs in through the API,
so no suite depends on a human password. That was a real bug once: the helper used to hardcode the
owner's password, and rotating it turned the suite red.

```bash
cd tests
uv run --with playwright python test_final.py     # main UI suite (needs the live service)
python3 test_hardening.py                          # needs the live service
```

| Needs the live service on :8088 | Spins up its own server + temp `data/` (safe anywhere) |
| --- | --- |
| `test_final` `test_mobile` `test_tracker` `test_personalization` `test_plan` `test_streak` `test_schedule_advance` `test_rot` `test_exam` | `test_sync` `test_graf` `test_demo` `test_register` `test_multiuser` `test_ai` `test_ai_guard` `test_onboard` `test_diag` `test_hardening` `test_legacy_guard` `test_security2` `test_server_hardening` `test_telemetry` |

Counts at handoff: `test_hardening` 16 · `test_security2` 14 · `test_server_hardening` 16 ·
`test_ai_guard` 15 · `test_telemetry` 14 · `test_multiuser` 18 · `test_onboard` 15 ·
`test_plan` 8 · `test_legacy_guard` 9.

### Two hard rules for tests

- Suites that spin their own server change `server.DATA_DIR` and `PORT` **before** starting it.
  Never let them touch the real `data/` (one of them did once, and the owner's progress had to be
  restored from a backup).
- Audio/video UI is testable with Playwright's fake devices:
  `--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<wav>`. Use this for the
  speaking feature instead of "test it by hand".

---

## 6. The delegation loop (how the last 13 phases were built)

`delegacion/run-fase.sh <N> cc` runs one phase: it snapshots, launches an agent CLI with
`delegacion/prompt-fase<N>.md`, runs the gate tests, and emits a verdict line.

```
== fase 17 | harness cc | branch feat/ia-hackathon | base 3defe23d
== baseline: node --check=0 | GET / =200 | arbol_sucio=0
== lanzando cc (deepseek/deepseek-v4.1-flash)
== fin: EXIT=0 commits=1 head=247743e dirty=0 js=0 svc=200 quota=0 noauth=0
== VERDICT: ok
```

- `VERDICT: ok` requires: exit 0, a commit, clean tree, JS syntax valid, service 200, gate tests green.
- `VERDICT: tests_rojo` means it committed but a gate test failed — **inspect before trusting**. That
  happened on phase 11, and the cause was the test hardcoding the owner password, not the phase.
- Model is `CC_MODEL`, default `deepseek/deepseek-v4.1-flash`. Override per run:
  `CC_MODEL=other/model bash delegacion/run-fase.sh 18 cc`.
- `delegacion/queue.json` holds the phase queue; `b2f_loop.py` (cron, every 10 min) picks the next
  pending one. Mark a phase `done` by hand if you accept it despite a red verdict, or the loop
  will retry it forever.
- **`command-code` writes no log until it finishes.** A phase takes 10–40 minutes and looks dead the
  whole time. Never kill it because the log is empty — that mistake was made once.

---

## 7. Security model (phases 11, 12, 16, 17)

Run `bash tools/audit.sh` — 14 checks against the public URL, exits non-zero on failure. At
handoff: **14/14 PASS**.

| Control | Where |
| --- | --- |
| Path/user-id sanitisation, no traversal | phase 11 (`user=../../etc/passwd` → 400) |
| Write locks + atomic `os.replace` (the "transaction" equivalent, no DB) | phase 11 |
| Headers: CSP, nosniff, DENY, referrer, permissions, HSTS, COOP, CORP | phases 11 + 16 |
| CORS closed explicitly (not by omission) | phase 11 |
| `X-Request-Id` on every response, logs never contain tokens | phase 11 |
| `/api/health` | phase 11 |
| Schema version + migration with a pre-migration backup | phase 11 |
| Password reset by CLI: `tools/reset_password.py` | phase 11 |
| Brute-force lockout: 5 failures → username locked 15 min | phase 12 |
| Tokens stored as `sha256(token)`, never plaintext | phase 12 (+ a one-off migration of 78 legacy tokens) |
| Payload schema caps: 5000 items, 500 chars, depth 6 | phase 12 |
| Auth audit log + per-user "recent activity" | phase 12 |
| Global 300 req/min/IP | phase 12 |
| Socket timeout 15 s (slowloris), 200-connection semaphore → 503 | phase 16 |
| URI > 2048 → 414 · >60 headers → 431 · `Content-Length` > 3 MB → 413 before reading | phase 16 |
| `TRACE` → 405 · `..` in any encoding → 400 · `.env`/`.git`/`.es_salt` → 403 | phase 16 |
| No version banner (`Server: B2First`, `sys_version=""`) | found by `tools/audit.sh` |
| AI: instruction hierarchy, per-request nonce fence, injection/off-topic heuristics, output leak guard | phase 17 |

**The one that mattered:** before phase 11, `PUT /api/progress` accepted requests with **no token**
for `user_id="owner"` (a LAN convenience). Through the Funnel, that meant anyone on the internet
could `GET /api/progress?download=1` and read everything, or overwrite it. Fixed by rejecting the
tokenless path whenever `X-Forwarded-For` / `X-Real-IP` is present, with `test_legacy_guard.py`
(9 asserts) as the regression test.

### Limits currently enforced (server-side)

Register 5/h/IP · login 10/10min/IP + 20/h/username, 5 failures → 15 min lock · progress 2 MB and
60 writes/min · AI 10/min + 60/h/IP, 8/day/user, 80/day/instance · telemetry 60 batches/h/IP.

---

## 8. Telemetry and privacy (phase 15)

- Client `track(event, props)` batches every 10 s or 20 events via `sendBeacon` → `POST /api/events`.
- **Closed allowlist of event names and scalar props.** No free text, no email, no token, no content.
- IP is stored only as `sha256(ip + salt)[:16]` (salt in `data/.events_salt`, `0600`).
- 7-day retention, pruned on write. `GET /api/metrics` is owner-only and returns aggregates.
- **Do Not Track is honoured**: with DNT on, the client sends nothing at all (asserted in
  `test_telemetry.py`).
- `GET /privacy` serves the policy; it is linked from the footer and from registration. Sections
  cover what is stored, what is not, retention, user rights (export/delete), what the AI receives,
  and Ley 25.326. A placeholder `TODO_OWNER_EMAIL` is documented in the README rather than invented.

---

## 9. AI layer (phase 17)

Endpoint `POST /api/ai/writing`. Request: `{task: essay|article|report|review|email, text}`.
Response: four Cambridge bands 0–5 (Content, Communicative Achievement, Organisation, Language)
with quoted evidence, two weaknesses per criterion and three rewritten sentences.

Guards, all live and tested against the real model:

- 40–700 words, ≤ 4000 chars, control chars stripped, binary rejected.
- The student text is wrapped in `<<<TEXT_<nonce>>>` … `<<<END_<nonce>>>` with a **fresh nonce per
  request**; if the text contains the delimiter it is neutralised.
- The system prompt states an explicit hierarchy: only the system message carries instructions,
  everything inside the fence is data to grade, and injection attempts are themselves evidence of a
  weak off-task answer.
- Heuristics block (`422 {"error":"off_topic","reason":"prompt_injection"|"code"|...}`) **before**
  the model call. Deliberately tuned to prefer false negatives over blocking a real essay.
- Output guards: refuses `{refuse:true}` accepted; system-prompt leakage → `502 unsafe output`;
  > 8 KB rejected.
- Never logs the student text. `audit.log` records `ai_blocked` with `rid`, reason and char count.

Verified live: injection → 422 in 0 ms of model time; code → 422; a real 160-word essay → 200 in
5.2 s with bands `3/3/3/3`.

**Cost:** the app uses `B2_AI_KEY` (DeepSeek). Quotas exist because that key belongs to Juan.
At handoff, 8/day/user and 80/day/instance were still the configured values; the recommendation on
the table is to drop the instance cap to 20 (§12.3).

---

## 10. Operations

### Backups (verified, not aspirational)

- `~/.hermes/scripts/b2f_backup.sh` — tars `data/`, **extracts and JSON-parses every file** to prove
  the archive is restorable, keeps 14 copies in `~/b2first-backups/`, logs to `backup.log`, stays
  silent unless something fails.
- systemd timer `b2f-backup.timer` at **03:30** daily, `Persistent=true` (runs on boot if missed).
- Weekly off-device copy to Telegram: cron job, Sundays 21:00.
- **Restore procedure** (used once for real): pick the `.tgz`, `tar xzf` into a temp dir, verify the
  JSON parses, stop the service, copy `users/` and `users.json` back, `chown juan:juan`, restart,
  check `/api/health` and log in. Never restore over a live service.

### Watchdog

`~/.hermes/scripts/b2f_health.py`, cron every 15 min, `no_agent`, **silent unless broken**: service
inactive, `/api/health` not ok, free disk < 500 MB, or newest backup older than 48 h. It tolerates a
404 from `/api/health` (pre-phase-11 servers) rather than crying wolf.

### Other cron jobs

| When | What |
| --- | --- |
| every 10 min | `b2f_loop.py` — advances the delegation queue |
| every 15 min | watchdog (above), silent on success |
| 03:30 daily | verified backup (systemd timer, not cron) |
| 07:40 daily | morning summary to Telegram |
| Sun 21:00 | weekly backup to Telegram |

---

## 11. The agent environment (Hermes) — read this before changing keys

Three separate billing paths existed, and they were confused. The truth at handoff:

| Channel | Endpoint | Key location | Who pays |
| --- | --- | --- | --- |
| **Hermes (this agent)** | `api.commandcode.ai/provider/v1` | `~/.hermes/config.yaml` → `providers.commandcode.api_key` | **Command Code** plan |
| **Delegated phases** (`run-fase.sh`) | same gateway, through the `command-code` CLI | `~/.commandcode/auth.json` | Command Code plan |
| **The product's AI** | `api.deepseek.com` | `~/.config/b2first/ai.env` → `B2_AI_KEY` | DeepSeek balance (shared account) |

What was wrong and what was done on 2026-10-30:

- The `user_...` key in `~/.hermes/config.yaml` was **invalid (401)**. Hermes silently fell back to
  the `deepseek` fallback provider, so the agent had been running on Juan's DeepSeek credit without
  anyone noticing.
- Fixed by replacing the three `user_...` keys with the working key from `~/.commandcode/auth.json`
  (validated: `HTTP 200` against the gateway) and **removing `deepseek` from `fallback_providers`**
  so the DeepSeek balance is reserved for the product alone. Remaining fallbacks: `copilot`,
  `openrouter`.
- YAML validated with `uv run --with pyyaml`. Backups: `~/.hermes/config.yaml.bak-*`.
- **A config change only applies to a new Hermes session.** The session that made the change kept
  running on the fallback.

If Hermes ever looks like it is burning DeepSeek credit again, check in this order:
`grep -A4 '^model:' ~/.hermes/config.yaml` → is `provider: commandcode`? → is the key the one from
`auth.json`? → does a one-line completion against the gateway return 200? → is `deepseek` back in
`fallback_providers`?

**Never paste any of these keys into a commit, a doc, a chat message or a test fixture.**

---

## 12. Open work, in priority order

### 12.1 Domain (blocked on Juan)

`firsttracker.app` verified free (no DNS). Name.com student offer: **$0 year 1, US$26.99/yr renewal**
(from Juan's own checkout screenshot). He has not registered it. When he does:

1. Create a free Cloudflare account, add `firsttracker.app`, copy the two nameservers into Name.com.
2. `cloudflared` **is already installed** on the Pi (`/usr/local/bin/cloudflared`, 2026.8.2).
3. `cloudflared tunnel login` (interactive, needs a browser — Juan must do it or hand over the cert).
4. `cloudflared tunnel create firsttracker` → `config.yml` with ingress
   `firsttracker.app → http://127.0.0.1:8088`, then `cloudflared service install`.
5. Keep the Funnel running as a fallback; verify with `tools/audit.sh` after the switch.

Rejected alternatives and why: `.me` (personal, not product), `.tech` (expensive renewal),
`.dev` (developer connotation), `band`-based names (that is IELTS vocabulary, verified via Google
autocomplete across `es-AR`, `es-ES`, `pt-BR`, `tr`, `en-GB` — "b2 first band" returns nothing).

### 12.2 Speaking evaluator (planned, not started)

Full plan in `docs/SPEAKING-EVALUATOR.md`. **Its staging (§4) is superseded by
`docs/SPEAKING-REALTIME-PLAN.md`** (2026-10-30): live examiner + live partner, phoneme-level
pronunciation via Azure PA, silences via client VAD, two simultaneous voices via two Live
sessions plus a client-side turn director.

**S1 (voice -> VAD -> HUD) shipped in phase 18, see docs/SPEAKING-REALTIME-PLAN.md.**
That first slice is fully client-side (no keys, no network); the rest is still plan only, blocked
on two new keys (Gemini + Azure) and the minute caps. Summary: 3 of the 4 Cambridge speaking scales are
automatable (Grammar & Vocabulary and Discourse Management from the transcript; Pronunciation only
with a phoneme-level API — Azure Speech Pronunciation Assessment supports `en-US` with prosody
scores). **Interactive Communication is not** — Part 3 is a collaborative task and needs a second
human. Recommended staging: S1 record-and-grade (fits the stdlib stack), S2 live metrics (wpm,
fillers, silence), S3 turn-based partner, full duplex last and behind a flag.

### 12.3 Decisions waiting on Juan

- **AI instance cap:** `B2_AI_DAILY_TOTAL=80` → 20. With a shared DeepSeek balance this is the
  single change that protects the product's budget.
- **Domain:** see 12.1.
- **Video + Devpost submit:** `docs/VIDEO-SCRIPT.md` (6 shots, 90–110 s) and
  `docs/DEVPOST-FIELDS.md` are ready. The video needs his voice; the submit needs his account and
  his age declaration. **Neither has been done.**

### 12.4 Known gaps, honestly

- **No load test has ever been run.** Capacity numbers in the README/chat are reasoned, not measured:
  ~10 concurrent users, 50–100 registered, with the 89 KB gzipped page load as the real ceiling.
  If someone claims a number, ask for the test.
- Windows `/privacy` has a `TODO_OWNER_EMAIL` placeholder on purpose (no invented contact).
- `GET /api/metrics` returns `users_active` but the value counts **sessions** (`sid`). Cosmetic, and
  the UI labels it "active sessions"; the JSON key is just misnamed.
- No password recovery by email (no mail server). `tools/reset_password.py` is the path.
- No admin UI: registration/quota changes are env + restart.
- The morning-summary and watchdog crons depend on Hermes being alive on this box.

---

## 13. Pitfalls that will bite the next person

1. **`X-Forwarded-For` decides auth.** Any proxy in front means the tokenless legacy path must 401.
   Do not "simplify" that guard.
2. **`command-code` logs nothing until it exits.** 10–40 min of silence is normal.
3. **Tests that boot their own server must set `DATA_DIR` before import**, or they will overwrite
   real user data.
4. **`node --check` on the extracted JS** before any deploy:
   `python3 -c "import re;open('/tmp/a.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/a.js`
5. **`index.html` is one file** — a merge conflict there is a lost afternoon. Commit small.
6. **The RDAP of `.app` lies**: it returns 404 for registered domains (parked ones). Confirm
   availability by DNS *and* RDAP, and trust the registrar's checkout.
7. **DeepSeek balance is shared** between the product and (formerly) this agent. Check
   `https://api.deepseek.com/user/balance` before blaming quotas.
8. **`data/tokens.json` keys are hashes now.** Do not "helpfully" re-add plaintext for debugging.
9. **Playwright suites need `uv run --with playwright`**, plain `python3` will fail on import.
10. **`systemctl restart b2first` is safe; `systemctl restart nft-hardened` is not** — it can lock
    you out of SSH. Ask first.

---

## 14. Recovery runbook

| Symptom | Do this |
| --- | --- |
| `/api/health` fails | `systemctl status b2first`, `journalctl -u b2first -n 50 --no-pager` |
| App loads but login fails | check `data/users.json` parses; check the account is not locked (5 fails → 15 min) |
| Someone locked out | `python3 tools/reset_password.py <name>` on the Pi |
| Progress looks wrong | restore from `data/users/<uid>/backups/` (20 rotations) — never hand-edit JSON |
| Disk full | `du -sh ~/b2first-backups`, prune old `.tgz`, check `data/events/` retention |
| Tunnel down | `tailscale funnel status`; re-run `tailscale funnel --https=443 http://127.0.0.1:8088` |
| Suspected compromise | `grep -i fail data/audit.log`, rotate every token (delete `tokens.json`), reset passwords |
| Need the pre-phase-11 state | `git log --oneline` around `6efb512` (the proxy guard fix); the owner's data was restored from `data/users/owner/backups/progress-20261029-224957.json` |

---

## 15. File map

```
~/b2first-tracker/
├── server.py            ~2500 lines: routing, auth, quotas, hardening, AI proxy, telemetry
├── store.py             storage seam: users, tokens (hashed), passwords, progress, migrations
├── prompts.py           the examiner system prompt + the fenced message builder
├── index.html           the whole frontend (tokens, 10 views, intake wizard, charts)
├── tests/               23 suites (see §5) + helpers.py
├── tools/
│   ├── audit.sh         14 external security checks against the public URL
│   └── reset_password.py
├── delegacion/
│   ├── run-fase.sh      the phase runner (tests as gate)
│   ├── queue.json       phase queue (0–17 done)
│   ├── prompt-fase*.md  one prompt per phase (15 = telemetry+privacy, 16 = network, 17 = AI)
│   └── README.md        how the loop works
├── docs/
│   ├── PRIVACY.md · SECURITY.md · SPEAKING-EVALUATOR.md
│   ├── VIDEO-SCRIPT.md · DEVPOST-FIELDS.md
│   └── screenshots/
├── README.md            problem, audience, features, calibration, stack, security
├── SUBMISSION.md        the Devpost narrative
├── SECURITY.md          threat model + control map + what is out of scope
└── agents.md            the working guide for anyone touching the code

~/.config/b2first/ai.env          B2_AI_KEY (never print)
~/.hermes/config.yaml             Hermes provider = commandcode (see §11)
~/.commandcode/auth.json          command-code CLI key
~/.hermes/scripts/b2f_backup.sh   verified backup
~/.hermes/scripts/b2f_health.py   watchdog
~/b2first-backups/*.tgz           local backups
/etc/systemd/system/b2first.service.d/override.conf   runtime config
```

---

## 16. If you only have five minutes

1. `curl -s http://127.0.0.1:8088/api/health` → must be `{"ok":true,...}`.
2. `cd ~/b2first-tracker && git status` → must be clean on `feat/ia-hackathon`.
3. `bash tools/audit.sh` → must print `14/14 checks passed`.
4. `python3 tests/test_legacy_guard.py` → must be `9/9 OK` (this is the guard that once leaked
   every user's data).
5. Then read §12 and pick up the highest-priority item that is not blocked on Juan.
