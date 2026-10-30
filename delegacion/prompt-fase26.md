# Phase 26 — More practice sources, reachable in one tap

## Goal
The app tracks practice but does not *offer* places to practise. Add a curated
catalogue of legal, free practice sources and put it where the owner actually
looks: a "Practice" entry in the main navigation plus, on the Today screen, one
tap from the daily suggestion to the source that trains today's weakest part.

Owner instruction (verbatim): "Añadí mas fuentes o lugares para practicar y
dejalos más a mano del usuario."

## Hard rules (non-negotiable, they come from AGENTS.md)
1. **No piracy.** Only official Cambridge/free-legit material. Never link to
   pirated PDFs, "free download" sites, Scribd copies or Torrents. If a source
   is behind a paywall, label it **Paid** and say why it is worth it — do not
   hunt for a "free" mirror.
2. **No made-up data.** Every entry: verify the URL resolves (HTTP 200/30x) when
   you add it. If you cannot verify one, leave it out and say so.
3. No dependencies. Data lives in a `PRACTICE_SOURCES` array in `index.html`,
   one object per source, no fetch at runtime.

## Data shape
```js
{n:"Flo-Joe", url:"https://www.flo-joe.co.uk/", skill:"rue",
 kind:"free",           // free | freemium | paid
 part:["1","2","3"],    // which exam parts it trains, [] = all
 what:"Word formation and key word transformation drills with instant answers.",
 mins:15}
```
`skill` uses the existing codes: `rue`, `w`, `l`, `sp`.
Include **at least 18** sources spread across the four skills, and mark clearly
which are free. Cover, at minimum:
- Cambridge official free samples and the Cambridge Write&Improve tool;
- BBC Learning English and British Council LearnEnglish (listening/reading);
- Flo-Joe (Use of English), Exam English (full mock sections);
- Youglish and LyricsTraining-style listening-in-context (verify legality);
- Write & Improve (writing feedback), r/writing feedback communities only if
  real and moderated;
- Speaking partners/tandems (e.g. free conversation exchange sites) — verify.

## UI
1. New nav item **Practice** (`data-i18n="nav_practice"`).
2. Screen: filter chips by skill (All / Reading & UoE / Writing / Listening /
   Speaking) and a free-only toggle; cards use the phase-27 grid rules; each
   card shows name, skill badge, what it trains, minutes, and a real
   `<a href target="_blank" rel="noopener noreferrer">Open</a>`.
3. **Today screen**: under the daily suggestion, a "Practise this now" row with
   up to 3 sources matching the weakest part from `D.diag` (fall back to the
   rotation's skill when there is no diagnostic). One tap opens the source.
4. Empty state: if a filter has no matches, say so — never a blank screen.

## Acceptance (write `tests/test_sources.py`)
Playwright, `tests/helpers.py`:
- The Practice item is in the nav and opens the screen in one click.
- `PRACTICE_SOURCES.length >= 18`.
- Every entry has `n`, `url` starting with `https://`, `skill` in
  `['rue','w','l','sp']`, `kind` in `['free','freemium','paid']`, `what` > 20 chars.
- Filter chips actually filter (count changes and the sum adds up).
- Free-only toggle hides every `kind !== 'free'`.
- Each card's `<a>` has `rel="noopener noreferrer"` and `target="_blank"`.
- On the Today screen the "Practise this now" row renders 1–3 links.
- Zero console errors.
- **Link liveness is checked in a separate, non-blocking step**: write
  `tools/check_sources.py` (stdlib, `urllib`, HEAD with a 5s timeout and a
  browser-ish User-Agent) and run it **once by hand**; paste the count of
  reachable sources into the verdict. Do not make the Playwright suite depend on
  the internet.

## Verify before finishing
```
cd tests && uv run --with playwright python test_sources.py   # exit 0
cd tests && uv run --with playwright python test_final.py     # must stay green
python3 tools/check_sources.py                                # report, not a gate
```
Finish with `VERDICT: ok` only if both Playwright suites pass, and include the
liveness numbers ("17/18 reachable, X returned 403 to HEAD") in the verdict.
