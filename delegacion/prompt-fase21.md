# PROMPT — Fase 21: examinador + compañero hablando a la vez (S4)

Sos ingeniero senior de sistemas de audio en tiempo real. Repo `/home/juan/b2first-tracker`.
**CODIFICAR.** Inglés en código/commits. Leé `docs/SPEAKING-REALTIME-PLAN.md` §4 **entero**: el
"patrón director" es esta fase. Es la fase que Juan pidió explícitamente.

## El problema real

Dos sesiones Live independientes escuchan el **mismo micrófono** y ninguna escucha a la otra. Si
las dejás libres, se pisan a los 20 segundos. La solución no es prompt engineering: es un
**director** del lado del cliente que decide de quién es el turno, mutea al otro a nivel de audio
y, cuando el compañero necesita saber qué dijo el examinador, se lo pasa **como texto** por
`sendText()`.

## A — Director (`spkDirector`), máquina de estados pura

Escribilo como función pura, sin DOM y sin red, para poder testearla sin audio:

```js
// input: {part, t, examiner:{speaking,since}, partner:{speaking,since},
//         candidate:{speaking,silenceMs}, transcriptTail}
// output: {examiner:{live,muted}, partner:{live,muted}, events:[{t,type,who,text}]}
function spkDirectorTick(state, input) -> {state, out}
```

Reglas exactas (implementá estas, no otras):

| Parte | Regla |
| --- | --- |
| 1 | Solo examinador. Partner **no se abre** (ahorro). |
| 2 | Alternancia estricta: examinador pregunta → candidato 60 s → partner 30 s → examinador cierra. Mute duro del que no le toca. El paso a "candidate" ocurre cuando el examinador terminó su turno **y** el candidato habló ≥ 500 ms. Timeout: si el candidato no habla en 3 s, el examinador repite la instrucción una vez. |
| 3 | **Ambos vivos.** El examinador **introduce y se calla**; el partner hace las preguntas del prompt escrito. El examinador vuelve **solo** si hay **≥ 2 s de silencio de ambos** o si el candidato lo direcciona por nombre. Acá sí se permite overlap y se **mide**: `overlap_ms` por turno. |
| 4 | Ambos vivos. Turno por dirección: si el hablante anterior fue examinador y la pregunta contiene `your partner` → partner; si contiene `you` → candidato. Default: partner. |

- Mute = `gain.gain.setTargetAtTime(0, ctx.currentTime, 0.01)` **y** `transport.mute(true)`.
  Nunca cerrar el socket para mutear (cuesta 1 s + un token nuevo).
- Cerrar/reabrir sesiones **solo** en los bordes de parte.

## B — Mezcla de dos voces

- Un solo `AudioContext`, **dos cadenas independientes**: `sessionA.source → gainA → destination`,
  `sessionB.source → gainB → destination`. Sin `MediaStreamDestination` extra.
- Compensación de volumen: si las dos hablan a la vez, bajá **5 dB** la que **no** fue
  direccionada (ducking suave, `setTargetAtTime`, 50 ms), y registralo en `overlap_ms`. Sin
  compresión, sin efectos: es un examen, no un podcast.
- Panel: un indicador por voz (`Examiner`, `Partner`) con estado `speaking / muted / offline`.
  Si una sesión se cae, el badge dice `offline` y la otra sigue — **una sesión caída nunca debe
  matar la sesión completa** (fail-safe del plan §4).

## C — Prompt del compañero

`speaking_prompts.py`: el partner es otro **candidato B2**, no un examinador. Personalidad:
amable, algo tímido, comete errores normales de B2 (no perfecto), **una pregunta corta por turno**,
nunca corrige, nunca hace de profesor. En Part 3 trabaja el prompt escrito (preguntas del cuaderno
de Cambridge) y **no puede** terminar la tarea solo: siempre devuelve la pelota
("What do you think?", "Shall we go with that?"). En Part 2 responde en 30 s sobre las fotos del
candidato.

## D — Verificación (`tests/test_speaking_director.py` + `tests/test_speaking_duo.py`)

Todo con `?spk=sim`. Sin red, sin key.

**Director (puro, ≥ 14 asserts, sin browser):** Part 1 no abre partner · Part 2 mutea partner
hasta que el candidato habla 500 ms · timeout de 3 s repite la instrucción una sola vez · Part 3
examinador callado con partner preguntando · Part 3 examinador vuelve a los 2 s de silencio de
ambos · Part 4 direcciona por `your partner` · un `t` que retrocede no rompe el estado · la misma
entrada dos veces produce la misma salida (idempotencia).

**Duo (Playwright, ≥ 8 asserts):** Part 3 con dos sesiones sim → ambas voces producen audio,
`overlap_ms > 0` y aparece en el panel, se cierran las dos al terminar · matar la sesión del
partner a mitad → el panel muestra `offline`, la sesión sigue, el cierre es limpio · 3 ciclos
abrir/cerrar sin leaks de `AudioContext` · cero errores de consola · el contador de minutos suma
las **dos** sesiones.

## E — Cierre

- Un commit `feat(speaking): examiner + partner duo with turn director`.
- `HANDOFF.md` §12.2: una línea con S4 hecho.
- `node --check` verde, `GET /` = 200, y las suites existentes (`test_sync.py`) verdes.
