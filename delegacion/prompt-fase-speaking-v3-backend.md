# Fase speaking-v3-backend — motor nuevo del Speaking (sin UI todavía)

Repo: `/home/juan/b2first-tracker`, base HEAD `bb294fd`.

## Objetivo

Rehacer el Speaking de IA desde cero, borrando el motor viejo. Esta fase es **solo backend, contenido y datos**: módulos nuevos, endpoints nuevos, guiones de los 4 exámenes y limpieza. La UI se rehace en la fase siguiente contra este contrato. **No tocar `index.html` salvo para nada**; si algo del JS viejo queda llamando endpoints viejos, se arregla en la fase UI.

REGLA MÁXIMA: todo debe parecerse al examen real. Nada de examiner robótico, nada de aceptar respuestas incorrectas, nada de transcripts visibles.

## 0. Voz del examiner: formal, británica, de examen

El examiner es un examinador Cambridge formal. **Siempre** habla en inglés británico formal, cordial y mesurado. Nunca suena a chatbot, profesor entusiasta ni amigo.

Reglas de estilo obligatorias:

- Británico: `organise`, `programme`, `colour`, `favourite`, `centre`, `practise` (verbo), `at the weekend`, `shall`, `have got`. Prohibido: `gotten`, `mom`, `math`, `vacation`, `fall`, `sidewalk`, `cell phone`, `soccer`, `train station` (usar `railway station`), `color`, `organize`.
- Registro formal: `Good morning`, `I'd like you to…`, `Would you mind…?`, `I'm afraid…`, `I beg your pardon`, `I'm terribly sorry`, `Forgive me`, `May I ask…?`, `Thank you very much`, `Shall we…?`, `Very well`.
- Prohibido: `Hi`, `Hey`, `Yeah`, `Okay`, `OK`, `gonna`, `wanna`, `stuff`, `guys`, `no worries`, `got it`, `Great job!`, `Awesome`, emojis, signos de exclamación múltiples.
- Contracciones solo donde el guion Cambridge real las usa (`I'd like`, `it's`). Nada de `gonna` ni `wanna`.
- El examiner no halaga: dice `Thank you`, `That's fine`, `Very well`. No dice `Excellent!` ni `Well done!`.
- El partner NO es el examiner: es un candidato B2, puede ser natural, dudar, discrepar o cambiar de opinión. Tiene otra voz.

Frases canónicas (usar exactamente estas o una variante igual de formal):

- No oyó el nombre: `I beg your pardon. I didn't quite hear your name. Would you mind repeating it?`
- No oyó la ciudad: `I beg your pardon. I didn't quite hear where you live. Would you mind repeating that?`
- No oyó algo en general: `I'm terribly sorry. I didn't quite hear that. Would you mind saying it again?`
- No entendió el contenido: `I'm afraid I didn't quite follow. Would you mind explaining that again?`
- Respuesta off-topic: `I'm afraid that wasn't quite what I asked. Would you mind answering the question about …?`
- Habló en español: `I'm afraid I didn't quite follow that. Would you mind repeating it in English?`
- Silencio: `Take your time. Do let me know when you're ready.`
- Cierre de parte: `Thank you very much. That brings us to the end of this part.`
- Transición: `Thank you. We'll now move on to Part … .`

Prohibido literalmente: `catch` (en cualquier forma: `catch your name`, `didn't catch`), `Could you please repeat the question?`, `Pardon?` solo, `Sorry?` solo, `What?`, `No problem`, `Alright?` (solo `All right?` cuando lo dice el guion), `Let's go`, `Ready?`.

## 1. Contenido: 4 exámenes exactos

Descargar y usar como fuente (ya verificadas, ~6 páginas cada una):
1. https://firsttracker.app/files/01-Examen-Completo-01/cambridge-english-first-2015-sample-paper-1-speaking%20v2.pdf
2. https://firsttracker.app/files/02-Examen-Completo-02/cambridge-english-first-2015-sample-paper-2-speaking%20v2.pdf
3. https://firsttracker.app/files/03-Examen-Completo-For-Schools-01/cambridge-english-first-for-schools-sample-paper-1-speaking.pdf
4. https://firsttracker.app/files/04-Examen-Completo-For-Schools-02/First%20for%20Schools%202015%20Speaking%20sample%20paper%202.pdf

Para cada uno:

- Extraer el texto real con `pdftotext -layout` y transcribir **literal** las instrucciones del interlocutor, las preguntas de Part 1 y Part 4, los prompts de Part 2 y las consignas de Part 3. No inventar preguntas.
- Extraer las imágenes de Part 2 (dos pares de fotos por test) y la tarjeta de Part 3 con `pdfimages`/`pdftoppm` + recorte. Guardar en `assets/speaking/exams/<01..04>/`.
- Verificar visualmente cada imagen recortada: solo fotos/tarjeta, sin texto del examiner, sin bordes de página. Si un recorte muestra texto de guion, está mal.
- La tarjeta de Part 3 sí puede tener texto (es lo que el candidato ve en la vida real). Part 2 solo fotos.
- Guardar metadatos en `material/speaking/tests/01.json` … `04.json`: id, título (“B2 First Sample Paper 1”, etc.), variante, partner_name, imágenes, y el guion completo por partes.
- Créditos: `assets/speaking/exams/CREDITS.md` indicando Cambridge sample papers y que se usan para práctica personal; no redistribuir como propios.
- Nada de transcripciones de audio en el contenido ni en las respuestas.

