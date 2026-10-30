# Speaking: real-time evaluator and AI partner — feasibility plan

> Status: **research + plan**, nothing implemented. Written 2026-10-30.
> Every number marked *(verify)* is an assumption to check against current pricing/docs before
> committing to it. The exam facts below were read from cambridgeenglish.org on that date.

## 1. What the exam actually asks for

The B2 First Speaking paper, as published by Cambridge:

- **14 minutes**, **four parts**, **two candidates** examined together by **two examiners**
  (one interlocutor who talks, one assessor who only scores).
- Part 1: interview (personal questions). Part 2: individual long turn comparing two photos
  (1 minute each) + a short response to the partner's photos. Part 3: two-way collaborative
  task from a picture prompt with written questions. Part 4: discussion with the interlocutor.
- Four assessment scales, all 0–5: **Grammar and Vocabulary**, **Discourse Management**,
  **Pronunciation**, **Interactive Communication** *(the last three are published in the
  Cambridge handbook; the exam-format page confirms the first and the structure)*.

That structure is the whole design constraint. Two of the four scales can be graded from a
transcript. One needs acoustics. One needs a second human.

## 2. What is actually automatable

| Scale | Input needed | Automatable? | How |
| --- | --- | --- | --- |
| Grammar and Vocabulary | transcript | **Yes, well** | LLM against the descriptor text; this is exactly what the Writing corrector already does |
| Discourse Management | transcript + timing | **Yes, decently** | LLM for cohesion/coherence; timings from the ASR for hesitation and dead air |
| Pronunciation | **audio**, phoneme level | **Only with a specialised API** | Azure Speech *Pronunciation Assessment* returns accuracy / fluency / completeness / **prosody** at phoneme granularity, `en-US` supported (verified in Microsoft Learn docs) |
| Interactive Communication | two speakers | **No, not honestly** | Requires turn-taking with a real interlocutor; measurable proxies only (initiations, response latency, question ratio) |

The honest conclusion: **a real-time evaluator is feasible for 3 of 4 scales, and the AI partner
can be simulated well enough to train Part 1, Part 2 and Part 4 — but Part 3 (collaborative
task) needs a second learner, because the skill being tested is negotiating with a peer.**

## 3. Three architectures, by latency

### A. Record and grade (5–20 s) — simplest, fits today's stack

```
browser MediaRecorder (webm/opus, ~24 kB/s)
  → POST /api/speaking/evaluate (multipart, ≤ 5 MB, ≤ 3 min)
  → server: ffmpeg-less passthrough to STT (batch)
  → transcript + word timings
  → LLM with the four Cambridge scales → JSON (same shape as the writing corrector)
  → store scores + transcript, never the audio
```

- **Latency:** 5–20 s for a 1–2 min answer. Nobody expects instant feedback on a monologue.
- **Works on the Pi:** yes. It is HTTP upload + one outbound API call, exactly like the writing
  corrector. No WebRTC, no new daemon, no public port.
- **Testable with Playwright:** yes — `--use-fake-device-for-media-stream
  --use-file-for-fake-audio-capture=<wav>` feeds a real WAV file through the fake mic.
- **Cost:** one STT pass + one LLM call per answer. With batch Whisper-class pricing this is
  cents per session *(verify)*.

### B. Streaming metrics (1–2 s) — live coaching while you speak

```
browser AudioWorklet → 16 kHz PCM → WebSocket to STT provider (partial transcripts)
  → server-side reducer: words/min, filler ratio, pause > 1.5 s, long turns
  → live UI: "you have been speaking 40 s, 2 fillers, 118 wpm"
  → on stop: full evaluation as in A
```

- **Latency:** 300–1500 ms for partial text.
- **Needs:** a WebSocket STT provider (Deepgram, AssemblyAI, Azure streaming) and a WS relay,
  because the stdlib server cannot hold long-lived sockets comfortably. A tiny `websockets`
  relay process, or provider-side WebRTC, breaks the "stdlib only" rule — that is a real
  architectural decision, not a detail.
- **Why it matters:** real-time *numbers* (pace, fillers, silence) are what a self-taught
  speaker cannot self-observe, and they are cheap to compute. Real-time *scores* are not
  needed and would be noise.

### C. Full-duplex AI partner (300–800 ms) — a conversation

```
browser ←WebRTC→ provider realtime voice API (OpenAI Realtime / Gemini Live / Deepgram Agent)
  server only issues an ephemeral token and enforces quota
```

- **Latency:** natural turn-taking, barge-in supported.
- **Cost:** per-minute audio in **and** out, typically an order of magnitude above batch
  *(verify current rates; at hackathon scale, one demo conversation is affordable, a public
  feature for many users is not)*.
