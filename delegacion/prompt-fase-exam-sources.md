# Fase exam-sources — la pestaña Exam con los mismos bloques y muchas fuentes a mano

Repo: `/home/juan/b2first-tracker`, HEAD `be80e1b`.

## Problema

En Today ya quedaron los materiales en bloques (paper + keys, Full paper y Online separados), pero en la pestaña **Exam** (`index.html` ~4730, card `u4-exam-sources`) las fuentes siguen como una lista corta (`#examSources`, construida desde `PRACTICE_SOURCES` en `renderExamSources()` ~18109) y hay que ir a otra pestaña para ver todo. Juan quiere que en Exam funcione igual que en Today, con **muchas fuentes a mano**.

## Alcance

1. **Reusar el mismo lenguaje de bloques** que Today (misma tipografía, espaciado vertical, tarjetas, hint de uso). No crear un estilo nuevo si ya existe: reutilizar las clases del renderer de bloques de "Where to find".
2. **Agrupar por paper**, en este orden: Reading & Use of English, Writing, Listening, Speaking. Cada grupo con su encabezado y una línea de qué se practica ahí.
3. **Mostrar todas las fuentes** de `PRACTICE_SOURCES` (hoy 28) en bloques, no una selección corta: cada bloque con
   - nombre de la fuente + link (mismo `target="_blank" rel="noopener"`),
   - el campo `what` como descripción de una línea,
   - una pista de uso concreta (derivada de `mins` y `kind`): p. ej. "15 min · free · marked instantly — do one set, then log it" / "20 min · free — read the model answer and compare structure".
   - si la fuente tiene `part`, mostrarlo como etiqueta chica ("Parts 1–4").
4. **Buscador y filtro rápido** arriba de los bloques, dentro de la misma tarjeta: input de búsqueda y chips "All / Free / Reading / Writing / Listening / Speaking". Filtrar en vivo, sin recargar. Accesible por teclado.
5. **Todo a un toque**: cada bloque es un `<a>` completo (toda la tarjeta clickeable), no solo el título. Los links abren en pestaña nueva.
6. Mobile 390×844: una columna, sin overflow horizontal, targets ≥44px, light y dark. i18n EN/ES para encabezados, labels del buscador, hints y contadores; los nombres de fuentes no se traducen.
7. Mantener el botón "Open the full source library" y el resto de la pestaña Exam (Real mocks, selector manual, `startFullMock`, `startRealMock`, `openSpeakingExam`) **sin cambios de comportamiento**.

## Reglas

- Solo `index.html` (markup, CSS interno, JS del renderer) y tests. No tocar backend, límites, plan, listening propio, cuentas, CSP ni landing.
- Sin dependencias nuevas, sin handlers inline (la app ya usa `data-action`; el buscador puede usar `data-input`/`data-change` según el patrón existente).
- Nada de listas hardcodeadas duplicadas: derivar de `PRACTICE_SOURCES`.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_exam_sources_blocks.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
```

Nuevo `tests/test_exam_sources_blocks.py`:
1. La pestaña Exam renderiza 4 grupos con encabezado y, en total, tantos bloques como `PRACTICE_SOURCES` (≥28).
2. Cada bloque es un link (`<a href>`) clickeable completo y su `href` coincide con el `url` de la fuente.
3. El buscador filtra: escribir "listening" deja solo fuentes de Listening; limpiar restaura todas.
4. Los chips de filtro funcionan (Free deja solo `kind==='free'`).
5. 390×844: sin overflow horizontal, alturas ≥44px, EN y ES con los mismos bloques.
6. No hay handlers inline nuevos y la pestaña no lanza pageerrors.

Capturas: `tests/out/exam_sources_390_light.png`, `_390_dark.png`, `_1280_light.png`.

## Cierre

Commit `feat(exam): fuentes en bloques con buscador y filtros`. Sin deploy.
