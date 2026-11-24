# Fase practice-real — práctica real, sin materiales de relleno ni repetición

Repo: `/home/juan/b2first-tracker`, base HEAD `34971f6`.

## Pedido del dueño

1. Sacar el cuadrado **“Last speaking exam”** de Today.
2. En Exam, el bloque **“📖 Open the exam papers”** tiene que llevar a lo mismo que el botón **“Open materials”** de arriba (Library filtrada al paper, scope full). No otra lista de links.
3. **El contador no arranca automático.** Al elegir un mock (paper o full) se abre un **pop-up** que explica qué mock vas a hacer y cuánto dura, con “Abrir materiales” y “Empezar contador” (este último recién arranca el timer). Cancelar no arranca nada.
4. **Sacar todo lo que sea lesson plans y relleno**: nada de lesson plans, teacher guides, handbooks, “reference”, examiner comments. Solo práctica real: paper, answer key, audio, tapescript, checklist y fuentes online.
5. **Todo se puede marcar como “ya practicado”** para no repetir: partes, recursos de Library y papers del mock. Queda guardado por usuario y se puede ocultar lo hecho.
6. En sesión, **“Materials” y “Contents” son lo mismo**: tocar Materials abre la pestaña Contents; no una lista paralela de chips.
7. **Writing Phase 3**: no hay nada para checkear ni completar a mano. Se elimina el rubric checklist, los contadores manuales y el score manual; queda directo **“Check with AI”**.
8. **Speaking**: elegir 1 parte lleva directo a esa parte (brief + start de esa parte, sin choose intermedio); elegir completo corre las 4 partes seguidas, 1→2→3→4, sin volver al choose.

## Cambios exactos

### 1. Today
- Borrar `#lastSpeaking` del HTML, su render (`renderSpeakingReport`/`spxLastExamEntry` si quedan exclusivos), estilos `#lastSpeaking` y keys i18n exclusivas. Nada de “Last speaking exam”.

### 2. Exam guide
- En `renderEx()`, reemplazar el HTML de `#exGuide` por: un único botón “Abrir materiales” (`data-action="openFullPaperLibrary"`, `data-paper=exPaper`) + el texto de ritmo/estrategia que ya exista para ese paper (sin links sueltos, sin chips, sin “Open the exam papers”).
- El botón tiene que ejecutar exactamente el mismo handler que “Open materials” de la tarjeta (`openFullPaperLibrary`).

### 3. Pop-up de inicio (nuevo)
- Modal reutilizable `#mockStartModal` (overlay existente, `role=dialog`, focus trap, Escape, mobile 390).
- Se abre desde `startRealMock(paper)` (tarjetas Rue/W/L) y desde `beginFullMockSequence()` (pre-flight).
- Copy: “Vas a hacer un mock de **Reading & Use of English** · 75 minutos. Abrí el material y arrancá el contador cuando estés listo.” Para full: “Full mock · 195 minutos escritos + 14 de Speaking, en orden oficial.”
- Botones: “Abrir materiales” (abre la Library filtrada, no cierra el modal necesariamente), “Empezar contador” (cierra y llama `exStart` una sola vez), “Cancelar”.
- `startRealMock` deja de llamar `exStart()` directo. `FULL_MOCK.active` y `exPaper` se setean, pero el timer queda en pausa hasta el botón.
- Al avanzar de paper dentro de un full mock ya iniciado, se mantiene el avance automático (el usuario ya aceptó el mock completo); no volver a pedir confirmación entre papers.

### 4. Solo práctica real
- En `buildExerciseLibrary()` / `buildExerciseLibraryItems()`: excluir `type:'lesson'` y cualquier ítem de guía/handbook/reference/examiner comments. Quedan paper, key, audio, tapescript, checklist y online.
- Quitar el chip/filtro “Reference” de Library y Practice; quitar “lesson plan” de subtítulos, resúmenes (`practice_res_lesson`) y chips de Materials.
- En `buildMatIndex`/`MAT` no hace falta borrar entradas, pero no deben renderizarse en ninguna superficie de práctica.
- Actualizar contador (va a bajar de 187): el test debe comparar contra las filas renderizadas, no contra un número fijo.

