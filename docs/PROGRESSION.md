# B2 First Tracker — Progression Model Specification

This document is the single source of truth for stage progression, gate evaluation,
manual overrides, stage history, and plan integration (`index.html`, `server.py`).

## 1. Core Concepts

- **Stage (`D.stage`)**: Integer in `{0, 1, 2}`:
  - `0` — **Stage 0: Foundations** (baseline diagnostic + core competence across all papers)
  - `1` — **Stage 1: Precision & Cohesion** (higher accuracy, timed Writing, pacing control)
  - `2` — **Stage 2: Mastery (Release Candidate)** (full exam conditions, consecutive Listening consistency, C1 Speaking validation)
- **Gate**: A deterministic readiness rule belonging to one stage (`0..2`).
  Every gate evaluates to:
  ```js
  {
    id,          // stable string ID, e.g. 's0-diag', 's0-rue', ...
    label,       // human-readable gate title
    requirement, // threshold summary text
    need,        // numeric target required to pass (> 0)
    have,        // numeric progress achieved strictly from data (never altered by overrides)
    pass,        // boolean: (have >= need) || manual
    dataPass,    // boolean: have >= need
    evidence,    // honest provenance string ("Based on N sessions since dd/mm/yyyy ...")
    manual,      // boolean: true when overridden via D.overrides
    manualAt,    // 'YYYY-MM-DD' date of manual override, or null
    pct          // integer 0..100 computed purely from have/need
  }
  ```
- **Pure Evaluation (`calcGates(doc, now)`)**:
  - Deterministic: identical `(doc, now)` inputs always produce identical outputs.
  - Pure: zero side effects, never mutates `doc`, never reads or writes the DOM or `localStorage`.
  - Returns `{ stage, gates, next, stages, diag, errors, sessions, thresholds, readyToAdvance }`,
    where `gates` is the active stage's gate list, `stages` holds `{ stage, label, gates, pass, dataPass, next }`
    for all 3 stages (`0, 1, 2`), and `next` describes the next stage (or `null` at stage 2 when completed).
- **Single Progression Selector (`getProgression(doc, now)`)**:
  - Exported globally (`window.getProgression`) and used by BOTH the Progress view
    (`renderGates()`, `openUserModal()`) and the Weekly Plan (`buildWeeklyPlan()`, `renderWeeklyPlan()`, `renderPracticeNow()`),
    so diagnostic freshness, error summaries, and stage status are never duplicated.

## 2. Input Sanitization & Boundary Rules

1. **Missing / invalid values**: Missing `D.log`, `D.errs`, `D.diag`, `D.overrides`, `D.stageHistory`, or `D.settings` never throw. Non-object rows, `NaN`, `Infinity`, and non-finite scores are ignored.
2. **Zero-total protection**: Any log or diagnostic entry requiring `correct / total` with `!(total > 0)` (including `total: 0` or negative/NaN `total`) is ignored — division by zero is impossible.
3. **Future dates ignored**: Every `date` is parsed to a valid local calendar day `YYYY-MM-DD`. Entries from `D.log`, `D.errs`, or `D.diag` with a missing/invalid date or `date > today` are ignored and do not count.
4. **Stale diagnostic (> 60 days)**:
   - A valid, non-future `D.diag` counts as fresh evidence only when `0 <= ageDays <= 60`.
   - When `ageDays > 60` (e.g. 90 days ago), `diag.fresh === false` and `diag.stale === true`. It does **not** pass `s0-diag` and does **not** drive the diagnostic-based weekly plan; the `evidence` string explicitly reports the age in days and that it exceeded the 60-day limit.

## 3. Thresholds (`D.settings.e0`, `e1`, `e2`) & Gate Definitions

Thresholds come from `D.settings.e0 / e1 / e2` (with `SETTINGS_DEFAULT` fallbacks if omitted or invalid):

- Defaults:
  - `e0`: `{ w: 14, u: 60, l: 3 }`
  - `e1`: `{ w: 16, wm: 45, u: 75, l: 24 }`
  - `e2`: `{ r: 80, rm: 50, w: 16, l: 26, ln: 4 }`

### Stage 0 — Foundations
| Gate ID | Data Source | Threshold & Rule | `have / need` |
| --- | --- | --- | --- |
| `s0-diag` | `D.diag` | Valid diagnostic within `0..60` days (`total > 0`) | `0..1 / 1` |
| `s0-rue` | `D.log` (`ue`, `r6`, `rue`) | All 7 R&UE parts (1–7) with best score `>= e0.u%` (default `60%`) | `0..7 / 7` |
| `s0-l` | `D.log` (`lp`, `l`) | All 4 Listening parts (1–4) `>= 20/30` (`66.7%`) **and** Part 2 errors `<= e0.l` (default `3`; `lp` P2 checks `total - correct <= e0.l`, full `l` checks `p2 <= e0.l`) | `0..4 / 4` |
| `s0-w` | `D.log` (`w`, `fw.s1→Essay`) | All 5 Writing genres (`Essay, Article, Report, Review, Email`) with best score `>= e0.w`/20 (default `14`) | `0..5 / 5` |
| `s0-sp` | `D.log` (`sp`, `sf`) | All 4 Speaking parts (1–4) with best band `>= 3/5` (`sp` full/4-part or `sf` `ok:true` cover 1–4) | `0..4 / 4` |

