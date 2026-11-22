# Fase practice-flow — un recorrido por intención, recursos exactos y speaking legible

Repo: `/home/juan/b2first-tracker`, base HEAD `ad11598`.

## Pedido del dueño (textual)

1. En `firsttracker.app`, **abajo del contador de los mocks** tiene que haber un acceso a la **Library con exacto lo que necesitás para hacer ese mock**.
2. Cuando apretás **Practice normal no aparece la Library**: hay inconsistencias y el usuario no encuentra cómo practicar.
3. Rediseñar **todo el mecanismo que lleva al usuario a practicar con los recursos correctos**, con **recursos ilimitados** (ofreciendo páginas online).
4. Pensar la experiencia para dos intenciones: **full mock** y **by part**.
5. Un **full mock no puede terminar en “solo 2 mocks y después nada”**: al terminarlo tiene que poder hacer otro (otra muestra u otro mock online), sin callejón sin salida.
6. **Speaking no funciona nada bien**: las preguntas no son coherentes, no se entiende cuándo habla el partner y cuándo vos, y a veces se confunden los turnos.
7. **Sacar los transcripts del speaking**: en un examen real no ves la transcripción.

## Regla de producto (una sola promesa)

> Elegís una intención (full mock o una parte) y **siempre** aterrizás en los recursos exactos para hacerla, con una salida online cuando se acaban los locales. Nunca una pantalla que sólo diga “no hay más”.

### Intención A — Full mock

Al tocar “Full mock” (o “Start full mock”) NO se arranca el cronómetro a ciegas. Se abre una **pre-flight** con:

- Las 4 pruebas en orden oficial (R&UoE 75′ → Writing 80′ → Listening 40′ → Speaking 14′), cada una con “Abrir materiales” que lleva a la Library **filtrada a esa prueba y a ítems de paper completo** (paper + key + audio + speaking cards).
- Selector de muestra: Standard 1, Standard 2, For Schools 1, For Schools 2 (las que existan en `libros.json`; no inventar archivos).
- Sección **“Más full mocks online (gratis)”** con al menos 4 tests completos de `PRACTICE_SOURCES` (Exam English test 1/2, Test-English, Cambridge preparation). Abren en pestaña nueva.
- Botón “Empezar secuencia 195′”.
- Al terminar (o al volver), el mismo bloque ofrece **“Hacer otro full mock”** con las muestras restantes y los online. Nunca un texto de “ya no tenés más mocks”.
- El contador de mocks de la izquierda/hoy (`This cycle`, `todayCycleValue`) pasa a ser un **botón/link** que abre la Library filtrada por la destreza/parte de ese contador, no texto muerto.
- Las tarjetas de paper de “Real mocks” dejan de ser un link genérico: cada una lleva a la Library con `paper` + ítems de paper completo; y los links de parte (si se agregan) con la parte exacta.

Regla de límites: los **recursos gratuitos son ilimitados** (no hay tope de Library ni de links online). Los **mocks con voz AI** siguen medidos por costo: mostrar minutos/mocks restantes antes de empezar y la opción de key propia; nunca bloquear el mock escrito ni los recursos online. Subir el servicio de `DAY_SPEAKING_MOCKS` de 1 a 3 y `DAY_SPEAKING_MINUTES` de 15 a 45 (el guard mensual global de 900 min sigue igual). Owner sigue sin tope.

### Intención B — By part

- En `#v-practice`, **la Library tiene que verse siempre**, debajo de “Exercises by part”, sin tab oculto ni botón extra. Refactorizar `renderExercisesLibrary()` para renderizar en un root parametrizable y reusarlo en Practice y en la pestaña Contents de la sesión (ids duplicados prohibidos; usar `data-*` o un parámetro `rootId`).
- Al tocar “Start” de una parte, la sesión abre **en Contents**, no en Session. Contents muestra, en este orden: paper local de esa parte → answer key → audio/tapescript (Listening) → lesson plan → **2–4 fuentes online de esa parte** (`PRACTICE_SOURCES` filtrado por `skill`+`part`), y un primario “Practicar online” que abre en pestaña nueva.
- “Practise now” de Today y los paneles de Materials usan el mismo filtro exacto (parte primero, genéricas después) y su link “More in Library” abre la Library ya filtrada por esa parte.
- El usuario nunca tiene que adivinar: cada fila de parte de Practice muestra debajo un mini-resumen (“Paper + key + audio + N online”) y cuántos recursos tiene.

## Speaking — rediseño de turnos y coherencia

### Problema real

- El examiner improvisa preguntas fuera del task; el partner y el candidato se mezclan; no hay una señal inequívoca de quién habla; el reporte imprime transcripción que en un examen no existe.

### Cambios obligatorios

1. **Tres roles visualmente distintos y nombrados**: `EXAMINER` (izquierda, color marca), `PARTNER` (derecha, ámbar), `YOU` (centro/verde). Cada línea/burbuja lleva el nombre del rol. Nunca dos roles “activos” a la vez.
2. **Un solo micrófono activo por turno**: mientras habla examiner o partner, el micrófono está cerrado y el botón dice “Escuchá”. Cuando es tu turno: estado “TU TURNO”, countdown visible y botón “Hablar”. El partner **nunca** se transcribe ni se atribuye al candidato.
3. **Guion determinístico por parte** desde `material/speaking.json` + `speaking_prompts.py`:
   - Part 1: examiner, preguntas fijas por tema, una por turno.
   - Part 2: instrucción del examiner → 1′ prep → 2′ long turn tuyo → pregunta corta del partner.
   - Part 3: examiner describe la tarea → **el partner abre la discusión** con una línea del banco → alternancia partner/vos con timer de 2′ → decisión 1′.
   - Part 4: examiner alterna preguntas dirigidas (“Partner, …” / “You, …”), con banco de follow-ups por tema.