### 5. Marcar como practicado
- Nuevo `D.practised = { [key]: 'YYYY-MM-DD' }` (migración suave: si falta, `{}`; no romper progress viejo).
- Key estable por recurso: `lib:<type>|<skill>|<part>|<nombre-o-url>`; por parte: `part:<type>:<n>`; por paper de mock: `mock:<rue|w|l|sp>`.
- En cada fila de Library: botón “Ya lo hice” / “Hecho ✓” que togglea y guarda con `save()`. En cada parte de “Exercises by part”: mismo botón junto a Start.
- Estado visual claro (badge/opacidad) y **orden**: los hechos van al final. Nuevo checkbox en Library “Ocultar hechos” / “Hide done” (default off) que los saca de la lista.
- En el full mock, marcar un paper como hecho guarda `mock:<paper>`; el pre-flight muestra “Hecho” en ese paper y permite desmarcar.
- No borrar del log: marcar es independiente de guardar resultado.

### 6. Materials = Contents
- En las 4 secciones de sesión (Rue, Writing, Listening, Speaking) reemplazar el toggle/panel `wtf-section` por un botón “Abrir Contents” / “Open contents” que ejecute `setSessionTab('contents')` (misma pestaña, mismo library filtrado). Sin chips duplicados, sin panel desplegable.
- Actualizar tests que abren `#wtfToggle*`.

### 7. Writing Phase 3
- Borrar de `#wPhase3`: rubric checklist (`#rubList`, `.rub`, `#rubCount`), inputs `wPv`, `wCol`, `wScore`, `auditScore` y todo lo que se complete a mano.
- Dejar un bloque corto con el texto del draft/estado y un único botón grande **“Check with AI”** (`checkRubricWithAI`). Sin checklist, sin contadores, sin timer manual de 20:00.
- Al entrar a Phase 3, el foco va al botón; no se envía solo (el usuario decide).

### 8. Speaking
- Verificar y corregir el flujo real: `spSelectPart(n)` + Start → brief de esa parte → `SP_EXAM.ready()` de esa parte, sin pantalla choose intermedia ni reset a Part 2.
- Full: `SP_EXAM.startFull()` corre 1→2→3→4 seguidas; al terminar Part 1 pasa a Part 2, etc., sin volver a choose. El reporte final es uno solo.
- Si ya funciona, agregar el test que lo pruebe y no tocar la lógica.

## Alcance

- `index.html`, `tests/`, capturas. Sin backend, sin límites, sin deploy.
- Sin handlers inline, i18n EN/ES simétrico, targets ≥44 px, 390×844 sin overflow, dark/light.

## Tests obligatorios

Actualizar/crear:
- `test_practice_flow.py`: Library sin lecciones/reference; contador = filas; “Hide done”; marcar/desmarcar persiste tras reload; marcado va al final.
- `test_mock_start.py` (nuevo): click en paper NO arranca timer (`#exTimer` no cambia en 2 s); modal con título/duración; Cancelar no arranca; “Empezar contador” arranca; “Abrir materiales” abre Library con `paper` y scope full; full mock pre-flight también pasa por modal.
- `test_exam.py` / `test_exam_sources_blocks.py`: `#exGuide` ya no tiene chips ni links; tiene el botón que abre la misma Library que la tarjeta.
- `test_practice_real.py` (nuevo): 0 lesson plans/guides/reference en Library; Materials abre Contents en las 4 sesiones; Today sin `#lastSpeaking`; Phase 3 sin checkboxes/inputs manuales y con `#rubAiBtn` visible.
- `test_speaking_turns.py` + `test_speaking_all_parts.py`: parte elegida directa; full 1→2→3→4 seguido, sin choose intermedio.
- `test_mobile.py`, `test_i18n.py`, `test_index_handlers_exist.py`, `test_ui_batch2.py`, `test_start_contents.py`, `test_plan.py`.

```bash
cd /home/juan/b2first-tracker/tests
for f in test_practice_flow.py test_mock_start.py test_exam.py test_practice_real.py test_speaking_turns.py test_speaking_all_parts.py test_start_contents.py test_practice_split.py test_ui_batch2.py test_mobile.py test_i18n.py test_index_handlers_exist.py test_plan.py; do
  uv run --no-project --quiet --with playwright --with httpx python "$f" || echo "FAIL $f"
done
```

Capturas: `tests/out/mock_start_modal_390_light.png`, `library_practised_390_light.png`, `writing_phase3_390_light.png`, `speaking_part_direct_390_light.png`.

## Cierre

Dos commits:
1. `feat(practice): solo recursos reales, marcado de practicados y Materials = Contents`
2. `fix(exam): arranque con pop-up y speaking por parte o completo`

Sin deploy.