## 2. Intro obligatoria (siempre, incluso Part 4)

Estado `intro`, fuera del timer de examen:

1. Examiner (TTS): saludo según hora local del servidor/usuario + “My name is Mr Thompson.”
2. Examiner: “And your names are?”
3. Usuario responde por micrófono. **Analizar semánticamente**: acepta “Juan”, “My name is Juan”, “I’m Juan”, nombre + apellido. Si dice otra cosa (ej. “I like pizza”), el examiner responde con la frase formal canónica: “I beg your pardon. I didn’t quite hear your name. Would you mind repeating it?” y reintenta. Máximo 2 reintentos; si sigue mal, avanza y registra `name_ok=false` para el reporte.
4. Partner (voz distinta, IA): dice su nombre (“I’m Alex.” / el que corresponda al test) **después** de que habló el usuario.
5. Examiner: “Where do you live, <nombre usuario>?”
6. Usuario responde; validar que sea ciudad/país/zona (“I live in Buenos Aires”, “Buenos Aires”, “Argentina”). Si no, repregunta formal (“I beg your pardon. I didn’t quite hear where you live. Would you mind repeating that?”), máximo 2. Registra `home_ok`.
7. Examiner: “And you, <partner>?” → partner responde con su ciudad fija.
8. Recién ahí: si el usuario eligió una parte, saltar directo a esa parte. Si es full, empezar Part 1.

El examiner **examina también al partner**: en Part 1 y Part 4 el partner responde las mismas preguntas cuando corresponde; en Part 3 colabora. El partner no es perfecto: puede discrepar, dudar o cambiar de opinión, pero responde correcto y natural (B2).

## 3. Partes y tiempos

- Part 1: 2 min. Preguntas de “Likes and dislikes / Special occasions / Media” (First) o “People you know / Things you like / Places you go to” (For Schools). Elegir 3–4 preguntas del PDF; alternar usuario y partner.
- Part 2: 4 min. Usuario 1 min con sus fotos + pregunta del partner 30 s; partner 1 min con sus fotos + pregunta al usuario 30 s. El examiner lee las instrucciones literales del PDF y da “All right?”. El usuario ve solo las fotos de su turno (y las del partner cuando corresponde, como en la vida real).
- Part 3: 4 min. 15 s para mirar la tarjeta; 2 min de discusión usuario↔partner; 1 min para decidir los dos puntos más importantes. El examiner abre y cierra con las frases del PDF.
- Part 4: 4 min. Preguntas de discusión del PDF, alternando usuario y partner.
- Single part: después de la intro, solo esa parte. Full: 1→2→3→4 continuo, con transiciones del examiner.
- Timer por parte, empieza al comenzar la parte (no en intro). Al agotarse, el examiner cierra la parte con una frase natural y pasa a la siguiente (full) o termina.

## 4. Validación de TODO lo que dice el usuario

Cada turno de audio se transcribe y se analiza antes de responder:

- Si la respuesta no contesta la pregunta (nombre, ciudad, pregunta de Part 1/4, o aporte en Part 3), el examiner **no la acepta**: repregunta o pide aclaración de forma natural, máximo 2 veces; luego sigue y lo marca en el reporte.
- Si el usuario habla en español u otro idioma, el examiner pide en inglés formal que repita en inglés (“I’m afraid I didn’t understand. Would you mind repeating that in English?”).
- Si hay silencio o audio vacío: “Take your time. Do let me know when you’re ready.” y reintenta; no inventar respuesta.
- En Part 2 el usuario habla hasta 1 min: no interrumpir por validez; al terminar, si no comparó las fotos, el examiner puede hacer una follow-up (“Which photo shows…?”).
- Guardar solo banderas booleanas/contadores (`name_ok`, `home_ok`, `off_topic_turns`), nunca transcript ni audio.

## 5. Voz y audio

- STT: Gemini (modelo actual del repo) acepta audio del turno; normalizar con ffmpeg si está disponible. No guardar audio.
- TTS: examiner y partner con voces distintas (Gemini TTS). Cachear en disco solo líneas fijas (saludo, instrucciones, transiciones) para latencia/costo; nunca cachear audio del usuario.
- Push-to-talk: el cliente manda un blob por turno. El servidor devuelve audio del siguiente hablante en base64 (o URL temporal), `speaker` y estado.
- Fallback sin key: Web Speech API en el cliente (la fase UI lo implementa); el backend debe responder `speech_not_configured` claro, no simular audio.
- Eliminar Azure Pronunciation Assessment y todo el endpoint `/api/speaking/pa`. Sin pronunciación en el reporte.
- Eliminar Live Studio / WebSocket / `/api/speaking/token` / `/api/speaking/capabilities` / modo live. Un solo transporte turn-based.

