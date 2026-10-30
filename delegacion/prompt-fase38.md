# Phase 38 — Two voices: instant and natural

## Measured floor on this key (2026-10-30, no guessing)
```
reply call (audio in, text out) : 2078–2608 ms   — best model is gemini-2.5-flash;
                                                   every "lite" model is 404 or slower
speech call (text in, audio out): 3179–4635 ms   — cost ≈ 0.3 s + the length of the line
total per turn                  : 5400–7000 ms
```
The speech call cannot be made faster: Google bills the audio duration, it generates
non-streaming, and a 10-word line is ~3 s of speech no matter what. So give the
candidate a choice instead of silently shipping a 6-second pause.

## A. `voice` setting with two modes
Add to `D.settings` (with input in the PLAN tab, default `fast`):
- `fast` — the reply **text** is spoken by the browser (`speechSynthesis`), so the
  turn costs only the reply call: ~2.1–2.6 s. Voice is the device voice: robotic but
  immediate and free.
- `natural` — today's path: Gemini TTS, 5.4–7 s, natural voice.
Default `fast`, and say in the UI what each one costs ("instant, device voice" /
"natural voice, ~6 s").

## B. Implementation notes
- Server: `POST /api/speaking/turn` accepts `tts: "gemini"|"none"`. With `"none"` it
  skips the TTS call entirely (saves quota and money) and returns `audio_b64: null`
  plus the text. Never build the audio anyway "just in case".
- Client: when `tts === "none"`, speak `reply` with `speechSynthesis` in `en-GB`,
  rate 0.95, and respect the existing per-voice mute and overlap handling: cancel the
  utterance on barge-in (`speechSynthesis.cancel()`), and never queue two utterances.
- Pick one voice deterministically from a small preference list, fall back to the
  default; log which one was chosen once, not per turn.
- iOS/Safari: `speechSynthesis` requires a user gesture the first time — the "Start
  exam" click is that gesture, so speak the first line from inside that handler.
- Show the measured latency of the last turn in the report ("reply in 2.3 s"), so the
  number is visible instead of claimed.

## C. Acceptance
- `test_speaking_exam.py`: with `tts:"none"` the response has `audio_b64 === null` and
  the TTS upstream call is **not** made (assert on the recorded calls).
- Same transcript, `tts:"gemini"` → audio present.
- Client test: the reply text reaches `speechSynthesis.speak` once per turn, and a
  barge-in cancels it.
- Latency printed for both modes; `fast` mode must be under 3000 ms or the test says
  so out loud.
- Quota: `fast` mode must consume **one** AI call per turn, not two — assert the
  instance counter increments by 1.
- `test_speaking_exam.py`, `test_speaking_duo.py`, `test_final.py` green.

## D. Honesty
The verdict must state: this is turn-based voice; the candidate cannot interrupt the
examiner mid-sentence; `fast` trades voice quality for ~3 s of latency.
