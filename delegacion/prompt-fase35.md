# Phase 35 — Speaking becomes a real exam simulation

## The complaint
Owner (verbatim): "En cuanto a lo del speaking con IA, no entiendo mucho cómo
funciona y no es fácil de interpretar para el usuario. Tenés que agarrar una task
real de speaking y que la IA haga de examinador."

Diagnosis: today the live studio is a free conversation with a director state
machine. There is **no task on screen, no timer, no instruction, no visible rule**
about who speaks when. A user cannot tell what the exam is, what they must do, or
how they did.

## Goal
Turn it into the Cambridge B2 First Speaking test, part by part, with the task
visible, the clock visible, and the examiner playing a **scripted role**, not a
chat partner.

## Task bank — `material/speaking.json`
Pure data, no code, so it can grow without touching the UI.
```
{"version":1,
 "parts":[
  {"part":1,"minutes":2,"sets":[{"id":"p1-a","questions":["...","..."]}]},
  {"part":2,"minutes":4,"tasks":[{"id":"p2-1","photos":["img/p2-1-a.jpg","img/p2-1-b.jpg"],
     "title":"Two ways of travelling to work",
     "prompts":["Compare the photographs and say why the people might have chosen
                 these ways of travelling.","..."]}]},
  {"part":3,"minutes":4,"tasks":[{"id":"p3-1","topic":"A school trip abroad",
     "prompts":["...5 ideas..."],"decision":"Which two ideas would be best?"}]},
  {"part":4,"minutes":4,"tasks":[{"id":"p4-1","linkedTo":"p3-1","questions":["...6..."]}]}
 ]}
```
Rules for the content:
- Part 1: 8 personal questions, one set, no jargon. Real B2 register ("Where are
  you from?", "What do you enjoy about studying English?").
- Part 2: photo pairs (see `img/spk/`) with the standard two instructions.
- Part 3: a topic card with 5 prompts + the decision question.
- Part 4: 6 discussion questions that clearly follow the Part 3 topic.
- English only in the data; the UI translates the chrome, not the exam.

## Assets already in the repo
`img/spk/` has six CC photos, three pairs, with `CREDITS.md` listing licence and
author — **keep that file and link it from the Part 2 brief** ("Photos: Wikimedia
Commons, CC BY / CC BY-SA — see credits"). Do not add images from Cambridge or any
textbook. If you need more pairs, add them by dropping files and extending
`material/speaking.json`; there is no image generator available in this environment.
Verified pairs: `p2-1-a/b` crowded metro vs cycling to work · `p2-2-a/b` café vs
library · `p2-3-a/b` street market vs shopping from home.

## The flow the user sees (this is the whole point)
Five screens, each with **one** instruction sentence and a progress dot:

1. **Choose** — "Part 1 · 2 min · you and the examiner" with a short plain
   description of each part. One button: Start.
2. **Brief** — what will happen, in 3 bullets, timings, and the single rule:
   "Speak in English. If you go quiet for 5 seconds I will ask you a question."
   Button: I'm ready.
3. **Exam** — the task on screen (photo pair / topic card / question), a big
   countdown for the current phase, and a **speaker indicator**: "Examiner
   speaking" / "Your turn" / "Partner speaking" with distinct colours. The
   transcript streams below (small, grey) so the user can see what was understood.
4. **Feedback** — 4 scales (Grammar & Vocabulary, Discourse Management,
   Pronunciation, Interactive Communication) each 1–5 with one sentence of
   evidence quoting the user, plus **one** thing to work on next time.
5. **Report** — saved to `D.log` as type `sp` with `part`, `min`, `bands`.

## Examiner behaviour (server prompt, not the client)
Rewrite the examiner system prompt so it behaves like a Cambridge examiner:
- Asks exactly the questions in the task, in order, adding at most one natural
  follow-up per answer.
- Never teaches, never corrects, never praises mid-exam. Only: "Thank you.",
  "Now, …", "Can you tell me …?"
- Enforces the clock: at 80% of the phase it asks the closing question; at 100%
  it says "Thank you, that is the end of Part N." and the client advances.
- Silence handling: 5 s of no speech → one prompt; 10 s → moves on. Both are
  logged as `silence_prompts` so the report can mention it.
- The partner (Parts 3–4 only) speaks **once** per examiner turn, maximum two
  sentences, and never answers for the user.

## Client work
1. New `SP_EXAM` module in `index.html`: state machine
   `choose → brief → exam(part) → feedback → report`, reusing `makeLiveTransport`,
   `spkVad` and the existing director for mute/overlap.
2. Photos served from `img/spk/` with `loading="lazy"`, `width`/`height` set (no
   layout shift), and a CSS frame that keeps the pair side by side on desktop and
   stacked on mobile without horizontal scroll.
3. Timers: Part 1 2 min · Part 2 1 min + 30 s response · Part 3 2 min + 1 min
   decision · Part 4 4 min. Visible at all times, colour shifts in the last 15 s.
4. Every chrome string through `I18N` in EN and ES. **Zero hardcoded text** (run
   `tools/scan_texts.py` from phase 32 in the acceptance).
5. Accessibility: the speaker indicator has `aria-live="polite"`, the countdown
   does **not** (it would spam a screen reader), and the whole flow is keyboard
   operable.
6. `?spk=sim` keeps working end to end, so the flow can be demoed without a key.

## Acceptance (write `tests/test_speaking_exam.py`)
- `material/speaking.json` parses and every part has ≥1 task with the required keys;
  every `photos[]` path exists on disk and returns 200.
- The five screens render in order; a screenshot per screen is written to
  `tests/out/` (the harness already does this).
- The speaker indicator flips to "Your turn" only after the examiner's audio ends
  (assert the state, not the pixels).
- In `sim` mode a full Part 2 run completes in under 200 s and produces bands for
  the 4 scales, none of them `null` except Pronunciation when no Azure key is
  configured (which must render "not measured", not a fake number).
- Silence handling: with the mic muted for 6 s, exactly one prompt is issued and
  `silence_prompts` is 1.
- The report lands in `D.log` with `type:"sp"`, `part:2`, `min` ≥ 3, `bands` present.
- ES mode: no English chrome left (allow-list: exam task text, book names, parts).

## Verify before finishing
```
cd tests && uv run --with playwright python test_speaking_exam.py   # exit 0
cd tests && uv run --with playwright python test_speaking_duo.py    # green
cd tests && uv run --with playwright python test_final.py           # green
cd tests && uv run --with playwright python tools/../tests/../tools/scan_texts.py 2>/dev/null || true
```
Finish with `VERDICT: ok` only if the three suites pass, and state in the verdict
what a real Cambridge examiner would still find missing (honesty over polish).

## Regression guard (learned the hard way, 2026-10-30)
The live transport used to send `setup.responseModalities` at the root; the API
answers `1007 Unknown name "responseModalities" at 'setup'` and closes the socket,
and the HUD only said "Examiner offline". It now lives inside
`setup.generationConfig.responseModalities` and the examiner reports `live`.
Do not move it back, and keep the close reason visible in the HUD: a silent close
is how this bug survived a whole session.
