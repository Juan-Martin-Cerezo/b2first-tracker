# Fase practice-ux — ordenar Practice y sacar el scroll infinito

Repo `/home/juan/b2first-tracker`, HEAD `727f9da`. Solo `index.html`, CSS y tests de Practice. No tocar backend, Speaking ni Writing. No deployar.

Problema: Practice acumula header + 2 tarjetas + Library con búsqueda + 5 chips de paper + 8 chips de part + 3 checkboxes + sort + listado; en mobile no se ve ni un contenido en la primera pantalla. Además “Exercises by part” está en un `<details>` al final de 116 contenidos: hay que scrollear muchísimo y las tarjetas de parte tienen inputs enormes inline. El usuario pide orden, menos scroll, pop-ups/pantallas aparte.

Diseño objetivo:
1. Header: “Practice” + subtítulo corto, sin duplicar el texto del Library.
2. Dos acciones compactas arriba: “Full mock” (flujo actual) y “Practise by part” (abre un modal/pantalla aparte, NO hace scroll al final).
3. Library como protagonista:
   - Una sola fila: buscador + botón “Filters” (con badge de filtros activos) + contador.
   - Eliminar del flujo los chips/checkboxes/sort; moverlos a un modal (`practiceFiltersSheet`): en mobile bottom sheet, en desktop modal centrado. Incluye papers, parts, Free only, Full paper only, Hide done, Sort, botones “Apply filters” y “Reset”. Aplicar en vivo o al confirmar, pero cerrar al aplicar.
   - Debajo del buscador, solo si hay filtros activos, una fila compacta de chips-resumen con “Clear”. Si no hay filtros, no ocupa espacio.
   - El listado empieza inmediatamente después; sin bloque de filtros enorme. Mantener búsqueda, grupos y “Mark done”.
4. “Practise by part”:
   - Convertir el `<details id="practicePartsDetails">` inline en un modal/pantalla `practicePartsModal` (desktop diálogo ancho 760-860; mobile full-screen sheet con header sticky y cierre).
   - Listar las partes agrupadas, pero en filas compactas: título/meta + resumen de recursos + acciones “Start”, “Resources”/“Open contents” y “Mark done”.
   - El registro de resultado (Correct/Total/Minutes/Save o Score/Minutes) NO debe estar siempre inline: un botón “Log result” abre un mini modal/popover con esos campos y Save. Al guardar, cierra y marca la parte.
   - En desktop se puede usar grid de 2 columnas para las partes; en mobile una columna.
5. Mobile: contenido real visible en la primera pantalla; filtros y by-part en sheets; safe-area; nada tapado por la nav inferior; targets ≥48 px; sin overflow horizontal.
6. Desktop: aprovechar ancho; Library max-width razonable, acciones y filas compactas; sin huecos gigantes.
7. Mantener i18n EN/ES, dark/light, IDs de datos y funciones existentes cuando sea posible. No romper `openPracticeLibrary`, `renderExercisesLibrary`, `renderParts`, `togglePractised`, `savePart`, `startPart`, `startFullMock`.
8. Tests:
   - Actualizar/añadir tests que abran Filters, apliquen paper/part, cierren, verifiquen que el listado queda visible sin chips inline; abran “Practise by part” como modal, verifiquen que NO hay `<details>` gigante al final, abran “Log result” y guarden.
   - Correr `test_practice_flow.py`, `test_practice_real.py`, `test_practice_split.py`, `test_start_contents.py`, `test_mobile.py`, `test_i18n.py`, `test_design_consistency.py`.
   - Capturas `practice_ux_1280.png` y `practice_ux_390.png` con filtros cerrados; una con filters sheet y otra con by-part modal. Revisar visualmente.
9. Commit en rama actual. No deployar. Reportar tests, capturas y archivos.
