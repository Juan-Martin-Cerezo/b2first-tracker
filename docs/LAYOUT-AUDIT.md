# Layout audit — Phase 27

Owner report: *"Muchas pantallas estan mal armadas o las cuadrillas no bien
posicionadas."* This file records what was measured, what was broken, and what
changed. A row is `PASS` only when the fix is verified by
`tests/test_layout.py`.

## Method

Playwright, Chromium, three viewports per view:

| Viewport | Size | Input |
| --- | --- | --- |
| phone | 360 × 740 | touch + mobile UA |
| tablet | 768 × 1024 | touch + mobile UA |
| desktop | 1440 × 900 | mouse |

Views: `today`, `plan`, `log`, `stats`, `errors`, `books`, `material`,
`speaking`, `exam`, `diagnostic`, `onboarding`, `auth` — each one in English
and Spanish (except the two overlays, which have no language context: the auth
card is shown before a document exists and the intake copy is English by
design). Every run checks:

1. `document.documentElement.scrollWidth <= innerWidth + 1`;
2. pairwise overlap of `.card` / `.tile` / `.stat` / `.stat-card` siblings
   inside the same grid or flex container (1 px tolerance);
3. every `button` at least 40 × 40 px;
4. no visible element painted past `innerWidth` (content inside a table's own
   horizontal scroller is clipped by that scroller, so it is not counted as
   painted outside);
5. zero console / page errors.

The full matrix is automated in [`tests/test_layout.py`](../tests/test_layout.py)
(69 snapshots: 3 viewports × (10 views × 2 languages + onboarding + step 3 +
auth)).

## Summary before → after

Counts are "issues reported by the five checks" (all five zero after the
changes).

| Viewport | Before (small targets / overlap / beyond / scroll) | After |
| --- | --- | --- |
| phone 360 | ~855 small targets; 0 overlap; 0 beyond; 0 scroll | 0 / 0 / 0 / 0 |
| tablet 768 | ~856 small targets; 0 overlap; 0 beyond; 0 scroll | 0 / 0 / 0 / 0 |
| desktop 1440 | ~1274 small targets; 0 overlap; 0 beyond; 0 scroll | 0 / 0 / 0 / 0 |

The four structural checks were already clean on the first pass. The owner's
complaint was in *composition* details that those four metrics do not encode
(rows with no separator, content escaping its card without crossing the
viewport, a floating delete button, an unbalanced card grid). Those were found
by visual inspection of every view at the three viewports and are listed
below alongside the mechanical findings.

## Issues

`before` → `after` values are the measured rectangles or the observed state.

