# Fase writing-ux — editor cómodo y resultado en pantalla aparte

Repo `/home/juan/b2first-tracker`, HEAD actual con Practice UX (esperar commit previo). Solo `index.html`, CSS y tests de Writing/IA. No tocar backend, Speaking ni Practice. No deployar.

Problema: en mobile el textarea/word meter queda tapado por la nav inferior y “Correct it” queda muy abajo; en desktop el resultado se apila debajo del editor y obliga a scrollear. La tarea opcional está en un `<details>` que empuja todo. El usuario pide orden y pop-ups/pantallas aparte.

Diseño objetivo:
1. Editor (`#v-ia`) compacto, una sola tarjeta:
   - Un solo título “Writing corrector” (sacar el `h2` interno duplicado); subtítulo corto.
   - Fila superior: `Text type` (select) + botón “Add task (optional)” que abre un modal `iaTaskModal` con `textarea#iaPrompt`, Save / Remove / Cancel. Mostrar badge “Task added” cuando hay texto; nunca inline.
   - Textarea grande y cómoda (desktop ~50vh; mobile ~42-45vh), sin que la nav la tape.
   - Barra de acción sticky (desktop y mobile) con: contador de palabras/estado (corto), cuota, y botón “Correct it”. En mobile va por encima de la nav inferior, con padding/safe-area; no se superpone. El word meter no debe quedar debajo del fold.
   - Loading: mantener progreso, pero en un panel compacto/overlay dentro del editor, sin empujar el layout; no mostrar resultado debajo.
2. Resultado en pantalla aparte:
   - Mover `#iaResult` a un modal/full-screen sheet `#iaResultSheet` (desktop diálogo ancho 860-960, mobile full-screen con header sticky).
   - Al terminar `submitIaWriting`, abrir el sheet; el editor queda detrás sin scroll. Header: “Cambridge B2 First result”, total badge, botón cerrar/volver al editor.
   - Dentro: bands (2 columnas desktop, 1 mobile), quotes y rewrites en secciones colapsables (`details`) para no hacer una página eterna; botón “Correct another” que cierra y limpia el resultado (sin borrar el texto salvo confirmación).
   - Al cerrar, el foco vuelve al editor; scroll arriba.
3. Error/validación: mostrar inline cerca de la barra de acción o como toast, no una alerta roja al fondo; mantener Retry.
4. Mobile: sin overlap con nav; teclado no tapa el botón principal (usar `position:sticky`/`env(safe-area-inset-bottom)` y `scroll-padding-bottom`); targets ≥48px; sin overflow horizontal. Desktop: ancho máximo, sin huecos gigantes.
5. i18n EN/ES, dark/light. Mantener IDs `iaText`, `iaKind`, `iaPrompt`, `iaSubmitBtn`, `iaResult`, `iaBandsGrid`, `iaRewriteList`, `iaQuotesList`, `iaTotalBadge`, `iaStateLabel`, `iaQuota`, `iaLoading`, `iaError`, `iaErrorMsg`, `iaRetryBtn` para no romper tests.
6. Tests:
   - Actualizar `test_ai.py` UI: submit abre `#iaResultSheet`, bands/rewrites visibles dentro; cerrar vuelve al editor; task modal guarda/borra `#iaPrompt`; en mobile el botón no queda tapado.
   - Actualizar `test_writing_progress.py`, `test_design_consistency.py`, `test_mobile.py`, `test_i18n.py` si usan detalles inline.
   - Capturas `writing_ux_1280.png`, `writing_ux_390.png`, `writing_result_1280.png`, `writing_result_390.png`, `writing_task_390.png`; revisar visualmente.
   - Correr `test_ai.py`, `test_writing_progress.py`, `test_design_consistency.py`, `test_mobile.py`, `test_i18n.py`.
7. Commit en rama actual. No deployar. Reportar tests, capturas y archivos.
