# Fase part4-seq — el examiner de Part 4 avanza, no repite

Repo: `/home/juan/b2first-tracker`. Base: HEAD `f3d0373`.

Prueba real en producción (audio TTS 16 kHz, `/api/speaking/turn`, part 4, tarea `p4-01` "School trips"):
- Candidato: "I think school trips are really useful because you remember what you see much better than what you read. Last year we visited a museum and I finally understood the history lesson."
- Reply del examiner: **"So you think school trips are useful. Why are they useful?"** → repite lo que el candidato ya explicó. En un examen real el examiner pasa a la siguiente pregunta de la tarea ("Should parents pay for school trips, or should the school pay?").

## Objetivo

En `speaking_prompts.py`, el prompt del examiner para Part 4 (modo turnos, `role="examiner"`) debe:
1. Llevar registro de las preguntas ya hechas (el historial ya viaja en `contents`).
2. Preguntar la **siguiente pregunta de `task["questions"]` que todavía no se hizo**, en orden.
3. No pedir que el candidato justifique algo que ya justificó; no reformular la misma pregunta.
4. Si ya se hicieron todas, cerrar con la fórmula de cierre de Part 4 ("Thank you. That is the end of the speaking test.") y no inventar una nueva.
5. Máximo 20 palabras por línea, sin elogios ni correcciones.

Mismo criterio para Part 1: si el candidato ya respondió, el examiner pasa a la próxima pregunta de la lista, no repite.

## Reglas

- Solo `speaking_prompts.py` y tests de speaking. No tocar UI, server, límites ni cuentas.
- No cambiar el contrato del turno ni el de partner.
- Mantener las líneas de cierre y las instrucciones de parte tal como están.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_speaking_v2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_exam.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_custom_task.py; echo exit=$?
```

Test nuevo `tests/test_speaking_part4_sequence.py` (offline, stub): con historial que ya contiene "Why do you think school trips are useful?" y una respuesta del candidato, el system prompt que sale hacia el modelo (a) nombra la siguiente pregunta de `task["questions"]`, (b) no contiene "Why are they useful", (c) mantiene el límite de 20 palabras.

## Cierre

Commit `fix(speaking): el examiner avanza por las preguntas de la tarea`. Sin deploy.
