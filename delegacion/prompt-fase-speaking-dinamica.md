# Fase speaking-dinamica — Part 3/4 realistas, espera elegida y desktop

Repo `/home/juan/b2first-tracker`, HEAD `3cfd97f`. Leer antes: `speaking_v3/engine.py`, `speaking_v3/voice.py`, `speaking_v3/validation.py`, `index.html` (bloque `SPEAKING` ~11000-12300 y CSS `.spk3-*` ~1200-1500), tests de Speaking.

## Contexto oficial (Handbook B2 First, Component 4, pp. 70-75)

- Part 3: 2 minutos de conversación **entre los dos candidatos**; después 1 minuto para decidir. El examiner solo da la instrucción, luego dice “Thank you. Now you have about a minute to decide...” y al final “Thank you.” No interrumpe ni hace preguntas durante la discusión. Hay una tarjeta con una pregunta y 5 ideas; **no hay que cubrir las 5**. Los candidatos eligen por dónde empezar, se preguntan opiniones, están de acuerdo o no, y avanzan a otra idea. Frases típicas: “Shall we start with this one?”, “What do you think?”, “I see your point, but...”, “Shall we move on to...?”. No se penaliza no llegar a una decisión, pero deben negociar.
- Part 4: 4 minutos. El examiner dirige preguntas relacionadas con el tema de Part 3; pueden ser para un candidato o para ambos. Los candidatos expresan/justifican opiniones, están de acuerdo/desacuerdo y especulan. El partner **también recibe preguntas propias**, no solo comenta lo que dice el usuario; el usuario también opina sobre lo que respondió el partner.
- Part 3 no es un monólogo del usuario ni una secuencia usuario→partner→examiner. Es una conversación con turnos solapados y cambio de ideas.

## A. Motor Part 3 (speaking_v3/engine.py)

Estado sugerido (puede ajustarse, mantener persistencia actual):
- `part3_open`: después de `prep_done`, examiner dice `start_discussion` y el partner abre la conversación con una línea natural, por ejemplo: “Shall we start with the nightclub?”. El usuario responde. Alternativa: si el usuario dice “Can I start?” / “Shall I start?” / “I’ll start”, el partner contesta “Yes, go ahead” y el usuario arranca; no contar eso como respuesta de contenido.
- `part3_discussion`: cada turno del usuario recibe una respuesta del partner que:
  - reacciona a la opinión concreta del usuario (de acuerdo/desacuerdo parcial, con razón),
  - introduce o pregunta por **otra** idea de la tarjeta que no se haya cubierto,
  - no repite siempre la misma idea ni la misma frase.
  Mantener `covered_options` y `focus_option` en la sesión. El partner debe cubrir ideas distintas a lo largo de la conversación. No agregar clips de examiner entre turnos.
  El usuario puede responder con una opinión nueva o con una reacción corta (“I agree”, “That’s true”, “I’m not sure”); la validación debe aceptar esas respuestas cooperativas y no exigir keywords largas. Solo reintentar por silencio/no inglés o respuestas claramente fuera del tema.
- La discusión debe durar hasta ~110-120 s o hasta 5-6 turnos de usuario, lo que ocurra primero, no terminar a los 3 turnos. Al llegar: examiner `decision_prompt`.
- `part3_decision` (1 min): el partner y el usuario negocian de verdad, 2-3 intercambios; el partner puede proponer, el usuario aceptar/discrepar, y el partner puede ceder o mantener. Terminar al llegar a ~60 s o tras 3 turnos de usuario. No hace falta que haya decisión unánime.
- No mostrar nunca el texto de la tarjeta ni las preguntas en pantalla; solo la imagen de la tarjeta.

## B. Motor Part 4

