# Fase speaking-exam — 4 partes coherentes, partner y tarea propia

Repo: `/home/juan/b2first-tracker`. Base: HEAD `80e6ca0`. Ahora la máquina está sana (load < 1).

Probé las 4 partes en producción con audio real (TTS 16 kHz) y misma `session_id`. Resultados:
- Part 1: transcript fiel, reply "Thank you. Do you work, or are you a student?" → bien.
- Part 2: transcript fiel y luego reply **"Thank you. Your partner will answer in a moment."** → mal: en modo por turnos no hay partner que responda, el examen se queda colgado.
- Part 3: "So where to go is most important. What about how to travel?" → bien.
- Part 4: "You think school trips are useful. What can students learn from travelling?" → bien.
- `POST /api/speaking/partner` con `{part,task,transcript,history}` devuelve 422 `invalid_question`; el contrato real es `{question, topic, candidate_said, mode, candidate_context}`. Revisar y dejar claro.

## Objetivo

### 1. Part 2 sin partner colgado
En `speaking_prompts.py`, `PART2_PARTNER_TURN = "Thank you. Your partner will answer in a moment."` solo debe usarse cuando `role == "partner"`. En el turno del examinador (`role == "examiner"`), después de la comparación el examinador debe preguntar la segunda consigna de la tarea (`task["prompts"][1]`, o "Which of these two ... would you prefer? Why?" si no hay), como en el examen real.

### 2. Tarea propia (custom exam task)
En la pantalla de elección del examen (`SP_EXAM`, pantalla `choose`), agregar por parte la opción **"Use my own task / Usar mi tarea"**:
- Un `details`/panel con un `textarea` donde el usuario pega la consigna en texto (una línea por ítem: para Part 2 dos prompts; Part 3 topic + opciones + decisión; Part 4 hasta 5 preguntas; Part 1 hasta 6 preguntas).
- Validación: mínimo 1 ítem y máximo 16, 300 caracteres por ítem, sin HTML (el server ya sanitiza con `clean_task`, pero el cliente no debe mandar basura). Mensaje de error claro si queda vacío.
- Se guarda por parte en `D.spxCustom` y en `localStorage` (`b2.spxCustom`), con botón "Remove my task / Quitar mi tarea". Al recargar sigue estando.
- Cuando hay tarea propia, la pantalla `brief` y el examen muestran un chip **"Your task"** y usan esa tarea en `task` para `/api/speaking/turn` y `/api/speaking/token`. El resto del flujo no cambia.
- i18n en inglés y español para todo lo nuevo; el texto de la tarea queda en el idioma que pegó el usuario.

### 3. Partner
- Corregir el cliente para mandar el contrato real (`question`, `topic`, `candidate_said`, `mode`, `candidate_context`) en cualquier llamada a `/api/speaking/partner`.
- `tools/speaking_smoke.py`: sumar `--partner` para probar ese endpoint y devolver `{http, ms, line}`.

### 4. Coherencia
- En Part 3 el examinador/partner no debe volver a preguntas de Part 1; en Part 4 debe seguir la pregunta de discusión de la tarea. Revisar los bloques de `speaking_prompts.py` y ajustar solo si el prompt actual no lo garantiza.

## Reglas

- No tocar cuentas, límites, owner, CSP, rotación del plan ni landing.
- No cambiar el contrato de `/api/speaking/turn` (audio_b64, mime, part, session_id, task, role, tts).
- Sin secretos en tests. Nada de audio real en tests automáticos.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_speaking_v2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_exam.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_turn_budget.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
```

Además, test nuevo `tests/test_speaking_custom_task.py` (offline, stub):
1. Con tarea propia cargada, el payload de `/api/speaking/turn` lleva exactamente esa tarea.
2. Part 2 con rol examiner pide `prompts[1]` y **no** contiene "Your partner will answer".
3. `/api/speaking/partner` con `{question,topic,candidate_said,mode}` responde 200 y el payload upstream incluye la pregunta.

## Cierre

Commit `feat(speaking): tarea propia, part 2 sin partner y contrato del partner`. Sin deploy.
