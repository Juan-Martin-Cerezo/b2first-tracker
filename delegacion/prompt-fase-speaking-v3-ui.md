# Fase speaking-v3-ui — interfaz nueva del Speaking, guiada y realista

Repo: `/home/juan/b2first-tracker`, base HEAD `e47a832` (backend v3 ya hecho y verificado). Leer primero `speaking_v3/engine.py`, `speaking_v3/tone.py`, `speaking_v3/catalog.py` y `tests/test_speaking_v3_*.py` para el contrato real. **No cambiar el backend salvo bugs concretos**; esta fase es UI, docs y tests de interfaz.

## Regla máxima

Todo lo más parecido a un examen Cambridge real. El usuario **no ve texto de preguntas ni transcripciones**: solo lo que vería en la mesa (fotos de Part 2, tarjeta de Part 3, timer, indicador de quién habla y botón de micrófono). El examiner habla; el partner habla; el usuario responde con push-to-talk. Nada de chat, nada de burbujas de texto, nada de “AI is thinking” eterno.

## 1. Borrar la UI vieja

- Eliminar el panel `#spxPanel` completo y todo su CSS/JS: `SP_EXAM`, `spx*`, `spk-*` viejo, Live Studio, transcripts, Azure, reporte viejo, `SPK`, `spxTx`, `spxRpTx`, `spxChoose*`, `spxBrief*`, `spxExam*`, `spxCustom*`, `spxReport*`, `spxDots`, etc.
- Eliminar i18n y handlers muertos (`spx_*`, `spk_*`, `live_*` de speaking). No dejar código que llame a `/api/speaking/{turn,report,partner,pa,token,capabilities,minute}`.
- Mantener el punto de entrada `openSpeakingExam` y `window.SP_EXAM.open()` como alias al nuevo `SPEAKING.open()`, para no romper Today, Full Mock ni links existentes.
- No romper Exam, Practice, Progress, Writing, auth ni Full Mock.

## 2. Pantalla nueva

Una vista/pantalla completa (puede ser modal full-screen, como el examen actual) con:

**Chooser**
- Título “Speaking”.
- 4 tarjetas, una por examen: `B2 First Sample Paper 1`, `B2 First Sample Paper 2`, `B2 First for Schools Sample Paper 1`, `B2 First for Schools Sample Paper 2`. Cada una muestra partner (“with Alex”) y dos acciones claras: **Full mock** y **Practise a part** (chips 1, 2, 3, 4).
- Botón **Use my own task**.
- Nada de “AI examiner” marketing ni bullets largos.

**Own task (formulario normal, no JSON)**
- Título.
- Parte: 1, 2, 3, 4 o Full.
- Preguntas (una por línea) — para Part 1/4.
- Consigna / what to compare — para Part 2/3.
- Pregunta de decisión — Part 3.
- Fotos: 2 para Part 2; tarjeta/imagen para Part 3 (opcional si escribió las opciones).
- Botón “Save task”; validación inline clara; el task aparece en la lista y se puede borrar.
- Debe sentirse para un usuario normal: labels, placeholders y ayuda breve; nada de campos técnicos.

