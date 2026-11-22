# Fase dedupe-exam — Exam simula, Library es el catálogo

Repo: `/home/juan/b2first-tracker`, HEAD `18427de`.

## Problema

Exam repite lo que ya está en Library: los "Local materials by paper" (4 secciones con papers, keys, audios) y la lista de 74 fuentes con buscador y filtros. La biblioteca ya muestra exactamente eso, mejor y ordenado. También dentro de Library hay duplicados: los "Reference" (sample cards) repiten papers que ya están como material local.

## Regla de producto

- **Exam** = simulación: mocks reales por paper, full mock, countdown, entrada al Speaking exam. Nada de catálogo.
- **Library** = el único catálogo de materiales y fuentes, dentro de Practice.
- **Today / sesión** = lo contextual de la unidad abierta (su paper, su key, su lesson plan), que no es catálogo completo.

## Cambios

### Exam
1. Borrar la tarjeta `examMaterialsCard` completa (las cuatro secciones `wtfSectionExam*`, `exMatRue/W/L/Sp`) con sus builders, acciones y claves i18n.
2. Borrar la sección de fuentes de Exam (`u4-exam-sources`, buscador, chips, `PRACTICE_SOURCES` render en Exam) y sus handlers/i18n exclusivos. `PRACTICE_SOURCES` sigue vivo para la biblioteca.
3. Dejar un solo link discreto al pie de la grilla de papers: "Papers, keys and practice links live in Library" que abre Practice → Library. Sin duplicar la lista.
4. Mantener intactos: grilla de 4 papers, "Start full mock", countdown, Speaking exam, y todo el flujo de simulación.

### Library
5. Eliminar duplicados por URL/nombre: si un ítem de Reference apunta al mismo paper o link que un material local o una fuente online, queda uno solo (prioridad al material local con archivo propio). Los libros y referencias que no estén en ninguna otra parte se mantienen.
6. El contador de Library debe reflejar los ítems reales después de deduplicar.

### Today
7. Los paneles de Materials de Today se quedan, pero no deben listar fuentes online completas: solo lo de la unidad (paper/key/lesson/audio) y un link "More in Library". Si ya listan las 74 fuentes, recortarlas a las 2–3 de esa parte.

## Alcance

Solo `index.html`, tests y capturas. Sin backend, sin dependencias, sin tocar plan, límites, corrector, speaking, listening propio, CSP ni landing.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_dedupe_exam.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_exercise_library.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_start_contents.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
```

Nuevo `tests/test_dedupe_exam.py`:
1. `#v-exam` no contiene `#examMaterialsCard` ni listas de fuentes con buscador; sí la grilla de papers, el full mock y el countdown.
2. Existe el link a Library y abre Practice en la pestaña Library.
3. Library no tiene dos filas con la misma URL ni el mismo nombre+parte; el contador coincide con las filas renderizadas.
4. En Today, el panel de Materials de una destreza no muestra fuentes online generales, solo las de esa parte, y aparece el link "More in Library".
5. 390×844 sin overflow, EN/ES simétrico, sin handlers inline.

Capturas: `tests/out/exam_clean_390_light.png`, `library_dedup_390_light.png`.

## Cierre

Commit `refactor(exam): Exam simula y Library cataloga, sin duplicados`. Sin deploy.