### Stage 1 — Precision & Cohesion
| Gate ID | Data Source | Threshold & Rule | `have / need` |
| --- | --- | --- | --- |
| `s1-rue` | `D.log` (`ue`, `r6`, `rue`) | All 7 R&UE parts (1–7) with best score `>= e1.u%` (default `75%`) | `0..7 / 7` |
| `s1-l` | `D.log` (`lp`, `l`) | All 4 Listening parts (1–4) `>= e1.l/30` (default `24/30`) | `0..4 / 4` |
| `s1-w` | `D.log` (`w`) | All 5 Writing genres with score `>= e1.w`/20 (default `16`) **and** finite `min <= e1.wm` (default `45` min) | `0..5 / 5` |
| `s1-sp` | `D.log` (`sp`, `sf`) | All 4 Speaking parts (1–4) with best band `>= 4/5` | `0..4 / 4` |
| `s1-err` | `D.log` + `D.errs` | At least `1` valid practice log **and** `<= 2` `T-LIM` errors within the last `30` days | `0..1 / 1` |

### Stage 2 — Mastery (Release Candidate)
| Gate ID | Data Source | Threshold & Rule | `have / need` |
| --- | --- | --- | --- |
| `s2-rue` | `D.log` (`rue`) | At least `1` full R&UE exam with `% >= e2.r` (default `80%`) **and** finite `min <= e2.rm` (default `50` min) | `0..1 / 1` |
| `s2-l` | `D.log` (`l`) | `e2.ln` (default `4`) consecutive chronological full Listening exams (`l`) each at `>= e2.l/30` (default `26/30`) | `0..4 / 4` |
| `s2-w` | `D.log` (`fw`) | At least `1` full Writing exam (`fw`) with `s1 >= e2.w` **and** `s2 >= e2.w` (default `16`) and finite `min <= 80` | `0..1 / 1` |
| `s2-sp` | `D.log` (`sp`, `sf`) | Full 4-part Speaking exam (`sp` with `full:true` or `parts:[1,2,3,4]`) at `>= 4/5` **or** `sf` with `ok:true` | `0..1 / 1` |
| `s2-err` | `D.log` + `D.errs` | At least `1` full mock (`rue`, `fw`, `l`, full `sp`, or `sf` `ok:true`) **and** `0` unfixed `T-LIM` errors within the last `30` days (fixed = non-empty `fix`) | `0..1 / 1` |

## 4. Stage Transitions & Monotonicity (`advanceStageIfReady()`)

- `advanceStageIfReady()` is the **only** function allowed to advance `D.stage`.
- Called automatically after every relevant save (`log`, `qlSave`, `submitIaWriting`, `finishDiag`, `saveEdit`, `saveErr`, `saveErr2`, `setGateOverride`, `importData`) and inside `refreshAll()`.
- **One step per transition**: if `D.stage < 2` and every gate of `calc.stages[D.stage]` has `pass === true`, it sets `D.stage = D.stage + 1` (never skipping two stages in one call), appends `{ stage: newStage, at: new Date().toISOString(), reason }` to `D.stageHistory`, and persists once.
- **Idempotent**: calling `advanceStageIfReady()` repeatedly when no new transition is ready is a no-op and never duplicates `D.stageHistory` entries.
- **Never regresses**: `D.stage` is strictly monotonic (`0 → 1 → 2`). Deleting logs, aging diagnostics past 60 days, or undoing a manual override never decrements `D.stage`.

## 5. Honest Manual Overrides (`D.overrides`)

- Any gate can be marked manually via `setGateOverride(gateId, true)` (or toggled via `toggleGateOverride(gateId)`), storing `D.overrides[gateId] = { manual: true, at: todayStr }`.
- **Visual distinction**: Overridden gates carry `.gate.manual`, display `"Manual override · dd/mm/yyyy"` (or `"Manual override"` if migrated without a date), and offer an `"Undo"` button (`44px` target).
- **Numbers stay honest**: Overrides never alter `have`, `need`, or `pct`; they only set `manual: true` and `pass: true` so the UI reflects the override and `advanceStageIfReady()` can advance when all gates in the active stage pass.
- **Undo**: Clicking Undo removes `D.overrides[gateId]`, reverting `manual` back to `false` and `pass` back to `have >= need` (while already-earned `D.stage` never regresses).

## 6. Legacy Migration

- Documents missing `D.stageHistory` load safely without losing `D.stage`, `D.log`, `D.errs`, `D.diag`, or `D.overrides`:
  - If `D.stage === 0`, `D.stageHistory` is initialized to `[]`.
  - If `D.stage > 0` and `D.stageHistory` is absent, `D.stageHistory` is seeded with pre-existing milestone entries `{ stage: s, at: null, reason: 'Migrated existing stage' }` for `1..D.stage` so the first event has `at: null` and existing progress is preserved.
- Legacy boolean `D.overrides[key] === true` is normalized to `{ manual: true, at: null }`.

## 7. Accessible Mobile & Desktop Matrix

- Each stage renders as its own `<section class="gate-stage-card">` with an `<h3>` heading, stage status badge, and transition timestamp/reason from `D.stageHistory`.
- Inside each stage card, gates use `role="table"` (`rowgroup` / `row` / `columnheader` / `cell`):
  - Desktop (`>= 768px`): 5-column aligned grid (`Gate`, `Progress`, `Evidence`, `Status`, `Action`).
  - Mobile (`<= 767px`): single-column cards (`100%` width, zero horizontal scroll at 360px/320px), with gate name, `have/need`, evidence, status, and ≥ 44×44 px action buttons with visible `:focus-visible` outlines.
- When `D.log` and `D.diag` are empty, the matrix renders a clear CTA banner with actions to start the diagnostic or log a session.