**Examen**
- Header: test, parte actual, timer oficial (mm:ss) y botón cerrar.
- Escenario: fondo neutro, avatar/indicador de EXAMINER, PARTNER y YOU. Solo un rol activo por turno.
- Centro: fotos de Part 2 lado a lado cuando corresponde; tarjeta de Part 3 cuando corresponde; en Part 1/4 solo el indicador de rol y timer. Sin texto de preguntas.
- Micrófono: botón grande **Hold to speak** (pointerdown/pointerup, touch y mouse). Al soltar, sube el audio. Mientras habla examiner/partner: micrófono deshabilitado y cartel “Listen”. Un solo turno activo.
- Si el usuario mantiene apretado más de `ui.turn_seconds` (Part 2/3) o 60 s, se corta solo y envía.
- Reproducir la respuesta del backend: usar `sequence` (array de clips `{speaker,audio_b64}`) en orden, actualizando el indicador; recién al terminar el último clip se habilita el micrófono. No mostrar texto.
- Si `accepted:false`/`retry:true`, el examiner ya mandó la repetición formal; el usuario vuelve a hablar. No mostrar “wrong answer”.
- `prep_done`: en Part 3, tras 15 s de mirar la tarjeta, enviar `action:"prep_done"` automáticamente y mostrar la tarjeta hasta que termine la discusión.
- Timer: empieza al entrar a la parte (no en intro). Al llegar a 0, enviar `time_up:true` en el siguiente turno o llamar al endpoint con `action:"time_up"` si el backend lo soporta; si no, mostrar cierre y pasar. No bloquear la UI.
- Al terminar: pantalla de reporte con las 3 bandas (Grammar & Vocabulary, Discourse Management, Interactive Communication), comentarios y botón **Save report**. Sin pronunciación, sin transcripts, sin “pronunciation not measured” (se sacó del reporte).
- Manejo de errores: `503 speech_not_configured` → mensaje claro “Speaking voice is not configured on this server” y link a Settings; no simular voces. `429` cuota → mensaje claro con límite. `410` sesión expirada → volver al chooser.
- Mobile 390×844 primero: botón de micrófono alcanzable con el pulgar, fotos sin overflow, timer legible. Desktop también.

## 3. Integración

- `SPEAKING.open(testId?, part?)` abre chooser o directo el examen.
- `openSpeakingExam` y `SP_EXAM.open` delegan.
- Full Mock: al terminar Listening, abrir Speaking en el test correspondiente (o test 01 si no hay mapeo) en modo full, sin volver al chooser.
- Practice/Today: el botón de Speaking abre el chooser nuevo.
- Cuota: single part y full consumen 1 mock; mostrar límite si 429.
- No guardar ni mostrar transcripts en ningún lado (ni en consola, ni en DOM, ni en localStorage).

## 4. Tests de UI (obligatorio)

- `test_speaking_v3_ui.py`:
  - catálogo muestra exactamente 4 tests + own task; click en Part 2 arranca sesión y muestra fotos correctas; no hay texto de guion ni transcript en el DOM.
  - intro: primer audio examiner, luego micrófono habilitado; secuencia partner/examiner respeta orden; no se habilita el mic mientras hay audio.
  - push-to-talk: pointerdown/up dispara el POST; botón deshabilitado durante playback.
  - Part 3: tarjeta visible, prep 15 s, `prep_done` automático.
  - reporte: 3 bandas, sin palabra “pronunciation” ni “transcript”; Save report llama al endpoint.
  - own task: formulario crea tarea, aparece en la lista, arranca; validación de campos por parte.
  - mobile 390 y desktop 1280: sin overflow horizontal, mic ≥56 px, fotos dentro del viewport.
- `test_speaking_v3_no_old_ui.py`: `grep` en `index.html` sin `spx`, `spxTranscript`, `/api/speaking/turn`, `Live Studio`, `pronunciation`, `transcript` visibles.
- Actualizar `test_i18n.py`, `test_mobile.py`, `test_index_handlers_exist.py` si corresponden.
- Backend tests existentes deben seguir en 0. Tests con `B2_SPK_TEST_MODE=1` y audio stub; nada de red.

## 5. Docs

Actualizar README, docs/HACKATHON.md, PRIVACY, DATA-MAP, TERMS y cualquier copy visible:
- Speaking = 4 exámenes Cambridge sample + own task, intro obligatoria, partner IA, push-to-talk, sin transcripts, sin pronunciación, sin Live/Azure.
- Privacidad: audio del usuario no se guarda; solo banderas/bands; own task images se guardan por cuenta hasta que el usuario las borra.
- Quitar toda mención a Live Studio, Azure Pronunciation, WebSocket, `/api/speaking/pa`, transcripts.
- Mantener créditos de Cambridge y Wikimedia si quedan fotos.

## 6. Entregable

- Commit(s) en la rama actual. **No deploy.**
- Capturas reales `tests/out/speaking_v3_chooser_390.png`, `speaking_v3_intro_390.png`, `speaking_v3_part2_390.png`, `speaking_v3_report_390.png`, `speaking_v3_own_task_390.png` y una desktop.
- Resumen: archivos tocados, tests con exit code, qué quedó fuera y cualquier limitación real.
- No inventar resultados: si un test no pasa, decirlo y arreglarlo antes de terminar.