| View | Viewport | What | Fix | Status |
| --- | --- | --- | --- | --- |
| material / books | all | 400 `✓` / `↺` row controls measured 36 × 40–44 px | `.chip-ctl` with `min-width:40px`, centred | PASS |
| plan, today, errors, diagnostic, speaking, log, stats, exam, books, material | desktop | every `.btn.sm` was 32 px tall (44 px on touch only) | `.btn.sm{min-height:40px;min-width:40px}` | PASS |
| plan | phone | `English` / `Español` switch buttons were 35 px tall | `.lang-btn{min-height:40px;min-width:44px}` | PASS |
| onboarding (step 3) | all | 5 skill-rating buttons were 36 × 36 px (22–32 per viewport) | `.ob-rate-btn{40 × 40}` + wrappable rate rows | PASS |
| onboarding (step 3) | tablet, desktop | "Take the 10-minute diagnostic instead" button was 24 px tall | `.ob-link{min-height:40px}` as inline-flex | PASS |
| today, log, stats, plan, errors, exam, speaking | all touch / desktop | selects were 22–38 px tall (`#ovW` 22, `#spkPart` 33, `#exPaper`/`#errCode2` 38, schedule selects) | global `min-height:40px` on form controls | PASS |
| today (topbar) | all | user-switch `⇄` button was 34 px wide | covered by `.btn.sm` `min-width:40px` | PASS |
| today (recent sessions) | phone | label and score ran together: `29/10/20266/8` | `.metric-row` is a global flex row with `gap:12px`; score stays right | PASS |
| errors | phone | delete `✕` floated to the bottom-right corner of each card | `.err-head` flex header: code + date + delete (delete at the end) | PASS |
| errors | all | cards nested with a floated control outside the header rhythm | header uses gap, no `float`, no margins as gutters | PASS |
| material | phone, desktop | `Open PDF` was blue text on the blue button (contrast ≈1.1:1) | `.book a.btn{color:var(--on-primary)}`, gray variant keeps `--txt` | PASS |
| material | phone | 5-line file names squeezed into ~130 px; controls took half the row | material rows wrap at ≤520 px: title takes the row, controls move to a right-aligned footer row | PASS |
| books / material | phone | long book titles / file names had no shrink floor | `min-width:0` on row children + `overflow-wrap:anywhere` on titles | PASS |
| prog, graf | phone, desktop | `material-symbols-outlined` wasn't loaded: its ligature text (`monitory`, `military_`, `hourglass_`) rendered clipped in the stat cards | replaced with the existing inline SVG icon set (`.stat-ico`) | PASS |
| prog | all | "Global Average" showed `NaN%` when the log contained a Speaking-final entry without `correct/total` | `pctOf()` returns `null` for non-finite values | PASS |
| exam | tablet, desktop | four cards fell into a 3 + 1 row (auto-fit 280 px) | explicit 2 columns, 1 at ≤560 px — balanced 2 × 2 at tablet and desktop | PASS |
| diagnostic | phone | 3-column results table was clipped: `CORRECT/T…`, the bar column hidden behind sideways scroll | removed the 440 px floor for this table, compact cells, bar column at 34 %; the table now fits 360 px | PASS |
| log / stats | phone | both tables were 440 px inside a 288 px card (152 px of hidden columns) | 12 px labels, 4 px cells at ≤520 px; stats fits exactly, log shrinks to ~317 px (≈29 px scroll for its two 40 px action buttons) | PASS |
| today (session header) | phone | wrapped "STUDIO TIME / 60 MIN" block sat left of the card with `text-align:right` doing nothing | becomes an inline label + value under the description | PASS |
| today (writing studio) | phone | 3-step phase grid laid out 2 + 1, leaving an orphan half-width card | one column at ≤520 px, full-width steps | PASS |
| today (rotations) | phone | writing queue, session tabs and gates tabs scrolled sideways inside cards | all wrap (`flex-wrap:wrap`, `overflow:visible`) | PASS |
| books | phone | category chips were forced onto one nowrap scroller | categories wrap; every chip is visible | PASS |
| today (topbar) | phone | brand wrapped to two lines; the stage badge clipped at 110 px | brand `white-space:nowrap`; badge hidden ≤480 px; no artificial max width on desktop | PASS |
| today (next session) | phone, desktop | title, schedule and actions were three independent flex columns; actions stacked vertically | copy wrapped in `.next-copy`, actions in `.next-actions` (two columns, stacked on mobile) | PASS |
| today (diagnostic banner) | phone | the `Start` button stretched to the full height of the banner | banner aligns to the centre; ≤520 px stacks with a full-width button | PASS |
| today | phone, desktop | "Start session" jumped to a section hidden under the sticky header | `html{scroll-padding-top:140px}` (76 px on mobile) | PASS |
| all | all | horizontal page scroll / card overlap | none found before or after: 0 in 69 snapshots | PASS |
| all | all | console errors | none before or after: 0 | PASS |

## Residual behaviour (intentional)

- **Log table at 360 px** keeps ~29 px of its own horizontal scroll inside
  `.table-wrap`: six columns include two 40 px tap targets, so it cannot shrink
  below the card width without breaking the 40 px floor. Every other table
  (`stats`, diagnostic) fits at 360 px. This is the only horizontal scroller
  left.
- **The quick-log FAB is `position:fixed`** above the bottom nav. It floats over
  page content while scrolling — it is not a grid sibling and cannot overlap a
  card's box in flow. Its position is unchanged in this phase.
- **The topbar sync dot** now sits next to the account controls instead of
  floating at the centre of the bar.

## Verification

```
cd tests
uv run --with playwright python test_layout.py    # 69 snapshots, VERDICT: ok
uv run --with playwright python test_final.py     # green
uv run --with playwright python test_i18n.py      # green (English + Spanish)
```

`test_layout.py` prints the per-snapshot table and a `TOTAL` line with the
counts (`scroll_ok=69/69 overlap=0 small=0 beyond=0`).