## 6. API nueva (contrato para la fase UI)

Diseñar limpio, versionado en `/api/speaking/v3/...`:

- `GET /api/speaking/v3/catalog` → `{tests:[{id,title,variant,partner,parts:[1,2,3,4]}], own_tasks:[...]}`. Sin guiones ni respuestas.
- `POST /api/speaking/v3/sessions` `{test_id, part: 1|2|3|4|0, own_task_id?}` → `{session_id, speaker:"examiner", audio_b64, state:{phase:"intro",step:"greeting"}, ui:{part, timer_seconds, images:[], card:null}}`. `part:0` = full.
- `POST /api/speaking/v3/sessions/<id>/turn` `{audio_b64, mime}` → `{accepted, retry, speaker, audio_b64, state, ui, done}`. `accepted:false` = respuesta inválida y el examiner repreguntó. Nunca devolver transcript al cliente.
- `POST /api/speaking/v3/sessions/<id>/skip` (solo si micrófono no disponible, para no bloquear la demo) → avanza con frase natural, marca `skipped`.
- `POST /api/speaking/v3/sessions/<id>/report` → bands `{grammar_vocabulary, discourse, interactive}` 0–5 + comentarios; sin pronunciación. Guardar solo si el cliente pide `save:true`.
- `DELETE /api/speaking/v3/sessions/<id>`.
- Own task: `POST /api/speaking/v3/own-tasks` multipart/form-data con campos de formulario (no JSON técnico): `title`, `part` (1–4 o full), `questions` (una por línea), `prompt`, `discussion`, `decision`, `images[]`. Validar tamaño/tipo; devolver id. `GET` lista; `DELETE`.
- Sesiones persistidas en `data/speaking_v3/sessions/<id>.json` con estado y banderas, sin audio/transcript. Expirar a las 24 h.

Límites de cuota actuales (3 mocks/45 min por día, owner sin tope, guard mensual 900 min) se mantienen. Un single part consume 1 mock; full consume 1; own task igual.

## 7. Borrado de lo viejo y del historial

- Eliminar del backend: rutas viejas `/api/speaking/{turn,partner,report,minute,token,capabilities,pa}`, Live/WebSocket, Azure PA, `speaking_prompts.py`, `speaking_report.py` si quedan obsoletos, y tests viejos de esas features.
- Crear `tools/purge_speaking_history.py`: hace backup `data/.backup-speaking-<timestamp>.tar.gz` y luego elimina de cada `data/users/*/progress.json` las claves `speaking` y `spxCustom`; borra `data/speaking*` viejo (no `speaking_v3`). Ejecutarlo una vez y reportar cuántos usuarios tocó.
- No borrar cuentas ni progreso no-speaking.

## 8. Tests (obligatorio)

Tests propios, sin depender de micrófono físico:

- `test_speaking_v3_intro.py`: saludo→nombres→usuario válido→partner→where live→usuario válido→partner→parte elegida. Incluye respuesta inválida (“I like pizza”) y verifica repregunta + reintento + flag.
- `test_speaking_v3_parts.py`: single Part 2 salta directo tras intro; full recorre 1→2→3→4; timings configurados; imágenes correctas por test; sin texto de guion en las imágenes.
- `test_speaking_v3_validation.py`: off-topic, español, silencio, reintentos máximos, partner responde después del usuario.
- `test_speaking_v3_own_task.py`: form multipart, validación por parte, ejecución single/full; no requiere JSON.
- `test_speaking_v3_privacy.py`: turn no devuelve transcript; archivos de sesión no contienen audio/transcript; reporte sin pronunciación; historial viejo borrado.
- `test_speaking_v3_catalog.py`: exactamente 4 tests, títulos, partner, 4 partes cada uno, assets existen y no contienen texto de examiner.
- `test_speaking_v3_tone.py`: recorrer TODAS las líneas del examiner en los 4 guiones y en las respuestas de validación. Fallar si aparece cualquier término prohibido (`catch` (cualquier forma), `Could you please repeat the question?`, `Pardon?` solo, `Okay`, `OK`, `Hi`, `Hey`, `gonna`, `wanna`, `stuff`, `guys`, `gotten`, `mom`, `math`, `vacation`, `fall`, `sidewalk`, `soccer`, `color`, `organize`, `Excellent!`, `Well done!`), si hay spelling americano, o si las frases de reintento no son las canónicas. El partner queda exento del registro formal, pero no de las reglas de idioma.
- Tests con proveedor stub/offline; audio WAV sintético o `X-Test-Transcript` solo en modo test. Nada de red real.

Usar `uv run --no-project --with playwright --with httpx` si hace falta. Todos exit 0.

## 9. Entregable

- Commit(s) en la rama actual. **No deploy.**
- Resumen: archivos nuevos/borrados, contrato final exacto (campos JSON), cantidad de usuarios cuyo historial se borró, tests con exit code, y cualquier limitación real (ej. TTS sin key).
- No tocar la UI todavía; si `index.html` queda llamando rutas viejas, es esperado y se arregla en la fase siguiente.
