# Devpost submission — Build Your First AI App 2026

Deadline: 27 Nov 2026, 5:00pm EST (19:00 ART).
Eligibility check pending: the rules require being above the legal age of majority; confirm with the organizer before submitting.

## Title

B2 First Tracker

## Tagline (<= 120 chars)

An AI examiner that marks Cambridge B2 First writing and runs the 14-minute Speaking exam out loud.

## Links

- Try it: https://firsttracker.app
- Source: https://github.com/Juan-Martin-Cerezo/b2first-tracker
- Video: <pending>

## Built with

gemini-3.8-live, Gemini Live API, gemini-2.5-flash, Gemini 2.5 Flash TTS, DeepSeek V4.1 Flash, Python, WebAuthn, Azure Pronunciation Assessment, Cloudflare

## Inspiration

B2 First candidates who study alone can check multiple-choice answers against a key, but nobody marks their Writing and nobody sits through their Speaking. Feedback arrives days later, if it arrives at all, and it rarely points at the exact band that cost them the grade.

## What it does

B2 First Tracker is a self-study system built around one practice log:

- A 12-question diagnostic maps the weakest exam parts and builds the first week around them. The check can be skipped and taken later.
- A daily session shows one prioritized task with its real exam timer.
- Writing (essay, article, report, review, email) is scored on the four published Cambridge bands, 0-5 each, with quotes from the draft, two weak spots and three rewritten sentences. The exam prompt can be pasted so Content is checked point by point.
- Speaking runs all four parts with real timings (2, 4, 4 and 4 minutes), a partner voice in Part 3, a transcript and a banded report.
- Errors are logged by root cause (vocabulary, grammar, distractor, time limit) so the next session targets the cause, not the symptom.

## How we built it

A single Python stdlib server renders the app and stores each account's progress. The browser owns the microphone and speech recognition; the server mints short-lived Gemini Live tokens so audio goes straight from the browser to Google and never touches the server or a disk.

Two AI paths, chosen by cost and latency:

1. Speaking, real time: Gemini 3.8 Live through the Live API. The server only mints an ephemeral token; the examiner voice and the candidate turns run over the WebSocket. When Live is unavailable, the app degrades to one request per turn: Gemini 2.5 Flash for transcript and reply, Gemini 2.5 Flash TTS for the voice.
2. Writing and report: DeepSeek V4.1 Flash with strict JSON output. The rubric prompt asks for the four bands, quoted evidence and three rewrites, and the response is capped at 8 KB and never trusted blindly: the server validates the shape before rendering.

Pronunciation is measured only by Azure Pronunciation Assessment. Without that key the report prints "not measured" instead of inventing a score, and the endpoint returns 503 speech_not_configured. The honesty rule is enforced in code, not in the prompt.

Costs are bounded per account and per instance (5 writing evaluations and one 15-minute Speaking mock per day; 20 text calls and 25 voice minutes per instance per day). Keys live only in the server environment; no provider key is ever sent to the browser or committed.

## Challenges

- Keeping the feedback truthful: the model proposes, the code validates, and a band that cannot be measured stays unmeasured.
- Cost control on a hobby budget: measuring real token and audio prices, then sizing the daily caps to fit the balance.
- Streaming audio without storing it: ephemeral tokens plus a server that never sees the media bytes.

## What we learned

Real-time voice is the expensive part, not the text model: one 14-minute mock costs about 50x one writing evaluation. A rubric prompt with quoted evidence produces feedback students can act on, while a generic "score my essay" prompt produces numbers with no handle.

## What's next

- Calibration against real marked scripts.
- A teacher view for classrooms.
- Offline mode for practice papers.

## My contribution

Solo project. I designed the product, the rubric prompts, the cost model and the tests, and wrote the Python server and the front end. AI coding assistants were used for implementation and review, as declared in the repo; every line was reviewed and verified with the test suite and manual runs against production. Third-party resources are credited in the README.

## AI tools disclosure

Claude/Codex-style coding agents (via agy) for code generation and review, Gemini and DeepSeek APIs at runtime as described above. No AI-generated user data or fake metrics anywhere in the submission.

## Notes for judges

- Sign up with a username and a 12+ character password. No email required.
- A fresh account can skip the diagnostic in the onboarding and go straight to Today.
- Daily caps are deliberate: one full Speaking mock (14 min) and five Writing evaluations per account per day.

## Video script (2:30, English)

1. 0:00-0:15 — Landing: "AI rubric marking and live voice practice for B2 First". One sentence on the problem.
2. 0:15-0:45 — Create account, onboarding: exam date, skill ratings, skip the check.
3. 0:45-1:30 — Writing: paste a 160-word essay, run the corrector, show the four bands, the quoted evidence and the three rewrites.
4. 1:30-2:10 — Speaking: start Part 1, answer one question out loud, stop, show transcript and banded report; point at "not measured" if Pronunciation has no Azure score.
5. 2:10-2:25 — Today's session and the plan built from the diagnostic.
6. 2:25-2:30 — Repo and close: "One log, four skills, honest AI feedback."
