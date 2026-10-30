# PROMPT — Fase 20: examinador en vivo (S3)

Sos ingeniero senior WebRTC/WebSocket + frontend. Repo `/home/juan/b2first-tracker`. **CODIFICAR.**
Inglés en código/commits. Leé `docs/SPEAKING-REALTIME-PLAN.md` §2, §4, §5 y §8-S3.

## Contexto y regla de oro

El examinador habla en tiempo real contra **Gemini Live API** (`WSS`, PCM 16 kHz in / 24 kHz out,
barge-in, transcripción de entrada y salida). El browser se conecta **directo a Google** con un
**ephemeral token** que emite nuestro backend; la Pi **no** está en el path de audio.

Antes de escribir el cliente, **verificá el protocolo exacto** en la doc oficial
(`curl -sL https://ai.google.dev/gemini-api/docs/live` y `.../docs/ephemeral-tokens`): nombre del
modelo, forma del mensaje `setup`, nombre del evento de transcripción de entrada, y la URL WSS.
**No inventes nombres de eventos ni campos**: si la doc no lo confirma, escribí el código para
fallar explícito (`throw new Error("unverified protocol field")`) en vez de adivinar.

## A — Backend: `POST /api/speaking/token`

- Auth obligatoria. Devuelve `{token, expires_in, model, ws_url}` — **nunca** la API key.
- Mint con `urllib` a la API de tokens efímeros de Google (`uses:1`, `expireTime` +30 min,
  `newSessionExpireTime` +1 min). Key desde `B2_SPK_GOOGLE_KEY`; si falta → **503
  `{"error":"speech_not_configured"}`** (mismo contrato que fase 19).
- Cuotas nuevas: `B2_SPK_MIN_DAILY_PER_USER` (default **20**) y `B2_SPK_MIN_DAILY_TOTAL`
  (default **120**) en **minutos**, no requests. Se consumen del lado del cliente: endpoint
  `POST /api/speaking/minute` con `{seconds}` que acumula por usuario/día y responde
  `{remaining_s}`; al llegar a 0 el cliente debe cerrar la sesión sola y mostrar
  "daily speaking limit reached (20 min)". Debe sobrevivir a reinicios (persistir en
  `data/users/<uid>/speaking.json`, `0600`, con el mismo patrón de locks que `progress.json`).
- Rate limit: 10 tokens/min/usuario. `GET /api/metrics` suma `speaking_minutes_today` y
  `speaking_tokens_minted`.

## B — Cliente: capa de transporte abstracta (esto habilita los tests)

En `index.html`, dentro del bloque SPEAKING STUDIO, definí **una interfaz** y dos implementaciones:

```js
// spkTransport: { start(cfg), sendAudio(int16), sendText(s), mute(bool), close(), on:{audio,inText,outText,error} }
function makeLiveTransport(cfg) { /* WebSocket real a Gemini, base64 PCM 16k */ }
function makeSimTransport(cfg)  { /* scripted, determinista, sin red */ }
function makeTransport(cfg)     { return (cfg.mode === 'sim') ? makeSimTransport(cfg) : makeLiveTransport(cfg); }
```

- `sim` se activa con `?spk=sim` en la URL o `localStorage.b2f_spk_sim='1'`. Reproduce un guion
  fijo (3 turnos del examinador con texto conocido) y emite audio sintético (tono 440 Hz, 200 ms
  por chunk) por el mismo camino de reproducción que el real. **Es lo que usan los tests y el
  modo demo**; el código real no se toca.
- Si `/api/speaking/token` devuelve 503, el cliente **cae a `sim` automáticamente** y muestra un
  badge honesto: `Examiner unavailable (no speech key) — simulated voice`. Nunca un error crudo.

## C — Reproducción y barge-in

- Cola de `AudioBufferSourceNode` a 24 kHz, encolado contiguo (`when = max(ctx.currentTime,
  nextTime)`), `nextTime` avanza por `buffer.duration`. Nada de `setTimeout` para timing de audio.
- **Barge-in**: mientras el modelo habla, el HUD muestra "examiner speaking"; si el VAD local
  detecta habla del alumno durante > 300 ms, se llama `mute(true)` + se vacía la cola
  (`source.stop()` en todos) y se marca `interrupted` en la métrica del turno.
- Transcripción: `inText` va al panel del alumno, `outText` al del examinador, ambos con
  timestamp relativo a la sesión. Esto es **"exactamente lo que digo"**.

## D — Part 1 y Part 2 (el script del examinador)

En `prompts.py` (o un nuevo `speaking_prompts.py`), el system prompt del examinador:

- Rol: interlocutor Cambridge B2 First. **Solo inglés.** Habla poco: preguntas cortas.
- Part 1: banco de preguntas reales del examen (nombre, dónde vivís, estudios, tiempo libre,
  viajes, tecnología) — 8 preguntas, elige y sigue el orden, no repite.
- Part 2: describe la tarea de comparar dos fotos, 1 minuto, con la instrucción exacta de
  Cambridge; después pide la respuesta corta del compañero (que en S3 no existe: dice
  "your partner will answer in a moment" y continúa).
- **Nunca corrige durante el examen** (eso es del reporte de S5, no del examinador en vivo).
- El transcript del alumno es **texto no confiable**: va con el mismo fence de la fase 17 si
  alguna vez se le pasa al LLM de texto. En vivo no se le pasa: el modelo lo escucha.

## E — Verificación (`tests/test_speaking_live.py`), sin key, con `sim`

Asserts (≥ 10):

1. `/api/speaking/token` sin key → 503 `speech_not_configured`; con key falsa apuntando a un stub
   local → 200 con `{token, ws_url, expires_in}` y **sin** la key en el body.
2. Sin `Authorization` → 401; 11 tokens en un minuto → 429.
3. Con `?spk=sim`, 3 turnos completos, cero errores de consola, transcripción de ambos lados
   visible y con timestamps crecientes.
4. Barge-in: simular habla local durante el turno del examinador → la cola de audio se vacía y
   `interrupted: true` aparece en el turno.
5. Cuota: `POST /api/speaking/minute` acumula; al pasar el cap el cliente cierra y muestra el
   mensaje. Reiniciar el server conserva el consumo (leer `speaking.json`).
6. El panel sigue funcionando si se abre y cierra 3 veces (no leaks de `AudioContext`:
   `ctx.state === 'closed'` después de cerrar).
7. Las suites existentes siguen verdes (`test_sync.py`, `test_final.py` si el servicio está vivo).

## F — Cierre

- Un commit `feat(speaking): live examiner with ephemeral token and sim transport`.
- `CSP connect-src` debe incluir **explícitamente** el host WSS de Google (una línea, comentada
  con el motivo). Ese cambio tiene que estar en el mismo commit.
- `docs/PRIVACY.md`: qué recibe Google, que el audio no pasa por nuestro servidor, retención.
- `node --check` verde y `GET /` = 200 al terminar.