- Cada ronda debe incluir al partner con una pregunta propia, no un “What do you think?” genérico sobre lo que dijo el usuario.
- Patrón recomendado, alternando el orden:
  - Ronda impar: examiner pregunta al usuario → usuario responde → examiner pregunta al partner **la misma pregunta o una relacionada** (“And you, Alex?”) → partner responde → examiner pregunta al usuario “Do you agree with Alex?” / “What do you think?” → usuario reacciona → siguiente pregunta.
  - Ronda par: examiner pregunta primero al partner → partner responde → examiner pregunta al usuario la misma pregunta → usuario responde → examiner pregunta al partner “Do you agree?” → partner reacciona → siguiente.
- El partner debe recibir `question_text` real y contexto para responder con opinión propia; no limitarse a comentar la respuesta del usuario. El usuario también debe poder reaccionar a la respuesta del partner.
- Validación: aceptar respuestas de opinión/reacción razonables; no convertir cada respuesta en un interrogatorio. Mantener 4 min y máximo 3-4 preguntas.
- Mantener examiner formal británico; sin transcripciones; solo audio.

## C. Latencia y UX de espera (index.html)

Problema actual: al soltar el micrófono queda “Please wait…” mucho tiempo, sin explicación ni control.
- No enviar el audio automáticamente la primera vez. Mostrar una hoja/paso compacto: “Answer recorded · 12 s. Checking your answer can take 10–30 seconds.” con:
  - `Check answer` (primario): envía y muestra progreso.
  - `Record again`: descarta el audio y vuelve a grabar.
  - `Skip question`: llama al endpoint `/skip` sin enviar audio (seguro, no hay carrera).
  - Checkbox “Always check automatically” guardado en `localStorage` (`spk3_auto_check=1`); si está activo, enviar directo.
- Mientras se comprueba: mostrar tiempo transcurrido (“Checking… 8 s”), texto claro de que puede tardar y que puede esperar; no un “Please wait…” opaco. Si el usuario quiere, puede salir del examen; no prometer cancelar una petición ya enviada.
- El timer oficial debe seguir congelado mientras `busy` (ya implementado en `ecbd46c`/`03ea542`), y reanudarse cuando empieza el audio. Mantener ese comportamiento y su test.
- Reducir latencia real si es seguro: sintetizar en paralelo los clips TTS (ThreadPoolExecutor manteniendo orden), evitar llamadas LLM redundantes y cachear lo cacheable; medir antes/después con logs o test. No romper tono ni cuotas.

## D. UI desktop

- Actualmente en 1280×800 las fotos quedan chicas y hay grandes huecos verticales; parece mobile estirado.
- A partir de 900 px: layout de dos columnas. Izquierda: stage de materiales (fotos lado a lado grandes, tarjeta de Part 3 grande) con límite de altura y `object-fit`. Derecha: panel de control sticky con roles Examiner/Partner/You, timer grande, micrófono, estado y explicación de la parte. Header compacto.
- En partes sin imágenes (Part 1/4), el stage no debe ser un rectángulo blanco vacío: usar un área de conversación con rol activo, indicador de audio/waveform y el timer, sin inventar preguntas ni texto.
- Mobile 390×844 se mantiene apilado y usable; no overflow horizontal; botones ≥48 px.
- Capturas: `speaking_v3_desktop_1280.png`, `speaking_v3_part2_390.png`, y una de Part 3/4 desktop/mobile. Revisarlas visualmente.

## E. Tests obligatorios

- `test_speaking_v3_parts.py`: ampliar/ajustar para Part 3 con opening del partner, meta “Can I start?”, cambio de ideas, decisión; Part 4 con pregunta al partner y reacción del usuario.
- `test_speaking_v3_ui.py`: preflight de espera, auto-check, skip seguro, desktop 1280 y mobile 390, sin transcripts ni preguntas en DOM.
- `test_speaking_v3_timer.py`: sigue pasando.
- Tests de tono, privacidad, intro, fullmock, mobile, i18n.
- No deployar. Correr tests, mirar capturas y dejar commits en `feat/speaking-continuous` (o commits claros en la rama actual). Reportar latencia antes/después y archivos tocados.
