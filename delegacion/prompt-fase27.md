# Phase 27 — Fix broken screens and misaligned grids

## Goal
Several screens are badly laid out and the grids (cards, stat tiles, tables,
charts) are not aligned. The owner uses a phone and a PC; both must look
deliberate. Nothing may scroll sideways or overlap at any common width.

Owner instruction (verbatim): "Muchas pantallas estan mal armadas o las cuadrillas
no bien posicionadas."

## Hard rules
- One `index.html`, no framework, no build, no dependencies.
- Use **CSS Grid/Flex with `gap`**, never margins to fake gutters and never
  absolute positioning for layout.
- No visual redesign: keep the colour system (`oklch`, dark mode), the type scale
  and the component shapes. This phase is about alignment, rhythm and breakage.
- Code, comments, commits in English.

## Method — measure first, then fix
1. Start the server, open every view with Playwright at three viewports:
   **360×740** (phone), **768×1024** (tablet), **1440×900** (desktop).
   Views: today, plan, log, stats, errors, books, material, speaking, exam,
   diagnostic, onboarding, auth.
2. For each view record, and write into `docs/LAYOUT-AUDIT.md`:
   - `document.documentElement.scrollWidth > innerWidth` (horizontal scroll) —
     must be `false`;
   - elements whose bounding box crosses the viewport edge;
   - **pairwise overlap** of `.card`, `.tile`, `.stat`, `button`, `table`
     siblings inside the same grid (catches the "cuadrículas" complaint);
   - any interactive element smaller than **40×40 px** (44 is the iOS target;
     40 is the floor);
   - text clipped by `overflow: hidden` without `text-overflow: ellipsis`.
3. Fix in this order, highest count first. Prefer:
   - `display:grid; grid-template-columns: repeat(auto-fit, minmax(<n>px, 1fr));`
     for card collections;
   - `min-width:0` on grid/flex children (the classic cause of overflow with
     long file names and book titles);
   - `overflow-wrap:anywhere` on titles that come from user or file data;
   - `gap` on the container instead of margins on the children;
   - tables wrapped in a container with `overflow-x:auto` **only** when a table
     genuinely cannot shrink.
4. Keep `docs/LAYOUT-AUDIT.md` up to date: one row per issue with
   `view | viewport | what | fix | PASS/FAIL`.

## Acceptance (write `tests/test_layout.py`)
Standalone Playwright (`uv run --with playwright python test_layout.py`),
logging in with `tests/helpers.py`:
- For every view × 3 viewports: `scrollWidth <= innerWidth + 1`.
- No two sibling cards/tiles in the same container have overlapping rectangles
  (allow 1px tolerance).
- Every `button` is at least 40px in both dimensions.
- No element extends beyond `innerWidth`.
- Zero console errors.
- Print a table of the counts so the log shows what was fixed, not just "ok".

## Verify before finishing
```
cd tests && uv run --with playwright python test_layout.py    # exit 0
cd tests && uv run --with playwright python test_final.py     # must stay green
cd tests && uv run --with playwright python test_i18n.py      # checks both languages
```
Test **Spanish too** (`setLang('es')`): Spanish labels are longer and are the
most likely thing to break a tight grid.
Finish with `VERDICT: ok` only if all three pass.
