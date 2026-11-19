# Fase test-gates-2 — actualizar el texto explicativo de la matriz

Repo: `/home/juan/b2first-tracker`. Base: HEAD `0618545`.

`tests/test_ui_batch2.py` línea ~199 sigue esperando el texto viejo "Complete all criteria within a stage to advance.", que ya no existe: la vista renderiza "Complete all gates within your current stage to unlock the next one automatically." (verificado en el DOM real).

## Qué cambiar

- `tests/test_ui_batch2.py`: reemplazar únicamente esa cadena por `"Complete all gates within your current stage to unlock the next one automatically."`.
- Nada más.

## Verificación

```bash
cd /home/juan/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
```

exit=0 obligatorio. Si falla otro check, no lo toques: reportá línea y mensaje.

## Cierre

Commit `test(prog): actualizar el texto de la matriz de etapas`. Sin deploy.
