# Fase speaking-layout-fill — llenar el stage en desktop y compactar mobile

Repo `/home/juan/b2first-tracker`, HEAD `c4e9ee6`. Solo tocar CSS/HTML del Speaking y, si hace falta, el JS que muestra/oculta stage. No cambiar el motor ni la lógica de turnos.

Problema visible en capturas:
- `tests/out/speaking_v3_part3_1280.png`: la tarjeta mide ~788×410 y queda toda la mitad inferior de la pantalla en blanco.
- `tests/out/speaking_v3_part2_390.png`: hay un hueco grande entre la guía y las fotos, y otro entre las fotos y el micrófono; las fotos se ven chicas.
- `tests/out/speaking_v3_part4_1280.png`: el stage de conversación está centrado pero deja mucho blanco interno; parece un rectángulo vacío.

Requisitos:
1. Desktop >=900 px:
   - El área de materiales debe ocupar la altura disponible del viewport (desde debajo del header hasta el dock), no solo el alto intrínseco de la imagen. Usar `height`/`flex`/`grid` con `min-height:0` y evitar que el body crezca más allá de `100dvh`.
   - Fotos Part 2 y tarjeta Part 3: que sean lo más grandes posible dentro de ese alto, manteniendo proporción (`object-fit:contain` para la tarjeta, `cover` o `contain` para fotos), centradas. Si sobra alto por la relación de aspecto, el stage debe tener fondo/borde/radio de “mesa de examen” para que no sea blanco muerto; no agregar texto de preguntas ni contenido inventado.
   - Panel derecho sticky sigue igual, pero alineado arriba y sin forzar altura extra.
   - Part 4/Part 1: el stage de conversación debe llenar el alto disponible (no un rectángulo de 500 px con 200 px blancos abajo); distribuir rol activo, waveform y timer en el espacio, por ejemplo con `justify-content:space-between` y padding vertical, sin inventar preguntas.
2. Mobile 390×844:
   - Reducir huecos: el stage debe crecer para usar el espacio entre guía y dock; fotos con `max-height` mayor (sin overflow), centradas; botón de micrófono cerca del contenido.
   - Sin scroll horizontal; botones ≥48 px; nada tapado por el dock.
3. No romper: timer congelado en preflight/busy, preflight (Check/Record again/Skip/auto-check), roles, audio, i18n, sin transcripts.
4. Correr `test_speaking_v3_ui.py`, `test_speaking_v3_timer.py`, `test_speaking_v3_parts.py`, `test_mobile.py`, `test_i18n.py`.
5. Regenerar y revisar visualmente `speaking_v3_desktop_1280.png`, `speaking_v3_part3_1280.png`, `speaking_v3_part4_1280.png`, `speaking_v3_part2_390.png`, `speaking_v3_part3_390.png`.
6. Commit en la rama actual. No deployar.
