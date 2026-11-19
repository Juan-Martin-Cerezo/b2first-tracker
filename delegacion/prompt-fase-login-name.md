# Fase login-name — el ejemplo del login no puede decir "Owner"

Repo: `/home/juan/b2first-tracker`. Base: HEAD `e2e7af3`.

Juan pidió: "De ejemplo de nombre en el login no puede ser owner, decí que simplemente ingrese nombre". Hoy el input `#authName` muestra `e.g. Owner` (clave i18n `auth_ph_owner`).

## Qué cambiar

- `index.html`: valor de `auth_ph_owner` en inglés → `Your name` y en español → `Tu nombre`. Están en el bloque i18n EN (~línea 5011) y ES (~línea 5938).
- Si hay otra locale con esa clave, actualizarla también con equivalente neutro ("Your name").
- No cambiar el label "User name", ni el `id`, ni el `data-i18n-placeholder`, ni la lógica de auth.

## Verificación

```bash
cd /home/juan/b2first-tracker
grep -n "auth_ph_owner" index.html         # sin "Owner" en los valores
grep -ci "e\.g\. owner" index.html          # 0

cd tests
uv run --no-project --quiet --with playwright --with httpx python test_auth_methods.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
```

Ambos exit=0. Captura del login abierto (`/app` sin sesión) y confirmar visualmente que el placeholder dice "Your name" / "Tu nombre", no "Owner".

## Cierre

Commit `fix(auth): placeholder de usuario genérico en el login`. Árbol limpio. Sin deploy.
