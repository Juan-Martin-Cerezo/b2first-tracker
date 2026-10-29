# PROMPT — Fase 9 (REEMPLAZA al anterior): onboarding como intake + plan + tour

Sos un ingeniero senior de producto. Repo `/home/juan/b2first-tracker`. **Este turno es para
CODIFICAR.** Todo en inglés.

> Si el árbol ya trae un `onboard*` de un intento previo (welcome card + coach marks sueltos),
> **partí de eso y amplialo**, no lo descartes. Lo que falta es la parte de intake.

## El objetivo, en palabras del usuario

> "El onboarding es para evaluar lo que quiere el usuario y hacer su plan, y mostrarle las
> funciones de la web."

Es decir: no es un tour. Es **un cuestionario de 6 pasos que produce un plan real**, y recién
al final muestra cómo se usa la app. El que llega nuevo sale con: fecha de examen, meta,
horas por semana, debilidades declaradas **y un plan de 5 sesiones ya armado**.

## Tarea A — Wizard de intake (6 pasos, una cosa por pantalla)

Card centrada, `role="dialog"`, `aria-modal`, focus trap, barra de progreso fina `1/6`, botones
`Back` / `Continue`, `Skip for now` siempre visible. `Entrar/avanzar` también con `Enter`.

Paso 1 — qué es esto (3 líneas + `Start`):
```
Title: Build your B2 First in two habits
Body:  It tells you which exam parts are weak, and it makes every practice session
       cost 15 seconds to log.
```

Paso 2 — **fecha y meta**:
- `Exam date` → `<input type="date">`, min = hoy. Guardá ISO (`YYYY-MM-DD`).
- `Target grade` → 3 opciones tipo radio-card: `A (C1 level)` · `B (solid B2)` · `C (pass)`

Paso 3 — **nivel actual por skill** (esto es lo que "evalúa lo que quiere el usuario"):
- 4 filas: `Reading & Use of English`, `Writing`, `Listening`, `Speaking`
- Cada una: 5 botones `1..5` con labels `1 = starting`, `5 = confident`. Default `3`.
- Debajo, link: `Not sure? Take the 10-minute diagnostic instead` → salta al paso 5.

Paso 4 — **tiempo disponible**:
- `Hours per week` → slider o chips `2 / 4 / 6 / 10+`
- `Days you can study` → chips `Mon..Sun`, multi-select, default `Mon, Wed, Sat`

Paso 5 — **qué te cuesta** (multi-select, máx 3):
```
Vocabulary · Grammar accuracy · Reading speed · Listening speed · Writing structure · Speaking fluency
```
Mapeo interno a la taxonomía existente: `Vocabulary→L-GAP`, `Grammar accuracy→G-ERR`,
`Reading speed`/`Listening speed→T-MIS`, `Writing structure→G-ERR`, `Speaking fluency→L-GAP`.
Guardá lo declarado Y el mapeo.

Paso 6 — **resultado**: preview del plan generado (las 5 filas reales, con su `reason`), y dos CTA:
`Start the diagnostic` (primario) y `Go to Today`.

- `Esc`, backdrop o `Skip for now` → cierra, marca `onboarded: true`, y **no** genera plan inventado.
- Al terminar los 6 pasos → `onboarded: true` y **tour de 3 coach marks** (nav → FAB quick-log →
  botón del diagnóstico), anclados con `getBoundingClientRect()`, reposicionando en
  `resize`/`scroll`, y **salteando el paso si el target no está visible**.
- En modo demo (`config.demo`) el paso 1 agrega: *"This is the demo: nothing is stored on the server."*

## Tarea B — `D.profile` (nuevo, persistido y sincronizado)

```js
D.profile = {
  examDate: "2027-06-12",      // ISO o null
  targetGrade: "A"|"B"|"C",
  skills: { rue: 3, w: 2, l: 3, sp: 2 },   // 1..5
  hoursWeek: 6,
  days: ["mon","wed","sat"],
  struggles: ["L-GAP","G-ERR"],   // taxonomía mapeada, deduplicada
  declaredAt: "2026-10-30T..."    // ISO
}
```

