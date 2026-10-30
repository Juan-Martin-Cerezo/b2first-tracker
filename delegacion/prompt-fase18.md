# PROMPT — Fase 18: captura de micrófono + VAD + HUD en vivo (S1)

Sos ingeniero senior front-end + audio web. Repo `/home/juan/b2first-tracker`. **CODIFICAR.**
Código, comentarios, UI y commits en **inglés**. Docs internas pueden ser español.

Leé primero `docs/SPEAKING-REALTIME-PLAN.md` (§3, §4, §8-S1). Es la especificación. No inventes
otra arquitectura.

## Reglas duras del proyecto

- **Sin dependencias nuevas.** Cero npm, cero pip, cero CDN. `index.html` sigue siendo un archivo
  vanilla HTML+CSS+JS. Backend `server.py` stdlib only (en esta fase no se toca el backend).
- **Sin datos inventados.** Si algo no se puede medir sin API, no lo muestres.
- No toques `data/` real. No toques `saveSP()` ni el flujo de guardado existente.

## A — Captura y análisis (todo cliente, sin red)

En `index.html`, dentro del bloque SPEAKING STUDIO:

1. Botón **"Live studio"** que abre un panel nuevo (`#livePanel`) sin romper el timer existente.
2. `getUserMedia({audio:{echoCancellation:false, noiseSuppression:false, autoGainControl:false}})`
   — los tres en `false` a propósito: el VAD y la futura evaluación de pronunciación necesitan la
   señal cruda. Documentá ese motivo en un comentario.
3. `AudioContext` a **16000 Hz** (si el browser ignora el sampleRate, resampleá con un
   `OfflineAudioContext` antes de mandar; en esta fase solo importa el análisis).
4. `AudioWorkletProcessor` (`spkVad`, definido con `Blob`+`URL.createObjectURL` para no agregar
   archivos) que emite cada **20 ms**: `{rms, peak, zcr, speaking}`.
5. VAD por histéresis sobre RMS con umbral adaptativo:

   - calibración: primeros **500 ms** de silencio → `noiseFloor = mediana(rms)`;
   - `umbral_on  = noiseFloor * 3.0 + 0.004`, `umbral_off = umbral_on * 0.6`;
   - `speaking` pasa a `true` tras **3 frames** consecutivos sobre `umbral_on` y a `false` tras
     **8 frames** consecutivos bajo `umbral_off` (anti-flicker);
   - un silencio se **registra** solo si dura ≥ **300 ms**: `{start, dur}` en la línea de tiempo.

6. Estado en vivo, actualizado en `requestAnimationFrame` (nunca dentro del worklet):

   - `elapsed` (mm:ss), `speech ratio` (%), **cantidad de silencios**, **silencio más largo**,
   - **timeline** de la sesión: barra horizontal donde el silencio se pinta distinto del habla
     (un div por tramo, sin canvas: tiene que ser inspeccionable en tests).
   - **alerta visual** cuando un silencio supera **2.0 s** ("long pause") y otra a los **5 s**
     ("frozen?") — texto, no solo color (`aria-live="polite"`), porque el color solo no es
     accesible.

7. "Stop" congela el HUD, calcula el resumen y **no guarda nada** todavía (eso es S5). Un botón
   "Discard" limpia el panel.

## B — Verificación (obligatoria, en `tests/test_speaking_metrics.py`)

Playwright con dispositivo falso:
`--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<wav> --use-fake-ui-for-media-stream`.

Generá el WAV **dentro del test** con `wave` + `math` (stdlib, sin fixtures binarios en el repo):
patrón de 90 s = habla simulada (ruido de banda + tono, amplitud media) separada por silencios
de duración **conocida**: 1.2 s, 2.5 s y 4.4 s, en posiciones fijas.

Asserts (≥ 8):

1. El panel abre y pide permiso sin errores de consola.
2. Silencios detectados = **3**.
3. Cada duración detectada cae dentro de **±0.25 s** de la real.
4. `silencio más largo` = 4.4 ± 0.25 s.
5. Ningún silencio < 300 ms aparece en la lista.
6. La alerta "long pause" aparece con el de 2.5 s y "frozen?" con el de 4.4 s.
7. `speech ratio` entre 45 % y 85 %.
8. El frame time medido (Medición con `performance.now()` en 60 frames) es **< 16 ms**: el HUD no
   puede bloquear el main thread.
9. Cero dependencias agregadas (`git diff --stat` no toca package.json porque no existe).

## C — Cierre

- `git commit` chico y descriptivo. Un commit, conventional (`feat(speaking): ...`).
- Actualizá `agents.md` (sección de estructura del script) con el bloque nuevo y `HANDOFF.md`
  §12.2 con una línea: `S1 (voice -> VAD -> HUD) shipped in phase 18, see docs/SPEAKING-REALTIME-PLAN.md`.
- `node --check` sobre el JS extraído debe pasar; el servicio en :8088 debe seguir dando 200.
