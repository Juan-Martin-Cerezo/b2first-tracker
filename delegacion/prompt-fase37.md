# Phase 37 — Make the turn-based examiner listen, and make it fast

## Two defects measured on the live service (2026-10-30)
```
POST /api/speaking/turn  (6.2 s of real speech, Part 1)
  transcript: "In my opinion, traveling by bike is healthier than the metro."   exact
  reply:      "How do you use technology in your daily life?"                   unrelated
  latency:    6407 ms (llm 2919 + tts 3473)
```
1. **It does not react.** The reply came from the scripted Part 1 question list, so
   the transcript is decoration: the examiner would answer the same thing to any
   candidate. This defeats the whole point.
2. **6.4 s per turn** reads as broken.

## A. The examiner must answer what it heard
- The reply prompt gets: the task (from `material/speaking.json`), the **last 6 turns
  of transcript with who said what**, and the new transcript.
- Hard rule in the prompt: reference something concrete the candidate said (a word
  from their answer) before asking the next question. If the candidate answered with
  fewer than 4 words or went off-topic, ask a "why / can you tell me more about X"
  follow-up instead of advancing the script.
- Keep the scripted question list as the *fallback* when the candidate is silent, not
  as the normal path.
- Never invent what the candidate said: if the transcript is empty, say the audio was
  not understood and ask them to repeat. No fake transcription.

## B. Latency budget: target under 3000 ms end to end
Measured costs: TTS ≈ 0.3 s + audio duration; text ≈ 2.9 s with thinking on.
- Set `thinkingConfig: {thinkingBudget: 0}` for the examiner turn (measured: no loss
  in quality for a 12-word reply, and it removes the reasoning pass).
- Cap `maxOutputTokens` at 80 and instruct "max 14 words". Short line = short TTS =
  faster playback. A 4 s reply costs 4 s of TTS no matter what.
- **Pre-generate and cache TTS for the scripted lines** (`material/speaking.json`) the
  first time a part is opened: cache in `data/tts/<sha256(text+voice)>.wav`, 0600,
  max 40 entries, LRU. The first question then plays instantly, and only genuine
  follow-ups pay the TTS cost.
- Stream the reply text to the client as soon as the text call returns, and start
  playback when the audio arrives (do not wait for both if the UI can show text
  first).
- Measure and print: `ms.stt`, `ms.llm`, `ms.tts`, `ms.total`. Assert `total < 4000`
  in the test with the cached path, and print the cold number honestly.

## C. The comprehension check that proves it listens
Add to `tests/test_speaking_exam.py`:
- Same audio fixture, two different candidate answers → two **different** replies,
  and each reply contains at least one content word from its own transcript.
- A silent/empty audio fixture → the reply asks the candidate to repeat, and the
  transcript field is empty (never invented).
- The prompt sent upstream includes the previous turns (assert on the recorded
  request body, not on the model's output).

## D. Copy fix found by clicking through
The Part 1 brief says "A partner joins you in Parts 2, 3 and 4" — true but confusing
inside Part 1. Give each part its own line:
- P1: "Just you and the examiner. No partner."
- P2: "You speak for a minute, then your partner answers a question about the photos."
- P3: "You and your partner discuss a task card, then decide together."
- P4: "A discussion with the examiner and your partner about the topic."

## E. Do not break what works
- `/api/speaking/capabilities` must keep saying `live:false` on this key.
- No audio, transcript or reply stored in `data/` except the TTS cache (text-keyed).
- `test_speaking_exam.py`, `test_speaking_duo.py`, `test_final.py` green.
- In the verdict, state the measured cold and warm latency, and say plainly that
  this is turn-based: the candidate cannot interrupt mid-sentence.
