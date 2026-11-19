# Fase test-landing-claim — alinear el chequeo con el copy real de la landing

Repo: `/home/juan/b2first-tracker`. Base: HEAD `e034428`.

`tests/test_readme_limits.py` línea 66 exige la cadena `"It is practice, not a certificate"` en `landing.html`. Ese texto ya no existe con esa redacción: la landing dice `Practice, not a certificate:` (línea 908, dentro de un `<b>`), que es la misma afirmación. El test está desactualizado, no el copy.

## Qué cambiar

- `tests/test_readme_limits.py`: reemplazar esa cadena por `"Practice, not a certificate"`, sin tocar el nombre del check (`landing_agrees`) ni ningún otro assert.
- Nada más.

## Verificación

```bash
cd /home/juan/b2first-tracker/tests
uv run --no-project --quiet --with httpx python test_readme_limits.py; echo exit=$?
```

exit=0 y `FAILED` vacío.

## Cierre

Commit `test(readme): alinear el chequeo con el copy de la landing`. Sin deploy.