- **Testability:** effectively manual. You cannot assert on a voice conversation in CI.
- **Risk:** this is the feature that looks impressive in a video and is the least testable
  thing in the repo. Ship it behind a flag, with a hard per-user minute cap.

## 4. Recommended staging

| Stage | Scope | Effort | Why this order |
| --- | --- | --- | --- |
| **S1** | Part 2 long turn: record 60 s → transcript + 4 scales + 3 concrete fixes, saved as a `speaking` session in `D.log` | 2 phases | Fits the stack, exercises the existing AI guard, produces a real score |
| **S2** | Live metrics overlay (wpm, fillers, silence) using batch STT on 5 s chunks instead of a WS stream | 1 phase | 80% of the perceived "real-time" value with none of the WebSocket cost |
| **S3** | Part 1 & 4 partner: text-first chat with TTS voice replies (turn-based), ephemeral token for a realtime mode behind a flag | 2 phases | A turn-based partner already trains the interaction; full duplex is the last 20% |

**Do not start with C.** It demos best and helps least per hour invested, and it cannot be
regression-tested.

## 5. Constraints specific to this deployment

- **Raspberry Pi, 4 GB, no GPU.** Local ASR would be `whisper.cpp` tiny/base on ARM: usable for
  transcripts, **not** usable for pronunciation scoring (no phoneme alignment quality). So STT
  goes to an API, like the writing corrector already does.
- **No public ports.** Recording goes browser → existing HTTPS endpoint. WebRTC to a provider is
  outbound from the browser, so the Pi is not in the media path at all — good for a home box.
- **Stdlib-only server.** Multipart upload parsing must be written by hand (~40 lines) or the
  audio posted as base64 in JSON (simpler, +33% bytes, fine at 5 MB).
- **Privacy.** Audio is far more identifying than text: it can carry accent, age, gender, and
  ambient voices of third parties. Default must be **audio never stored**, transcript stored only
  if the user opts in, and the privacy policy needs a new section before any of this ships.
- **Prompt injection.** A transcript is untrusted text — it goes through the same fencing,
  heuristic blocking and output validation as the writing corrector (phase 17). No new surface,
  same guard.
- **Quotas.** Speaking burns minutes, not tokens. Needs its own daily minute cap per user,
  separate from `B2_AI_DAILY_*`.

## 6. Milestones with acceptance criteria

**M1 — Recording + upload (no AI).** `MediaRecorder` with a visible timer, 3-minute cap, 5 MB cap,
`POST /api/speaking/upload` accepting base64 payload, server validates MIME+duration header and
**discards the bytes** after STT. Test: Playwright fake audio device sends a 60 s WAV, endpoint
returns 200 with `{duration_s, bytes}`; a 4-minute file returns 413.

**M2 — STT + four-scale evaluation.** Transcript with word timings, then the LLM returns
`{bands:{grammar_vocabulary, discourse_management, pronunciation, interactive_communication},
evidence:[…], fixes:[…]}`. Pronunciation band comes from the Azure PA prosody/accuracy score, not
from the LLM's guess. Test: a fixture answer (TTS-generated, known text) scores within ±1 band of
a human-marked expectation; the response never contains the system prompt.

**M3 — Session integration.** The result is written into `D.log` as `type:"sp"` with
`{part, min, score, bands}` and shows up in the charts and the weekly plan. Test: log entry
appears, charts render, streak unaffected by a failed evaluation.

**M4 — Live metrics.** wpm, filler count, longest silence, computed client-side from partial
transcripts. Test: a scripted 90 s audio fixture yields wpm within ±5 of the known value.

**M5 — Partner (turn-based).** Part 1 question bank, TTS voice, transcript of both sides, per-turn
latency < 2 s. Test: 6-turn conversation completes with no JS errors; refusal path works when the
learner pastes an injection.

**M6 — Realtime flag (optional).** Ephemeral token endpoint, 5-minute hard cap, cost meter in
`/api/metrics`. Manual test only; documented as such.

## 7. What I would tell a judge

> The app already marks the paper nobody can self-mark. Speaking is the same problem with a
> microphone: three of the four scales are gradeable automatically, interactive communication is
> not, and pretending otherwise would be dishonest. So the plan scores what can be scored and
> gives a partner to practise the rest against.

## 8. Open questions before writing code

1. Which STT (batch vs streaming) — decides S2's whole shape.
2. Azure Speech free tier covers how many minutes/month *(verify)*.
3. Do we accept one non-stdlib process for streaming, or stay batch-only?
4. Store transcripts by default or opt-in? (Recommendation: opt-in, and never store audio.)
5. Does the LLM see the audio or only the transcript + PA scores? (Recommendation: only the
   transcript + numeric PA scores — cheaper and auditable.)