4. **Coherencia**: el reply del examiner/partner sólo puede salir del banco del parte y tema actual. Si el modelo devuelve algo fuera de tema o vacío, usar el **fallback scripted** de esa parte. Validación simple por tema/palabras clave; nada de preguntas nuevas inventadas. El server (`speaking_prompts.py` y el system prompt de `/api/speaking/turn`) debe reforzar “no cambies de parte ni de tema”.
5. **Sacar TODOS los transcripts visibles del speaking**: eliminar `#spxTx`, `#spxRpTxWrap`/`#spxRpTx`, botón Copy, `spxTranscriptLines/Text/RenderReportTranscript`, `SP_EXAM.copyTranscript`, el bloque `.spk-transcript` del Live Studio y las claves i18n `spx_rp_transcript`, `spx_transcript`, `spx_copy`, `spx_aria_copy`. El transcript interno se sigue usando para puntuar, pero **no se renderiza, no se copia y no se guarda**.
6. **Reporte sin texto del candidato**: bands + un comentario por parte + un tip. Sin quotes, sin “full transcript”. Pronunciación: si no hay proveedor, mostrar “No medida” una sola vez con explicación corta, no un hueco que parezca roto.
7. **Live Studio**: sin transcript; sólo HUD de turnos/tiempos.

## Alcance técnico

- `index.html` (UI, estado, i18n EN/ES simétrico, handlers `data-action`, sin handlers inline), `plans.py` (subir límites de servicio), `speaking_prompts.py`, `server.py` (system prompt/validación del turno), `material/speaking.json` sólo si falta el guion de partner, `tests/`.
- NO tocar: landing, auth, billing, CSP, OAuth, wordlist, deploy, diseño global fuera de estas pantallas.
- Sin dependencias nuevas. Sin APIs pagas nuevas. Español para UI es-AR, código/UI keys en inglés.

## Tests obligatorios (nuevos y actualizados)

Crear `tests/test_practice_flow.py`:
1. `#v-practice` contiene la Library visible sin clicks, con contador y filas.
2. Start de Reading Part 2 abre sesión en Contents y lista paper + key + al menos 2 fuentes online de la parte 2; ninguna fuente de otra parte.
3. El contador de Today es clickeable y abre Library filtrada por su destreza.
4. En Exam, “Start full mock” abre pre-flight (no countdown directo) con las 4 pruebas, selector de muestras y al menos 4 full mocks online; existe “Hacer otro full mock” después de terminar.
5. Full mock ofrece materiales exactos por prueba (paper + key + audio) y no muestra “no hay más”.
6. 390×844 sin overflow; EN/ES con el mismo contenido; sin ids duplicados de Library.

Crear/actualizar `tests/test_speaking_turns.py`:
1. Secuencia de roles por parte: examiner → (partner) → you, con un solo rol activo y el nombre visible en cada turno.
2. Micrófono cerrado mientras hablan examiner/partner; “TU TURNO” sólo en el turno del candidato.
3. Partner nunca aparece como “You” ni contamina el reporte.
4. Follow-up fuera de tema se reemplaza por el fallback del banco (stub).
5. No existe ningún nodo de transcript en speaking ni en el reporte; no hay Copy; no se guarda texto en `data/`.
6. Full Part 2 sim termina con bands y sin texto del candidato.

Actualizar los tests de speaking existentes que asserten `#spxTx`/transcript, y `test_plan*`/`test_readme*` si cambian los límites.

Verificación obligatoria (todas deben salir 0):

```bash
cd /home/juan/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_practice_flow.py
uv run --no-project --quiet --with playwright --with httpx python test_speaking_turns.py
uv run --no-project --quiet --with playwright --with httpx python test_exercise_library.py
uv run --no-project --quiet --with playwright --with httpx python test_start_contents.py
uv run --no-project --quiet --with playwright --with httpx python test_practice_split.py
uv run --no-project --quiet --with playwright --with httpx python test_dedupe_exam.py
uv run --no-project --quiet --with playwright --with httpx python test_mobile.py
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py
uv run --no-project --quiet --with playwright --with httpx python test_speaking_exam.py
uv run --no-project --quiet --with playwright --with httpx python test_speaking_v2.py
uv run --no-project --quiet --with playwright --with httpx python test_speaking_report.py
uv run --no-project --quiet --with playwright --with httpx python test_plan.py
python3 -m py_compile server.py speaking_prompts.py speaking_report.py plans.py
```

Capturas nuevas en `tests/out/`: `practice_library_390_light.png`, `full_mock_preflight_390_light.png`, `speaking_roles_390_light.png`, `speaking_roles_1280_light.png`, `practice_library_390_dark.png`.

## Cierre

Dos commits, en este orden, sin deploy:
1. `feat(practice): intención → recursos exactos, Library siempre visible y full mock sin callejón`
2. `fix(speaking): turnos inequívocos, guion por parte y sin transcripciones`

Si algo del pedido no se puede verificar sin micrófono real, dejarlo documentado en el resumen con el test que lo cubre con stub; no inventar evidencia.
