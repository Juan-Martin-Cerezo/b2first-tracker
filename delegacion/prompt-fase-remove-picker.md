# Fase remove-picker — sacar "Practise a real exercise / Give me one"

Repo: `/home/juan/b2first-tracker`, HEAD `a0254ae`.

## Pedido

Juan no quiere el sistema de ejercicios aleatorios. Sacarlo **de todos lados**: la UI, el estado, las acciones, los textos y la documentación. No dejarlo escondido ni detrás de una flag.

## Alcance

### 1. index.html
Eliminar por completo:
- Los bloques de UI de Today y de Exam: `#practicePicker`, `#examPracticePicker` y todo lo que los rodea (títulos "Practise a real exercise", "Give me one", tarjeta del ejercicio, "Give me another", "Mark as done", selectores de paper/parte que solo existían para eso).
- Las funciones `exercisePool`, `pickExercise`, el historial `D.pick`, y todo el código de render/asociación de esos bloques (eventos, helpers, CSS específico).
- Las entradas de `ACTIONS`/delegación y las claves i18n que quedaron huérfanas (`practice_*`, `exam_pick_*`, `pick_*`, "Give me one", "Practise a real exercise", "Give me another", "Mark as done", hints asociados).
- No tocar: materiales en bloques colapsables (paper + keys, Full paper, Online), fuentes en Exam con buscador, Real mocks, plan, límites, corrector, speaking, listening propio.

### 2. Tests
- Borrar `tests/test_practice_variety.py`.
- Revisar los tests que lo mencionen o que naveguen por esos bloques (por ejemplo `test_ui_batch2.py`, `test_today_compact.py`, `test_exam_sources_blocks.py`, `test_where_to_find.py`, `test_index_handlers_exist.py`) y ajustarlos al contrato sin picker. No debilitar asserts que no tengan que ver.

### 3. Documentación y copy
- `README.md`: quitar el bullet de "Non-repeating practice variety engine" y las referencias a "157 exercises" / "non-repeating exercise picker" (incluido el alt/caption de la captura de Today). Si la captura muestra el picker, regenerarla sin él.
- `landing.html`: quitar la mención "157 exercises · no repeats" y cualquier texto que prometa variedad infinita o aleatoria.
- `docs/`: cualquier mención al pool o al selector.
- Sin cambiar el resto de claims.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_today_compact.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_exam_sources_blocks.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_where_to_find.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_landing_honest.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_readme_limits.py; echo exit=$?
```

Además, comprobar con grep que no quede ninguna referencia:
```bash
grep -rn "Give me one\|Practise a real exercise\|practicePicker\|pickExercise\|exercisePool\|157 exercises" --include=*.html --include=*.md . | grep -v delegacion/
```
Salida vacía.

Capturas actualizadas: `docs/screenshots/today.webp` y `docs/screenshots/exam-sources.webp` sin el bloque eliminado.

## Cierre

Commit `refactor: quitar el selector aleatorio de ejercicios`. Sin deploy.
