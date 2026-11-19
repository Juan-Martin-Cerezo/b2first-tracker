# Fase speaking-turn — arreglar el turno y probarlo con habla real

Repo: `/home/juan/b2first-tracker`. Base: HEAD `ab7fd53`.

El modo por turnos de Speaking está roto en producción: `POST /api/speaking/turn` devuelve 502 `{"error":"turn_failed","reason":"upstream_failed"}` con un WAV válido de 19 s. La key y el modelo funcionan: llamando a `gemini-2.5-flash` a mano con el mismo audio, el modelo devuelve transcript y reply correctos.

Causa diagnosticada: en `_spk_turn_understand_locked` (`server.py` ~1610-1645) el payload pide `maxOutputTokens: 60` con `responseSchema` de dos campos. El transcript completo (~40-60 tokens) más el JSON no entran: Gemini devuelve `finishReason: MAX_TOKENS` y un JSON truncado, `json.loads` falla y el server lo convierte en `upstream_failed`. Reproducido a mano: con 60 tokens la respuesta se corta; con más presupuesto devuelve JSON válido.

## Qué cambiar

1. `server.py`, `_spk_turn_understand_locked`:
   - Subir `maxOutputTokens` a 320 (transcript de 25 s + reply de 8-14 palabras entran con aire). Dejar `thinkingConfig.thinkingBudget: 0`.
   - Mantener `responseSchema`.
   - Si `finishReason == "MAX_TOKENS"` o el JSON no parsea, devolver error explícito `turn_truncated` en vez de `upstream_failed`, para que el cliente pueda reintentar mostrando "repeat that".
   - No tocar timeout, gate de minutos, rate limits ni la ruta.
2. `tests/test_speaking_turn_budget.py` (nuevo, offline): arranca el server aislado con un proveedor stub y verifica que el payload que sale hacia Gemini lleva `maxOutputTokens >= 300`, `thinkingBudget == 0` y `responseSchema` con `transcript` y `reply`; y que un cuerpo truncado (`finishReason: MAX_TOKENS`) se mapea a `turn_truncated`, no a 502 genérico. Usar el patrón de stub de `tests/test_speaking_v2.py`.
3. `tools/speaking_smoke.py` (nuevo): script manual que toma `--url`, `--user`, `--password`, `--wav` y `--part`, manda el WAV como `audio_b64` a `/api/speaking/turn` (`tts:"none"`, `session_id` nuevo) e imprime en JSON: `http`, `ms`, `transcript`, `reply`, `finish_reason` si viene. Sirve para probar con habla real sin micrófono. Sin dependencias fuera de stdlib.
4. Fixture local: `tests/fixtures/candidate_b2.wav` existe en el disco pero `tests/fixtures/` está en `.gitignore`, así que NO se commitea. Ningún test automático debe depender de ese archivo: el test offline usa el stub, y `tools/speaking_smoke.py` recibe el WAV por `--wav`.

## Reglas

- No tocar los prompts de examinador (`speaking_prompts.py`) en esta fase; el foco es que el turno funcione.
- No tocar Live, report, PA, límites ni onboarding.
- Nada de claves en logs ni en el repo.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_speaking_turn_budget.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_v2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_dialogue.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_exam.py; echo exit=$?
```

Los cuatro exit=0.

Después del commit y sin deploy, dejá el service sin reiniciar: yo reinicio y corro `tools/speaking_smoke.py` contra producción con el WAV real en las 4 partes.

## Cierre

Commit `fix(speaking): turno con presupuesto de salida suficiente y error de truncado`. Árbol limpio. Sin deploy.
