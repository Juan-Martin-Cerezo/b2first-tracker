# Fase test-gates — actualizar selector viejo de la matriz de etapas

Repo: `/home/juan/b2first-tracker`. Base: HEAD `0d9c984`.

`tests/test_ui_batch2.py` línea 196 todavía busca `#gates tbody tr`, pero el commit `4ca32fe` reemplazó la tabla por tarjetas `.gate-stage-card` en `index.html` (contenedor `#gates`, render en `index.html:15056`). El test falla en el check 6 por eso.

## Qué cambiar

- `tests/test_ui_batch2.py`, solo el assert de la línea 196: contar `#gates .gate-stage-card` y seguir esperando 3 (una tarjeta por etapa). Mensaje de error: "the matrix does not have one card per stage".
- Nada más. No tocar `index.html`, ni `landing.html`, ni otro assert.

## Verificación

```bash
cd /home/juan/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
```

Debe salir exit=0. Si falla otro check, NO lo arregles: reportalo con la línea exacta.

## Cierre

Commit `test(prog): contar las tarjetas de etapa en la matriz`. Árbol limpio. Sin deploy.
