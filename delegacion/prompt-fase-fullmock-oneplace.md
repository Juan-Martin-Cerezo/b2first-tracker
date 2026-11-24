# Fase fullmock-oneplace — un solo lugar para hacer el full mock

Repo: `/home/juan/b2first-tracker`, base HEAD `8268623` (o el HEAD vigente).

## Pedido del dueño

En el pre-flight del full mock, “Choose a local sample” tiene que mostrar los samples y además decir algo como **“O abrí / tené a mano todos los ejercicios del full exam”**, dejándolos **ahí mismo**. Desde ese mismo lugar arranca el full mock, con el tiempo de cada paper y salto automático al siguiente. Todo intuitivo, **sin mover al usuario a otra pantalla**. Sacar redundancias del mismo material repetidas en varias partes de la app.

## Cambios

### 1. Pre-flight = una sola pantalla de full mock
- Encabezado: “Full mock — tené todo a mano”. Sub: “Elegí una muestra o abrí los ejercicios de cualquier muestra. Todo queda en esta pantalla; el cronómetro avanza paper por paper.”
- Muestra (`#fmSampleList`) queda como está (Standard 1/2, For Schools 1/2), con “Hecho”.
- **“Todos los ejercicios, a mano”**: reemplazar la lista de chips sueltos por un panel `#fmMaterialsAll` con 4 bloques siempre visibles (no acordeón cerrado, no chips truncados):
  1. Reading & Use of English — Paper, Answer key, (audio no aplica)
  2. Writing — Paper, Answer keys (si existen)
  3. Listening — Paper, Answer key, **cada audio por part** (P1–P4 cuando existan) y Tapescript
  4. Speaking — Speaking cards / examiner notes
  Cada ítem es un link real (`target=_blank`), con nombre claro y tipo. Si falta un archivo, se omite el ítem, no se muestra roto. Los links se actualizan al cambiar de muestra.
- Quitar de cada fila de paper el botón “Open materials” y los chips “quick”: los links ya están en el panel de arriba. La fila queda: nombre, duración, “Hecho/Desmarcar”, y nada más.
- Botón único “Empezar full mock · 195′ escritos + 14′ Speaking” al lado del panel (no obligar a scrollear hasta el final). El bloque “More full mocks online” queda plegado en un `<details>` para no competir con lo importante.

### 2. Runner en el mismo lugar
- Al confirmar el pop-up existente (`#mockStartModal`), **no cerrar el pre-flight, no scrollear a `#exActive`**. En cambio:
  - Mostrar `#fmRunner` arriba de los materiales: timer grande (hereda `exTimer`/`exIv`, una sola fuente), “Paper 1 de 4 · Reading & Use of English · 75′”, botones Pausa/Reanudar, “Saltar al siguiente paper”, y los links de **ese paper** repetidos en una fila compacta (para no scrollear).
  - Ocultar `#exActive` (la tarjeta vieja del timer) mientras `FULL_MOCK.active` sea true, para que no haya dos cronómetros ni dos listas.
  - Al llegar a 0, `fullMockAdvance()` cambia el runner al paper siguiente y actualiza título/duración/links. El scroll no se mueve.
  - Después de Listening, abre el Speaking exam como hoy, sin navegar a otra vista; al volver, `#fmRunner` muestra “Completo” y el banner “Hacé otro” sigue en la misma pantalla.
- “Saltar al siguiente paper” avanza el índice y reinicia el timer al paper siguiente (misma función que el avance automático), con confirmación breve si el timer sigue corriendo.
- El modal de inicio: “Abrir materiales” ya no navega a Library; cierra el modal y deja visible el panel de materiales del pre-flight, sin arrancar el timer.

### 3. Sacar redundancias
- Eliminar `#examLibraryLink` (“Papers, keys and practice links live in Library”): el pre-flight ya tiene todo.
- Eliminar `#exActiveLibBtn` (“Open materials for this mock”): el material está en el runner.
- Eliminar el botón “Open materials” de `#exGuide` (queda solo el texto de ritmo/estrategia) y el bloque visible “Or pick the paper manually” (mantener el `<select id="exPaper">` oculto si algún test lo usa).
- No duplicar la lista de online: el pre-flight muestra una sola lista plegada; Library sigue siendo el catálogo, pero no se enlaza desde Exam para evitar el salto.
- Mantener **un** botón “Open materials” por tarjeta de paper (para mock de un solo paper). Nada más.

### 4. Mobile
390×844: sample, frase “tené todo a mano”, panel de materiales y botón de inicio visibles sin scroll horizontal; runner sticky arriba del panel; timer ≥28 px; links con target ≥44 px; el FAB no tapa el botón de inicio. 1280×800: 2 columnas (muestra+runner | materiales) sin desperdiciar ancho.

## Alcance

- `index.html`, tests, capturas. Sin backend, sin límites, sin tocar speaking logic (solo abrir/cerrar su overlay), sin deploy.
- Sin handlers inline, i18n EN/ES simétrico, dark/light.

## Tests

Crear `tests/test_fullmock_oneplace.py`:
1. Abrir full mock: se ven los 4 samples, la frase de “tené todo a mano” y los 4 bloques de materiales con paper+key+audio donde existan; cambiar de muestra cambia los links.
2. No existe `#examLibraryLink`, ni `#exActiveLibBtn`, ni botón “Open materials” en `#exGuide`, ni el bloque visible del selector manual; sí un único “Open materials” por tarjeta de paper.
3. “Empezar” abre el modal; “Abrir materiales” lo cierra y deja el panel visible **sin** arrancar el timer (`#exTimer` no cambia en 2 s) y sin cambiar de vista (`#v-exam` sigue activa).
4. “Empezar contador” arranca el timer en `#fmRunner`, oculta `#exActive` y no scrollea (comparar `scrollY` antes/después, tolerancia 40 px).
5. Auto-salto: con un hook de test (`window.FULL_MOCK_TEST.setLeft(2)`), a los 3 s el runner pasa de “Paper 1” a “Paper 2” y el timer se reinicia a 80′; repetir hasta Listening.
6. “Saltar al siguiente paper” avanza manualmente y reinicia el tiempo.
7. Al terminar los 3 escritos se abre el Speaking; al volver, banner “Completo” y “Hacé otro” en la misma pantalla.
8. 390×844 sin overflow; links ≥44 px; FAB fuera del botón de inicio. EN/ES simétrico; 0 errores de consola.

Actualizar `test_mock_start.py`, `test_exam.py`, `test_practice_flow.py`, `test_mobile.py`, `test_i18n.py` por los controles eliminados. Verificación:

```bash
cd /home/juan/b2first-tracker/tests
for f in test_fullmock_oneplace.py test_mock_start.py test_exam.py test_practice_flow.py test_mobile.py test_i18n.py test_index_handlers_exist.py test_speaking_exam.py; do
  uv run --no-project --quiet --with playwright --with httpx python "$f" || echo "FAIL $f"
done
```

Capturas: `tests/out/fullmock_materials_390_light.png`, `fullmock_runner_390_light.png`, `fullmock_materials_1280_light.png`.

## Cierre

Un commit: `feat(exam): full mock en una sola pantalla con materiales a mano`. Sin deploy.
