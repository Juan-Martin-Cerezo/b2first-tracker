# Phase 36 — Turn-based voice examiner (works without Live access)

## Why this exists (measured, 2026-10-30)
The owner's Gemini key exposes **50 models but zero with `bidiGenerateContent`**.
The Live path therefore returns `setupComplete` and then never generates audio: the
examiner is silent forever. Tested and proven with the same key:

```
gemini-2.5-flash-preview-tts : TTS ok (natural voice)
gemini-2.5-flash             : audio input → exact transcript ok
gemini-2.5-flash             : text turn → "What makes it healthier?" ok
```

So build the examiner on a **turn-based voice pipeline** that this key can run, and
keep the Live transport for keys that do have it.

## Flow per turn (client)
1. The existing client-side VAD decides the candidate started and stopped speaking
   (800 ms of silence closes the turn; 15 s hard cap).
2. The client sends `POST /api/speaking/turn` with base64 16 kHz mono PCM (or WAV)
   for **that turn only** — never the whole session, to keep payloads small and
   privacy honest.
3. The server transcribes it and returns the examiner's reply **plus** its audio.
4. The client plays the reply and shows the transcript line.

Target: under 3 s from "candidate stops talking" to "examiner starts speaking".
Measure it and print the number in the test; do not claim it if it is not measured.

## Server: `POST /api/speaking/turn`
Request: `{audio_b64, mime, part, role:"examiner"|"partner", history:[{who,text}], task_id}`
Response: `{transcript, reply, audio_b64, mime:"audio/wav", ms:{stt,llm,tts}}`
- Audio limit 25 s / 800 KB per turn; reject larger before decoding.
- Use one Gemini call that takes **audio + the examiner prompt** (audio
  understanding and the reply in one request) — fewer round trips, lower latency.
- Then one TTS call (`gemini-2.5-flash-preview-tts`, voice `Puck` for the examiner,
  `Kore` for the partner) and return the audio.
- Keep `history` bounded to the last 6 turns; never store it server-side, never log
  audio or transcript content.
- Same plan quotas as the Live token route (free: 1 mock/week; pro 6/month; owner
  unlimited), counted by minutes, not by turns.
- If a key with Live access is configured (`B2_SPK_LIVE=1` and a model in
  `bidiGenerateContent`), `GET /api/speaking/capabilities` returns
  `{live:true, turn:true}`; otherwise `{live:false, turn:true}`. The UI must not
  advertise real-time when `live` is false.

## Client
1. `makeTurnTransport(cfg)` next to `makeSimTransport` / `makeLiveTransport`, same
   interface (`start/sendAudio/mute/close`), so phase 35's screens do not change.
   `makeTransport()` picks: live if capabilities say so, else turn, else sim.
2. Recording: reuse `spkVad`; buffer the PCM of the current turn in memory, drop it
   after sending. Show "listening" while open, "thinking…" while waiting, and
   "examiner speaking" during playback.
3. Playback: decode the returned WAV with `AudioContext.decodeAudioData` and play it
   through the existing per-voice gain chain, so muting and overlap still work.
4. Nothing is uploaded until the turn closes: say it in the UI
   ("audio is sent when you stop speaking").
5. If the request fails, say so plainly and offer retry; never pretend the examiner
   answered.

## Acceptance (extend `tests/test_speaking_exam.py`)
- With a stubbed Gemini, a turn round-trips: transcript arrives, reply audio plays,
  the transcript line appears in the HUD.
- `ms` values are present and the measured total is printed; flag it if > 4000 ms.
- A 30 s payload → 413 before any decode.
- The server stores nothing: after a full part, `grep -r` the transcript text in
  `data/` → zero hits.
- `GET /api/speaking/capabilities` reports `live:false` on this key and the UI
  hides any "real-time" wording.
- Quota: the 2nd mock in the same week for a free account → 429 with the plan
  message; owner → never.
- `test_speaking_exam.py`, `test_speaking_duo.py`, `test_final.py` all green.

## Honesty requirement in the verdict
State the measured stop-talking → first-audio latency, and say explicitly that this
is turn-based voice, not full duplex: the candidate cannot interrupt the examiner
mid-sentence the way they can in the real exam.
