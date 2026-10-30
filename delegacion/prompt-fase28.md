# Phase 28 — Remove the "synced" text from the UI

## Goal
The footer shows a sync badge whose text ("Synced", "Saved", "Offline") adds
noise and reads as developer jargon. Keep the *state* visible, drop the *word*.

Owner instruction (verbatim): "Saca el texto que dice synced."

## Hard rules
- `index.html` is a single 6.5k-line file and other phases are queued behind
  this one: touch only the sync badge and its render function.
- No new dependencies. No framework. Vanilla JS only.
- Code, comments and commits in English.

## Steps
1. Find the badge (`syncBadge`, `syncState`, or the element that renders
   "Synced"/"Saved"/"Offline"). Read the render function before editing.
2. Replace the visible text with a **dot + state conveyed by colour and
   `title`/`aria-label`**: green = synced, grey = saving, amber = offline.
   The badge must stay focusable (`tabindex="0"`) so a screen reader gets the
   `aria-label` ("Progress saved to the server", "Saving…", "Offline — changes
   stay on this device").
3. Remove any other place that prints the literal word "synced"/"Synced"
   (toasts, titles, comments in user-facing strings). Server logs and code
   comments are fine.
4. Keep the same DOM id so tests that poke it keep working; if you must change
   it, update the tests in the same commit.

## Acceptance (write `tests/test_no_synced.py`)
Standalone Playwright script, same style as `tests/test_final.py`
(`uv run --with playwright python test_no_synced.py`), logging in with
`tests/helpers.py`:
- After login and a save, `page.content()` does **not** contain the substring
  `synced` or `Synced` (case-insensitive) in visible text.
- The badge exists, has a non-empty `aria-label`, and `title`.
- Trigger a save and assert the badge's colour class changes at least once
  (proves the state is still conveyed).
- `page.evaluate("document.querySelectorAll('[id*=sync]').length") >= 1`.

## Verify before finishing
```
cd tests && uv run --with playwright python test_no_synced.py   # exit 0
cd tests && uv run --with playwright python test_final.py       # must stay green
```
The runner restarts the service for you; do not restart it yourself.
Finish with `VERDICT: ok` only if both suites pass.
