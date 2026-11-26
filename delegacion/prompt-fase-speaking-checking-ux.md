# Fase speaking-checking-ux — sacar preflight y mostrar espera animada

Repo `/home/juan/b2first-tracker`, HEAD `338c306`. Solo frontend (`index.html`, tests UI). No tocar motor ni API. No deployar.

El usuario NO quiere clickear “Check answer”. Quiere que al soltar el micrófono el audio se envíe automáticamente y que la espera se sienta parte del examen:
- visualizador animado de onda sonora,
- indicador/progress bar,
- aviso chico: “Checking your answers takes a few seconds.” / ES “Revisar tus respuestas toma unos segundos.”
- sin botones Check answer / Record again / Skip question / checkbox auto-check.

Cambios:
1. Eliminar el flujo preflight completo:
   - Borrar el bloque `#speakingPreflight` del HTML y sus handlers/acciones (`speakingCheckAnswer`, `speakingRecordAgain`, `toggleAutoCheck`), i18n y CSS que quede sin uso.
   - `finishRecordingAndSend` debe enviar siempre directo (`submitTurn`) después de obtener el audio; no guardar `pendingTurn`.
   - Eliminar `AUTO_CHECK_KEY`/localStorage y la lógica de pending.
   - Mantener intacto el skip por micrófono denegado si existe.
2. Estado “checking”:
   - Al enviar, mostrar un panel de espera visible en todas las partes (incluidas Part 2 y 3, donde el stage son fotos/tarjeta), en el dock o sobre el stage.
   - Incluir: onda animada de 7 barras (reutilizar `.spk3-wave`), texto “Checking your answer… {sec} s”, una progress bar indeterminada animada y el aviso chico de “a few seconds”. Sin botón.
   - En Part 1/4, el waveform del stage también debe animarse cuando `data-live="checking"`.
   - Respetar `prefers-reduced-motion` (sin animación, pero mostrando progreso/texto).
   - El timer oficial sigue congelado mientras `state.busy`; no cambiar eso.
3. Tests:
   - Actualizar `tests/test_speaking_v3_ui.py`: al soltar el micrófono debe haber `POST /turn` inmediato; NO debe existir `#speakingPreflight`, `#speakingCheckBtn`, ni checkbox; debe verse el panel de checking con onda/progress/nota y luego volver el mic.
   - Mantener safe skip solo si aplica al botón de mic denegado; si el test viejo usa skip de preflight, reemplazarlo por verificación de auto-envío.
   - Correr `test_speaking_v3_ui.py`, `test_speaking_v3_timer.py`, `test_speaking_v3_parts.py`, `test_mobile.py`, `test_i18n.py`.
   - Capturas: una mobile y una desktop del estado checking (se puede simular retraso de `/turn` para que se vea), y revisar que no haya huecos/overflow.
4. Commit en rama actual. Reportar archivos y tests.