- Se guarda en `D.profile` → viaja en el progreso (localStorage + `/api/progress`).
- **`examDate` reemplaza cualquier fecha hardcodeada del countdown** de Today: si existe, la usa;
  si no, muestra `Set your exam date` con link al wizard.
- En `Plan → Settings`: `Edit my intake` (reabre el wizard con los valores actuales cargados) y
  `Show the walkthrough again` (relanza los coach marks).

## Tarea C — El plan usa el intake (esto es lo que lo hace útil)

`buildWeeklyPlan()` (fase 6) hoy sólo mira diagnóstico + errores + `weekGoal`. Ahora, en este orden
de prioridad:

1. Si hay diagnóstico → las 3 partes más débiles (como hoy).
2. Si **no** hay diagnóstico → usar `D.profile.skills`: las 2 skills más bajas definen los slots
   (`w` → Writing, `l` → Listening, `rue` → Reading & UoE, `sp` → Speaking).
3. Nº de slots por semana = `D.profile.hoursWeek`: 2h→3 slots, 4h→4, 6h→5, 10+→6.
4. Los días de los slots salen de `D.profile.days` (no de una lista fija).
5. `struggles` agrega 1 slot de refuerzo con el tipo que corresponda según el mapeo.
6. Los `reason` en inglés, citando el dato real: *"you rated Writing 2/5"*,
   *"you flagged reading speed"*, *"part 3 was weakest in the diagnostic"*.

Sin `D.profile` y sin diagnóstico: comportamiento actual (no romper `test_plan.py`, actualizalo si
los `reason` cambian).

## Tarea D — Empty states (acompañan al intake)

- **Today** sin sesiones → *"Nothing logged yet. Your first session takes 15 seconds."* + `Quick log`
- **Charts** sin datos → *"Charts appear after your first session."* + `Quick log`
- **Errors** vacío → *"No errors logged. Tag a miss after a practice test."*
- **Today** sin `examDate` → chip `Set your exam date`

## Tarea E — Accesibilidad (no negociable)

`role="dialog"`, `aria-modal`, `aria-labelledby`, focus trap, foco inicial en el primer control,
foco devuelto al abridor al cerrar, `Esc` cierra, `prefers-reduced-motion` sin transición.
Los chips son `<button type="button" aria-pressed="true|false">`. Los radio-cards son `<input type="radio">` reales.

## Tarea F — `tests/test_onboard.py` (≥14 asserts)

Server propio, `DATA_DIR` temporal (patrón `test_sync.py`). Asserts:

1. primera visita → wizard visible, paso `1/6`
2. foco inicial dentro del diálogo
3. `Continue` avanza a `2/6`; `Back` vuelve a `1/6`
4. completar los 6 pasos → `D.profile` tiene los 6 campos y `onboarded === true`
5. recargar → el wizard **no** aparece
6. `Esc` cierra y marca `onboarded` sin crear `D.profile` vacío incoherente
7. `hoursWeek = 2` → el plan genera 3 slots; `10+` → 6 slots
8. días elegidos (`mon`,`fri`) → los slots caen sólo en esos días
9. sin diagnóstico, `skills.w = 1` → Writing aparece en el plan con `reason` que dice `2/5` o similar
10. `struggles: ["G-ERR"]` → hay un slot de gramática con su `reason`
11. countdown de Today usa `examDate` del perfil
12. `Edit my intake` reabre con valores precargados (verificar 2 inputs)
13. `Show the walkthrough again` relanza los coach marks sin recargar
14. coach mark se saltea si el target no es visible
15. `errores_js` vacío en todo el recorrido

## Prohibido

- Dependencias nuevas. Bloquear la app si se saltea. Mostrarlo en cada visita.
- Tocar auth, corrector de IA, racha o sync (salvo lo mínimo de `D.profile` en el payload).
- `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
cd tests && uv run --with playwright python test_onboard.py 2>&1 | tail -20
cd tests && uv run --with playwright python test_plan.py 2>&1 | tail -6
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -4
```

## Commit

```
feat(onboarding): intake wizard that builds the weekly plan, plus feature tour
```

Respondé al final **sólo** con: archivos tocados, salida literal de los comandos, hash.
