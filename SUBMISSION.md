# B2 First Tracker — Devpost Submission

## Inspiration

Preparing for Cambridge B2 First (FCE) alone means one gap is almost impossible to close: Writing is 25% of the exam score, yet it is the one part nobody corrects for you. Practice essays pile up with no feedback, and generic AI chatbots hand out inflated marks that tell you nothing about what to fix. At the same time, the study tracker I was using had become a graveyard of unchecked boxes. This project started as a personal tool to fix both problems: a tracker that actually gets used, and an examiner that grades Writing the way Cambridge does.

## What it does

- **Study sessions and streak** — a weekly rotation across all 15 exam parts with official Cambridge time limits, a 3-tap mobile quick-log (FAB + 3-step modal), a daily streak with a 1-day freeze shield, and a weekly goal ring.
- **Onboarding intake** — six questions on first open (exam date, target grade, self-rated skills, hours per week, available days, what is hard) that seed a 5-session weekly plan before a single session is logged, followed by a 3-step feature tour.
- **12-item diagnostic** — a 10-minute cold-start quiz covering all 7 parts of Reading & Use of English that populates the error log and highlights the 3 weakest parts on day one.
- **Progress charts** — 4 SVG charts: Writing evolution, accuracy by part, error taxonomy breakdown, and weekly consistency, plus 3 stage gates (Foundations, Precision, Mastery) with automated metric gates.
- **AI Writing examiner** — grades Essays, Articles, Reports, Reviews, and Emails against the official Cambridge B2 First Writing assessment scale: 4 bands (Content, Communicative Achievement, Organisation, Language) scored 0–5 each for a total of 20. Every band must be backed by an exact quote from the student's text, each criterion must list 2 concrete weaknesses, and the examiner rewrites 3 weak sentences from the student's own text at B2+/C1 level.

## How we built it

- A single-file frontend (`index.html`, 5,380 lines of vanilla HTML/CSS/JS) with no build step, no bundler, and no `node_modules` — it opens instantly on desktop and mobile.
- A backend (`server.py`) using only the Python 3 standard library, so it runs on a Raspberry Pi, a VPS, or a Docker container without `pip install`.
- Progress is stored as atomic JSON on disk (`store.py`, with rotating backups) behind a 6-function seam ready for SQLite.
- The AI examiner runs through a stateless proxy in `server.py` with strict server-side schema validation: malformed or out-of-range JSON from the model is rejected with `422` before it reaches the UI, and API keys live only in the browser's `localStorage` and are never logged or persisted server-side.
- The Cambridge B2 First Writing assessment scale is transcribed verbatim from the official B2 First Handbook (pages 33–35) into `prompts.py`, with explicit calibration rules so the model grades like an examiner rather than like a cheerleader.

## Challenges we ran into

1. **The examiner inflated bands.** Early prompts gave 19/20 to mediocre texts — a 160-word B2 email with simple structures and a short repetitive essay both scored `content 5, communicative_achievement 5, organisation 5, language 4`. A grader that generous is worse than no grader. We added mandatory calibration rules (a criterion with 2 named weaknesses cannot be a 5; every 4 or 5 must justify why it is not one band higher; effort and length earn nothing) and made the `weaknesses` field mandatory — the server rejects the response with `422` if it is missing.
2. **DeepSeek returned `feedback` as an array.** The schema demanded an object with one key per criterion, and a plausible-looking array sailed through casual parsing. We fixed it with an explicit JSON template in the prompt ("return arrays where objects are required — never") and strict server-side validation of exact keys and types.
3. **Writing source PDFs have no text layer.** The official past-paper PDFs are scanned images, so text extraction produced garbage. Instead of guessing OCR output, we link the official papers directly and keep the rubric — the part the grader actually needs — hand-transcribed and verified against the handbook.

## Accomplishments

The calibration work produced real band separation on test texts: a weak text scores **9/20**, a medium one **14/20**, and a strong one **20/20**. Before calibration, all three scored around 19/20. That separation is the difference between a demo and a tool someone can study with — the score now tracks what the writing is actually worth.

## What we learned

A generous corrector is worse than no corrector. If a tool tells you 19/20, you never study what is missing. Making the model name concrete weaknesses per criterion — and rejecting its output when it cannot — did more for accuracy than any prompt-engineering flourish.

## What's next

- AI-assisted Speaking practice for Parts 3–4 (the collaborative long turn and discussion).
- A weekly study plan derived directly from the diagnostic's weakest parts.
- SQLite storage behind the existing `store.py` seam for real multi-user deployment.

## Built With

python, javascript, html, css, docker, deepseek, gemini, playwright, systemd, linux, raspberry-pi
