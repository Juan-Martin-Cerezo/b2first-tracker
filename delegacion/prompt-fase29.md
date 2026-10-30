# Phase 29 — English by default, Spanish available in-app

## Goal
The product is in English. The owner wants **English as the default for
everything**, with a language switcher inside the app that turns the UI into
Spanish and back, persisted per account.

Owner instruction (verbatim): "Idioma default de todo es ingles, dentro de la app
que se pueda cambiar a Español."

## Hard rules
- `index.html` is one 6.5k-line file, edited by one agent at a time. Work in
  small, committed steps; never leave the file half-migrated.
- No dependencies, no build step, no i18n library.
- **Every new string lives in the dictionary.** No Spanish literal left in the
  HTML templates. Code, comments, commits, CSS class names: English.
- Do not translate the 30 book titles, exam part names (Part 1…7) or the
  material file names: they are proper nouns.

## Design
```js
const I18N = {
  en: { nav_today: "Today", nav_plan: "Plan", /* … */ },
  es: { nav_today: "Hoy",  nav_plan: "Plan", /* … */ },
};
let LANG = 'en';
function t(key, vars) { /* lookup + {x} interpolation + fallback to en */ }
function setLang(code) { LANG = code; D.settings.lang = code; applyI18n(); refreshAll(); }
function applyI18n() { /* data-i18n attributes + document.title + <html lang> */ }
```
- `D.settings.lang` defaults to `'en'`; `SETTINGS_DEFAULT` must carry it so old
  saved documents get it on load.
- `<html lang>` must follow the current language (`en` / `es`).
- Switcher: a two-state control in the PLAN tab (where other settings live),
  labelled with the language's own name ("English" / "Español"), plus
  `aria-pressed`. It must survive a reload.
- Numbers, dates and sizes keep `en-GB` formatting in English mode and
  `es-AR` in Spanish mode (the exam is British English; the owner is Argentine).

## Steps
1. Extract strings in **one screen at a time** (nav → auth → today → plan →
   log → stats → errors → books/material → speaking → exam → modals/toasts).
   Commit per screen so a failure is recoverable.
2. Wire `data-i18n` where the markup is static; call `t()` where JS builds DOM.
3. Add the switcher and the persistence.
4. Toasts and `confirm()` texts go through `t()` too — they are user-facing.

## Acceptance (write `tests/test_i18n.py`)
Playwright, `tests/helpers.py`, on a fresh throwaway account:
- Fresh account: `<html lang="en">`, nav shows "Today", `D.settings.lang === 'en'`.
- Click the switcher → `<html lang="es">`, nav shows "Hoy", a screenshot-free
  assertion that **no** English-only label remains in the nav (`Today` gone).
- Reload → still Spanish (persisted).
- Switch back → English.
- **No missing keys**: loop over every `data-i18n` element and assert
  `t(key)` is non-empty in both languages. Also assert `Object.keys(I18N.en)`
  and `Object.keys(I18N.es)` have the same length (catches forgotten strings).
- Zero JS errors in the console for the whole run.

## Verify before finishing
```
cd tests && uv run --with playwright python test_i18n.py     # exit 0
cd tests && uv run --with playwright python test_final.py    # must stay green
cd tests && uv run --with playwright python test_no_synced.py # must stay green
```
Finish with `VERDICT: ok` only if all three pass. If a screen is too entangled
to migrate safely, leave it in English, add it to a `TODO(i18n)` list at the top
of the script, and say so in the verdict — a half-translated screen that breaks
is worse than an English one that works.
