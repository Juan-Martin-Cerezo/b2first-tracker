# PROMPT — Fase 19: pronunciación real con Azure (S2)

Sos ingeniero senior backend Python stdlib + audio. Repo `/home/juan/b2first-tracker`. **CODIFICAR.**
Inglés en código/commits. Leé `docs/SPEAKING-REALTIME-PLAN.md` §3 y §8-S2. Es la especificación.

## Contexto

La escala **Pronunciation** del B2 First no se puede adivinar desde un transcript: necesita
fonemas. La única fuente permitida es **Azure Speech Pronunciation Assessment** (verificado:
`Granularity.Phoneme`, `EnableProsodyAssessment`, `en-US`, streaming continuo). El LLM **nunca**
inventa esa banda (regla del plan, §3).

## A — Configuración

- Nuevas env vars, leídas en `server.py` como las demás:
  `B2_SPK_AZURE_KEY`, `B2_SPK_AZURE_REGION` (ej. `eastus`), opcional `B2_SPK_AZURE_ENDPOINT`.
- **Si falta la key**: el endpoint responde **503 `{"error":"speech_not_configured"}`** con
  `Retry-After` ausente y **un log de una línea sin la key**. Nunca crash, nunca 500.
- La key **nunca** llega al browser y **nunca** se loguea ni aparece en un commit. Agregá la
  variable al ejemplo de `HANDOFF.md` §4 (solo el nombre).

## B — Endpoint `POST /api/speaking/pa`

Request JSON (no multipart, para no escribir un parser a mano):

```json
{"audio_b64": "<wav o opus base64>", "format": "wav|ogg", "ref_text": "<opcional>"}
```

- Auth obligatoria (`Authorization: Bearer`), mismo guard que el resto.
- Límites: **10 s de audio** (el cliente manda el turno, no la sesión entera), **2 MB** de base64,
  **30 llamadas/min/usuario**, y una cuota diaria nueva `B2_SPK_PA_DAILY_PER_USER` (default **60**)
  contada con el mismo patrón que `_ai_quota_consumed` / `_ai_quota_left`.
- Validar el header RIFF/`OggS` real del buffer (no confiar en `format`); si no coincide → 422.
- Llamada saliente con `urllib.request` a
  `https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=en-US&format=detailed`
  con headers `Ocp-Apim-Subscription-Key`, `Pronunciation-Assessment: <base64(JSON config)>` y
  `Content-Type: audio/wav; codecs=audio/pcm; samplerate=16000`. Config PA:
  `{ReferenceText:"", GradingSystem:"HundredMark", Granularity:"Phoneme", EnableMiscue:true,
  EnableProsodyAssessment:true, Dimension:"Comprehensive"}`.
  Timeout **8 s**, sin reintentos silenciosos (un reintento duplica el costo: si falla, 502).
- **El audio se descarta en la misma función.** No se escribe a disco, no se guarda en `data/`,
  no entra al audit log. Solo se persiste (si el usuario lo pidió en S5) el resultado numérico.

Respuesta normalizada (esto es contrato, no cambies los nombres):

```json
{"ok":true,
 "accuracy":87.5,"fluency":81.0,"completeness":100,"prosody":79.2,
 "words":[{"w":"thought","err":"None","score":93,"phonemes":[{"p":"th","score":71}]}],
 "worst":[{"w":"thought","score":41,"phonemes":[...]}],
 "duration_s":9.4,"provider":"azure"}
```

`worst` = hasta 5 palabras ordenadas por score ascendente, excluyendo `err:"Omission"`.

## C — Función pura + test (obligatorio)

Separás la parte pura en `speech.py` (nuevo módulo, stdlib, importable sin red):

- `parse_pa_response(azure_json) -> dict` (el contrato de arriba)
- `pa_config_header(ref_text="") -> str`
- `validate_audio(buf, fmt) -> (ok, reason)`

`tests/test_speaking_pa.py` debe, **sin red y sin key**:

1. Levantar un **stub HTTP local** (stdlib `http.server`, puerto libre) que devuelva un JSON de
   Azure realista (2 palabras, una con score 41) y apuntar el endpoint ahí con
   `B2_SPK_AZURE_ENDPOINT` — probás el camino completo HTTP→parseo, sin tocar Azure.
2. Asserts (≥ 10): contrato completo, `worst` ordenado, `Omission` excluida, phonemes presentes,
   base64 > 2 MB → 413, audio de 15 s declarado → 422, sin `Authorization` → 401, header RIFF
   inválido → 422, rate limit 30/min → 429 al intento 31, sin key configurada → 503
   `speech_not_configured`, y **el audio no quedó en disco** (glob `data/**/*.wav` vacío).
3. Un test de **no-fuga**: la respuesta y el audit log no contienen la key del stub
   (usá una key falsa tipo `FAKEKEY123` y grepeá el log).

## D — Cierre

- Servir el mismo patrón que el resto del server (headers, `X-Request-Id`, límites de payload,
  `_send_json`). Nada nuevo de infraestructura.
- `systemctl restart b2first` es seguro y esperado; verificalo con `/api/health`.
- Un commit `feat(speaking): azure pronunciation assessment endpoint`.
- Sección corta nueva en `docs/PRIVACY.md`: qué se manda a Azure, que el audio no se almacena,
  y que el proveedor procesa fuera de Argentina.
