# Fase part4-seq-2 — la regla del turno pisa al examiner

Repo: `/home/juan/b2first-tracker`, HEAD `b323386`.

Probado en producción, Part 4, tarea `p4-01`, `role="examiner"`, audio real:
- Candidato: "School trips are useful because you remember what you see much better than what you read…"
- Reply: **"You think school trips are useful. Why are they useful for students?"** — repite la pregunta 1 de la tarea con otras palabras.

Causa: `server.py`, `_SPK_TURN_RULE` (~1527) le dice al modelo "The scripted question list is a FALLBACK for silence, not a script to read" y "Never ask a question that could have been asked without listening", además de REACT FIRST. Eso gana sobre cualquier cambio en `speaking_prompts.py`.

## Cambio

Editar **solo `_SPK_TURN_RULE`** en `server.py` (y el test nuevo). Mantener:
- transcribir literal, no inventar;
- respuesta ≤ 10 palabras, en inglés;
- reaccionar a una palabra concreta de lo que dijo el candidato;
- silencio → pedir que repita.

Agregar, para `part` 1 y 4 (el system prompt ya trae la lista de `task["questions"]`):
- Si el candidato respondió la pregunta en curso (≥ 4 palabras, on-topic), la próxima línea **avanza a la siguiente pregunta de la lista que todavía no se hizo**, en orden, y la formula corta. Puede empezar con 2-3 palabras que retomen lo dicho ("Right, so school trips stick — should parents pay for them?").
- Prohibido reformular la pregunta que el candidato acaba de responder ("Why are they useful for students?" después de que ya explicó por qué) y prohibido encadenar "Why?" sobre lo mismo.
- Si ya se hicieron todas las preguntas de la lista, cerrar con la fórmula de cierre de la parte.
- El límite de 10 palabras sigue; si la pregunta de la lista no entra, usar una versión corta fiel.

Para Part 2 y 3 no cambia nada.

## Verificación

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_speaking_v2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_exam.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_custom_task.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_part4_sequence.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_turn_budget.py; echo exit=$?
```

Los 5 exit=0. Ajustar `test_speaking_part4_sequence.py` si verificaba el texto del prompt en `speaking_prompts.py` en vez de `_SPK_TURN_RULE`.

## Cierre

Commit `fix(speaking): la regla del turno avanza por la lista de preguntas`. Sin deploy.
