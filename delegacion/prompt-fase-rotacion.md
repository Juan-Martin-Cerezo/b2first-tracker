# Fase rotación — la rotación nunca se reinicia al cambiar de semana

Repo: `/home/juan/b2first-tracker`. Base: HEAD `a739ac9` (hay cambios sin commitear de la fase speaking-turn: NO los toques ni los commitees; trabajá solo sobre `index.html` y tests nuevos).

Reporte de Juan: "ya sea que elijas by part o by paper, siempre se tiene que rotar. Si elegís by paper y ponés 3 días: día 1 full Reading, día 2 full Listening, día 3 full Writing, y el día 4 NO vuelve a Reading, completa con Speaking. Lo mismo si es by part."

## Comportamiento actual (bug)

En `index.html`:

1. `weekSkillAt(weekIndex, dayIndex)` (`~15458`) devuelve `WEEK_SKILL_PAIRS[weekIndex % 2][dayIndex % 2]`. Con 3 días por semana: día 1 `rue`, día 2 `l`, día 3 `rue` otra vez. La semana siguiente vuelve a empezar la pareja `rue/l` o `w/sp`. Resultado: nunca se pasa a Writing/Speaking en una racha de 3 días.
2. `buildWeeklyPlan` en modo `full-section` (~16166) usa `FULL_SECTION[i % FULL_SECTION.length]` con `i` reiniciado en 0 cada semana. Con 3 días: semana 1 = Reading, Listening, Writing; semana 2 vuelve a Reading. Debe seguir con Speaking, Reading, Listening.

## Semántica pedida

Una sola secuencia continua de sesiones, sin reinicio semanal, compartida por PLAN, TODAY y "What comes next":

- `by-part`: las sesiones ciclan por `QUEUE_SKILLS = ['rue','l','w','sp']` en ese orden, tomando el índice global de sesión. Con 3 días: s1 rue, s2 l, s3 w, s4 sp, s5 rue, s6 l...
- `full-section`: las sesiones ciclan por `FULL_SECTION = [ue, l, w, sp]` con el mismo criterio. Con 3 días: s1 Full R&UE, s2 Full Listening, s3 Full Writing, s4 Full Speaking, s5 Full R&UE...
- El índice global se deriva del historial (sesiones ya registradas en el log) más `D.sessionOffset`, igual que hoy hace `queueStartSession`. Nunca de un cursor guardado que un refresh pueda mover.
- El ítem/parte dentro de cada skill sigue avanzando con la ocurrencia de esa skill (lo que ya hace `queueBlockUnit`/`sessionOccurrence`).
- `itemsPerSession` sigue aplicando en by-part: 2 unidades de la misma skill por sesión, continuando la ocurrencia.

## Qué cambiar

- `index.html`:
  - `sessionSkillFor` para que use `QUEUE_SKILLS[queueMod(sessionIndex, 4)]` (adiós a las parejas semanales).
  - `buildWeeklyPlan`, rama `full-section`: tomar como base el mismo índice global (sesiones ya hechas + offset) en vez de `i` local, y ciclar `FULL_SECTION` con ese índice.
  - Revisar `planNextSessions`, `planUpcomingRows`, `planWeekBlockLine`, `paintSessionStudios` y cualquier uso de `weekSkillAt`/`weekPairFor` para que muestren la misma secuencia. Si `weekPairFor` queda sin uso, borrala junto con `WEEK_SKILL_PAIRS`.
  - Mantener `sessionOffset` y el botón de reset funcionando.
- Tests: nuevo `tests/test_plan_rotation_continuous.py`, en el patrón de `tests/test_plan.py`, con números, no capturas de opinión:
  1. by-part, 3 días: `buildWeeklyPlan` con log vacío y con log simulado de 3 sesiones ya hechas debe dar, respectivamente, `['rue','l','w']` y `['sp','rue','l']` (leyendo `WEEK_PLAN.slots[].type`/`skill` en el navegador).
  2. full-section, 3 días: `['ue','l','w']` y, con 3 sesiones registradas, `['sp','ue','l']`.
  3. by-part, 2 días: `['rue','l']` y con 2 hechas `['w','sp']`.
  4. "What comes next" muestra la misma secuencia que el plan (comparar los próximos 3 tipos).
  - No borrar ni debilitar tests existentes; si alguno asume parejas semanales, se actualiza al contrato nuevo.

## Reglas

- No tocar `server.py`, `plans.py`, speaking, CSP, límites ni onboarding.
- No commitear los cambios pendientes de la fase anterior: `git status` ya muestra `M server.py`, `M tests/test_speaking_exam.py`, `?? tests/test_speaking_turn_budget.py`, `?? tools/speaking_smoke.py`. Commit SOLO `index.html` + el test nuevo (y los tests que ajustes).
- Mobile 390×844 sin overflow en la vista Plan.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_plan_rotation_continuous.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_plan.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_plan_today_match.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_edit_intake_plan.py; echo exit=$?
```

Los cuatro exit=0. Captura de la vista Plan en 390×844 y 1280×800 después de 4 sesiones simuladas, mostrando que la cuarta es Speaking.

## Cierre

Commit `fix(plan): rotación continua entre semanas en by-part y full-section`. Sin deploy.
