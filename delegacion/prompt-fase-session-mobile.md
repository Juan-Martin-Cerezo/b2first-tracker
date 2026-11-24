# Fase session-mobile — la sesión se explica sola y se usa con el dedo

Repo: `/home/juan/b2first-tracker`, base HEAD `5bf9064`.

## Pedido del dueño

La sesión en desktop es intuitiva; en mobile no. Tiene que:
1. **Adaptarse bien a mobile** (390×844): nada de apretar controles microscópicos, nada de scroll horizontal, tabs Session/Contents siempre alcanzables, timer visible y botones ≥44 px.
2. **Explicar el flujo**: “Abrí el ejercicio en Contents, iniciá el tiempo y en Phase 2 registrá tus resultados.” Hoy hay que adivinarlo.

## Rediseño de sesión (mobile-first)

### A. Coach de 3 pasos (nuevo)
Dentro de `#sessionTabSession`, arriba del studio visible, insertar `#sessionCoach` (card compacta, no modal, no wizard). Tres filas numeradas con estado pendiente/hecho y un botón por fila:

1. **“1 · Abrí el ejercicio en Contents”**
   - Botón: “Abrir Contents” → `setSessionTab('contents')` (misma pestaña real, sin duplicar).
   - Se marca hecho cuando el usuario entra a Contents al menos una vez en esa sesión (`SESSION_COACH.contents=true`).
   - Al volver de Contents, un check ✓ y texto “Ejercicio abierto”.
2. **“2 · Iniciá el tiempo”**
   - Botón: “Iniciar timer” → arranca el timer de la destreza abierta:
     - rue: `ueTimer.start()` (toggle: si corre, “Pausar”).
     - l: `lTimer.start()`.
     - w: `wPlan.start()` en Phase 1 o `wWrite.start()` en Phase 2, según fase actual.
     - sp: “Empezar speaking” → `spStartExam()` (el speaking no tiene timer propio).
   - Se marca hecho cuando el timer arrancó (o el speaking empezó).
   - El texto del timer en vivo (`mm:ss`) aparece en la fila, no hace falta scrollear al task.
3. **“3 · En Phase 2 registrá tus resultados”**
   - Botón: “Ir a Phase 2” → `switchUePhase('score')` / `switchListeningPhase('pm')` / `switchWritingPhase('audit')` según destreza; para speaking: “Ver reporte” (si ya terminó) o “Terminar y guardar”.
   - Copy específico por destreza:
     - RUE: “Cargá correctas, total y minutos, y guardá.”
     - Listening: “Cargá correctas y minutos en el post-mortem, y guardá.”
     - Writing: “Revisá tu texto con Check with AI (Phase 3).”
     - Speaking: “Terminá las partes; el reporte se guarda solo.”
   - Se marca hecho cuando se guardó un resultado en esa sesión (`saveUE`/`saveL`/`log` de esa unidad o reporte de speaking). Basta con escuchar el evento de guardado existente; no crear un segundo guardado.

Comportamiento: el coach se actualiza con la destreza de `SESSION_UNIT.skill`; no aparece en Practice/Exam. En desktop se ve como una franja de 3 columnas compacta; en mobile, 3 filas apiladas. No bloquear nada: es guía, no gate.

### B. Mobile (≤767px)
- `#sessionBar` (título + tabs Session/Contents) **sticky** debajo del topbar de la app, con fondo opaco y borde; siempre visible al scrollear. Tabs ocupan todo el ancho, 50/50, altura ≥48 px.
- `#sessionCoach`: texto 14 px mínimo, botones full-width ≥44 px, numeración visible. El paso activo resaltado; los hechos con ✓ y color ok.
- Timer + botón ▶/⏸: en mobile el `task-head` se apila; el timer va en una fila propia, tipografía ≥20 px, botón ≥44×44. Nada de `flex` que comprima el título a 3 líneas.
- `.phase-stepper`: en mobile 2 columnas iguales (o 1 si hay 3 fases en Writing), targets ≥44 px, texto sin cortar.
- `.row` de inputs: 1 columna en mobile; inputs full-width, altura ≥44 px. Los grupos de 3–4 inputs no pueden quedar en 3 columnas de 90 px.
- Botones primarios de guardado (`saveUE`, `saveL`, Check with AI, Start/End de speaking): full-width en mobile, ≥48 px, y visibles sin zoom.
- `overflow-x:hidden` no como parche: medir `scrollWidth <= clientWidth` en 390 y arreglar el elemento que desborde.
- El FAB “+ Log session” no debe tapar el coach, el timer ni el botón de guardar; si molesta dentro de session, ocultarlo mientras `#v-hoy.is-session-focus`.

### C. Desktop
- No romper la vista actual: coach en 3 columnas, sticky bar sólo si no genera saltos. Tabs y timers como hoy.

## Alcance

- `index.html`, tests, capturas. Sin backend, sin límites, sin speaking logic (sólo enganchar su start/reporte), sin deploy.
- Sin handlers inline, i18n EN/ES simétrico, dark/light, targets ≥44 px.

## Tests

Crear `tests/test_session_mobile.py`:
1. Abrir sesión de RUE desde Practice Start a 390×844. `#sessionCoach` visible con 3 pasos; texto “Abrí el ejercicio en Contents”, “Iniciá el tiempo”, “Phase 2”.
2. Paso 1 abre Contents (tab activo `contents`), al volver el paso queda ✓.
3. Paso 2 arranca el timer: `#ueTimer` cambia en 2 s; el botón pasa a Pausar; el valor se ve en el coach.
4. Paso 3 lleva a Phase 2 (`#uePhase2` visible) y el botón de guardar está a la vista y ≥44 px.
5. `#sessionBar` sticky: tras `window.scrollTo(0, 900)`, su `getBoundingClientRect().top` sigue dentro del viewport.
6. 390×844: `scrollWidth <= clientWidth`, todos los inputs y botones ≥44 px de alto, 0 solapamiento del FAB con coach/timer/guardar.
7. Repetir 1–4 para Listening y Writing (copy y acciones correctas).
8. 1280×800: coach en 3 columnas, tabs y timer intactos, sin overflow.
9. EN/ES simétrico; sin errores de consola.

Actualizar `test_start_contents.py`, `test_mobile.py`, `test_ui_batch2.py`, `test_i18n.py` si el coach o los tabs cambian selectores. Verificación obligatoria:

```bash
cd /home/juan/b2first-tracker/tests
for f in test_session_mobile.py test_start_contents.py test_mobile.py test_ui_batch2.py test_i18n.py test_index_handlers_exist.py test_practice_flow.py test_speaking_turns.py; do
  uv run --no-project --quiet --with playwright --with httpx python "$f" || echo "FAIL $f"
done
```

Capturas: `tests/out/session_coach_390_light.png`, `session_coach_390_dark.png`, `session_phase2_390_light.png`, `session_coach_1280_light.png`.

## Cierre

Un commit: `feat(session): coach de 3 pasos y sesión usable en mobile`. Sin deploy.
