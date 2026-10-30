# Speaking: real-time examiner + partner, live pronunciation and silence

> **Status: plan only, except S1 (§8): mic -> AudioWorklet VAD -> live HUD shipped in phase 18.
> It is client-only; no audio leaves the tab. Everything from S2 onwards is unimplemented.**
> Supersedes the staging in `docs/SPEAKING-EVALUATOR.md` §4 (that document stays as the
> research record; §2's capability table is still correct and is not repeated here).
> Written 2026-10-30. Facts marked *(verified)* were read from the vendor's own docs on this
> date, with the URL next to them. Numbers marked *(estimate)* are arithmetic on verified
> prices and must be re-measured before anyone quotes them as a result.

---

## 1. What Juan asked for, exactly

1. A **live** speaking examiner — it talks to him in real time, not turn-by-turn over text.
2. **Pronunciation** identified, not guessed from a transcript.
3. **Silences** detected — where he froze, for how long.
4. **Exactly what he says**, transcribed while he says it.
5. An **examiner and a partner talking at the same time**, all in real time — the exam is two
   candidates plus an interlocutor, and both voices have to exist simultaneously.

That is the whole scope. Anything in this plan that does not serve those five lines is cut.

---

## 2. What the providers actually offer (verified)

| Capability | Reality | Source |
| --- | --- | --- |
| Duplex voice, barge-in | Gemini Live API: stateful **WSS**, raw PCM in at **16 kHz**, out at **24 kHz**, **barge-in** supported, "audio transcriptions of both user input and model output" *(verified)* | `ai.google.dev/gemini-api/docs/live` |
| Client connects directly to the model | **Ephemeral tokens**: backend mints a short-lived token (`uses:1`, 1 min to open a session, 30 min connection lifetime); the browser then talks to Google directly, so **the Pi is not in the media path** *(verified)* | `ai.google.dev/gemini-api/docs/ephemeral-tokens` |
| Two distinct voices in one session | **Not available in Live.** Multi-speaker exists in *speech generation* (TTS), not in the realtime Live session, which carries one model voice *(verified: no multi-speaker option in the Live config; the only multi-speaker config in the docs is TTS)* | same |
| Pronunciation with phonemes | Azure Speech **Pronunciation Assessment**: `Granularity.Phoneme`, `EnableProsodyAssessment`, `en-US` default, and **continuous/unlimited streaming** ("as long as you don't stop recording, the evaluation doesn't finish") *(verified)* | `learn.microsoft.com/.../how-to-pronunciation-assessment` |
| Azure free tier | **5 audio hours/month** real-time STT free (F0), enough for ~21 full speaking mocks/month *(verified)* | `azure.microsoft.com/pricing/details/cognitive-services/speech-services` |
| Live audio price | audio in **$0.005/min**, audio out **$0.018/min** on the realtime voice model *(verified, pricing page)*; equivalent to $3 / $12 per 1M audio tokens at 25 tok/s | `ai.google.dev/gemini-api/docs/pricing` |

**The one hard truth:** no provider gives you two voices inside a single duplex session. So
"examiner and partner at the same time" is **not a configuration flag — it is an architecture
decision.** §4 is that decision.

---

## 3. Signal inventory — where each number comes from

This is the part that decides whether the feature is honest or a demo.

| Juan asked for | Produced by | Latency | Gradeable? |
| --- | --- | --- | --- |
| Exactly what he says | Gemini Live **input transcription** events | 300–800 ms | — (it is the input for everything else) |
| Silences, pauses, dead air | **Client-side VAD** in an `AudioWorklet` (RMS + zero-crossing on the 16 kHz PCM the browser already has). Do not ask the model for this; measure it. | < 50 ms | — (raw metric) |
| Pace, fillers | Reducer over partial transcripts + timings: wpm, `um/uh/like/you know` per 100 words, longest silence | < 1 s | Discord Management evidence |
| Pronunciation | **Azure PA** on the candidate's audio, phoneme granularity, prosody on | 1–3 s after the turn | **Yes**, and this is the only source allowed to set the Pronunciation band |
| Grammar & Vocabulary, Discourse | DeepSeek (existing corrector path) over the finished transcript + the metric object | 3–8 s after the session | Yes |
| Interactive Communication | **Not gradeable.** Proxies only: who initiated, response latency, question ratio, overlap seconds | live | No — reported as a diagnostic, never as a band |

Rule that must survive into the code: **the LLM never invents the Pronunciation band.** If Azure
did not score a segment, that scale is `null` and the UI says "not measured", not "3".

---

## 4. Architecture — the director pattern

```
                    ┌──────────────── browser (index.html, vanila JS) ────────────────┐
mic ──AudioWorklet──►│ PCM 16 kHz ──┬──► VAD ──► silence/pause timeline ──► UI overlay │
                    │              ├──► chunk buffer ──► WSS 1: Live session A       │
                    │              │        (EXAMINER voice, examiner prompt)        │
                    │              ├──► chunk buffer ──► WSS 2: Live session B       │
                    │              │        (PARTNER voice, candidate prompt)       │
                    │              └──► rolling 10 s opus ──► POST /api/speaking/pa   │
                    │                        (Azure PA → phoneme + prosody scores)   │
                    │  DIRECTOR (state machine): whose turn it is, who is muted       │
                    │  mixer: 2 × WebAudio gain nodes → one output                   │
                    └───────────────────────────────────────────────────────────────┘
        ▲ ephemeral tokens minted per session by server.py (key never leaves the Pi)
        ▲ at session end: transcript + metrics + PA → DeepSeek → 4-scale report → D.log
```

**The director is the whole feature.** Two independent duplex agents hearing the same
microphone will talk over each other within 20 seconds. The director is a small client-side
state machine that enforces exam turn structure:

| Part | Director behaviour |
| --- | --- |
| 1 — interview | Examiner only. Partner session is **not opened** (cost control). |
| 2 — long turn | Examiner asks, candidate talks 60 s, partner gives the 30 s response, examiner closes. Strict alternation, hard mute on the non-speaking agent. |
| 3 — collaborative | Both open. Examiner *introduces* and then goes quiet; partner drives with the written prompt questions; examiner re-enters only on 2 s of dead air from both. This is the only part where overlap is allowed, and overlap is *measured*, not prevented. |
| 4 — discussion | Examiner + partner both live, turn-taking by who was addressed (`you` ⇒ candidate, question directed at partner ⇒ partner). |

Muting is done at the audio level (gain 0) *and* by pausing that session's `realtimeInput`;
killing a session and reopening it costs 1 s and a new ephemeral token, so it is only done on
part boundaries.

**Fail-safe:** if either socket drops, the other keeps running, the UI shows which voice is
live, and the report is produced with the degraded scales marked `null`. A dead partner must
never kill the session — this is the single most likely thing to break in front of a user.

---

## 5. Latency budget (target, to be measured)

| Hop | Budget |
| --- | --- |
| mic → AudioWorklet frame | 20 ms |
| client → Live session (WSS, PCM) | 60–120 ms |
| model first audio token | 300–600 ms |
| audio out playback | 40 ms |
| **perceived reply latency** | **< 800 ms** |
| VAD flag on screen | < 100 ms |
| PA score for a finished turn | 1–3 s |
| full 4-scale report after "stop" | 5–10 s |

The Pi contributes **one** hop: minting a token (~100 ms, `POST /api/speaking/token`). No audio
passes through it. That is the reason this is buildable here at all.

---

## 6. Cost model and caps

Per minute, one live voice *(verified prices, arithmetic marked estimate)*:
audio in `$0.005` + audio out while the agent speaks. A 14-min mock:

| Scenario | Maths | Per mock |
| --- | --- | --- |
| Examiner only, Part 1 + 2 | 14 min in ($0.07) + ~5 min out ($0.09) | **≈ $0.16** |
| Examiner + partner (Parts 2–4) | 2 × input ($0.14) + ~7 min combined out ($0.13) | **≈ $0.27** |
| Plus DeepSeek report + PA | one LLM call + ≤ 1 audio hour Azure (free tier) | **≈ $0.01** |

So **≈ $0.25 per full mock, $0 for the first ~21 mocks/month** while Azure's 5 free audio
hours cover the PA side. That changes the earlier assumption in `SPEAKING-EVALUATOR.md` §3C
that full duplex is "an order of magnitude above batch": at current prices it is cents per
session, and the real constraint is **abuse**, not cost.

Caps to enforce server-side, in the same place the AI quotas live:

- `B2_SPEAK_MIN_DAILY_PER_USER=20` (minutes, 14-min mock + slack) — hard stop, mid-session.
- `B2_SPEAK_MIN_DAILY_TOTAL=120` for the instance.
- Sessions ≥ 3 min must be **minted only for an authenticated user with a token**; ephemeral
  tokens are `uses:1` so a leaked one dies after one session and 30 min.
- `GET /api/metrics` gains `speaking_minutes_today` and `speaking_tokens_minted`.

---

## 7. Privacy and security deltas (must land before any of it ships)

Audio is far more identifying than text — it carries accent, age, gender and any third party
in the room. Deltas to `docs/PRIVACY.md` and to the existing guard:

1. **Audio is never stored on the Pi.** Browser → provider directly; the Pi sees only token
   requests, metrics and the final transcript. `POST /api/speaking/pa` receives ≤ 10 s of opus,
   forwards it to Azure, and discards it in the same request handler.
2. **Transcript storage is opt-in**, default off; the report keeps bands and metrics, not the
   words. A checkbox in the report, not a hidden default.
3. The transcript is **untrusted text**: it goes through the phase-17 fence (`<<<TEXT_nonce>>>`),
   the injection heuristics, and the output leak guard. Same guard, no new surface.
4. New section in the privacy policy: what the provider receives, that Google/Azure process it
   outside Argentina, retention (none on our side), and how to delete a session.
5. The browser already has CSP — the Live WSS endpoint and Azure's host must be added to
   `connect-src` **explicitly**, not via `*`. That is a one-line diff with a security meaning.

---

## 8. Staging — five phases, each shippable alone

Order is by *risk retired per hour*, not by demo value. **S4 is the one Juan asked for and it is
not first**, because everything before it is a prerequisite that is individually useful.

### S1 — Recorder + live metrics, no AI (½ phase)

`MediaRecorder` unused for the metrics: stream the mic into an `AudioWorklet`, run VAD, show a
live HUD (elapsed, wpm from a batch-STT chunk pass, fillers, longest silence). No exam, no score.

**Acceptance:** Playwright with `--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=fixtures/90s.wav`
shows wpm within ±5 of the fixture's known value, and a 2.2 s inserted silence is reported as
`2.2 ± 0.1 s`. Fails if the HUD blocks the main thread (assert frame time < 16 ms).
*Retires the risk:* audio capture, VAD tuning, and the fact that the Pi is irrelevant.

### S2 — Azure Pronunciation Assessment endpoint (1 phase)

`POST /api/speaking/pa` → `{accuracy, fluency, completeness, prosody, words:[{w, err, phonemes:[{p, score}]}]}`.
Server-side only, key never in the browser, 10 s / 2 MB cap, 30 calls/min/user.

**Acceptance:** a TTS-generated fixture of known text returns word timings and a per-word score;
a fixture with an injected mispronunciation scores that word lower than the median by ≥ 20
points; a 5 MB payload → 413; `Authorization` absent → 401. *Retires:* the honesty question —
pronunciation is measured, not guessed.

### S3 — Examiner live, Part 1 + Part 2 (1 phase)

Token endpoint, one Live session, examiner prompt with the real Part 1 question bank and Part 2
photo-comparison script, input transcription streamed into the transcript pane.

**Acceptance:** a scripted 6-exchange session completes with no JS errors; input transcription
matches the fixture within WER < 15 %; reply latency p50 < 800 ms measured by the client;
`inject` pasted into the transcript path still gets refused by the report guard. *Retires:*
the duplex loop, transcript, and the token model.

### S4 — Examiner + partner, simultaneous (2 phases) ← *what Juan asked for*

Second Live session, the director state machine of §4, two-voice mixer, per-part turn rules,
overlap measurement.

**Acceptance:** in Part 3 both voices are audible and the partner produces ≥ 3 questions from
the prompt; in Part 2 the director never lets partner audio start before the candidate's 60 s
expire ± 2 s; killing session B mid-session leaves the session running and the report complete
with `interactive_communication: null`; a 20-minute session is force-stopped at the cap with a
clear message. *Retires:* the "two agents talk over each other" risk — the only risk that can
kill the feature.

### S5 — Report + `D.log` (½ phase)

Transcript + metrics + PA → DeepSeek → four bands with quoted evidence, three fixes, saved as
`{type:"sp", part, min, bands, metrics}`. Charts and weekly plan pick it up with no new code.

**Acceptance:** a 14-min fixture yields bands within ±1 of a human-marked expectation on the
three gradeable scales; `interactive_communication` is `null` with the proxy numbers attached;
the entry appears in the log, the charts and the plan; a failed evaluation does not touch the
streak.

**Total: ~5 phases.** Reusable across all five: `docs/SPEAKING-EVALUATOR.md` §5's constraints
hold unchanged (Pi, no public ports, stdlib server, quotas, injection).

---

## 9. What could kill it (ranked)

1. **Two agents, one mic** → they hear each other? No: each session hears only the *candidate's*
   mic stream. The partner never hears the examiner, so it cannot answer the interlocutor — the
   director must feed it the examiner's transcript as text. That is a design constraint, not a
   bug, and it is why S4 is two phases.
2. **Director complexity.** A hand-written state machine per part, 4 parts × ~6 states. This is
   where the bugs will live. Mitigation: the states are pure and therefore unit-testable without
   audio — a 40-line assertion suite, no Playwright.
3. **Azure PA on a shared mic.** Prosody scores degrade with background noise; the report must
   surface a confidence and refuse to band when the mic is clipping. Otherwise it hands out
   2s that feel arbitrary.
4. **Cost abuse** with a shared DeepSeek/AI budget: a minted token is money. Quotas in §6 are
   mandatory, not a nice-to-have.
5. **Non-determinism in CI.** Real model audio cannot be asserted. Every test above asserts on
   *our* side of the boundary (VAD, director states, endpoint contracts, transcript WER) — never
   on the model's prose. If a test needs the model to say something specific, it is the wrong test.
6. **The Pi.** Passes, but only because it is out of the media path. The moment someone proxies
   audio through it, this feature is dead on ARM.

---

## 10. Blocked on Juan (nothing below is code)

| Decision | Why it blocks | Recommendation |
| --- | --- | --- |
| **Gemini API key** (new, separate from DeepSeek) | Live API needs a key with billing enabled; free tier for native-audio Live is limited | Create one, put it in `~/.config/b2first/speech.env` as `B2_SPK_GOOGLE_KEY`, never in the repo |
| **Azure Speech key + region** | PA is Azure-only; free 5 h/month covers ~21 mocks | Create a free F0 resource, `B2_SPK_AZURE_KEY` / `B2_SPK_AZURE_REGION` |
| **Daily minute cap** | Protects the budget | `20 min/user/day`, `120 min/instance/day` |
| **Store transcripts?** | Privacy default | Off by default, opt-in per session |
| Domain (HANDOFF §12.1) | Unchanged, independent | Still open |

If either key is missing, the feature must degrade to **S1 metrics only** — live HUD, no voices,
no scores. That is the correct behaviour with one key absent and it needs to be true from S1.

---

## 11. Non-goals

- Grading Interactive Communication with a number. It gets proxies, labelled as proxies.
- Replacing a human examiner for certification. This trains; it does not certify.
- Storing audio. Ever. Not for "quality", not for "debugging".
- A three-way session (examiner + two candidates). Out of scope until S4 is stable.
- Running ASR on the Pi. `whisper.cpp` tiny on ARM produces transcripts of a quality that would
  make the Grammar band fiction.

---

## 12. The one-paragraph version for a judge

> The exam is two candidates, two examiners and four scales. We can now put a live examiner and
> a live partner in the same room as the learner, both speaking, and measure what no self-taught
> candidate can observe: phoneme-level pronunciation from Azure, pauses from a VAD on the raw
> audio, pace and fillers from the streaming transcript. Three of the four Cambridge scales are
> graded, the fourth is reported honestly as proxies, and the audio never touches our server.
