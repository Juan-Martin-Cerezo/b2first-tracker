# Fase eyebrow — borrar el texto "Cambridge B2 First · AI feedback" del hero

Repo: `/home/juan/b2first-tracker`. Base: HEAD `dcb2df4`.

Juan pidió: "borra ese textito de Cambridge B2 First · AI feedback". Es el `<p class="eyebrow">Cambridge B2 First · AI feedback</p>` del hero, el único eyebrow sin punto.

## Qué cambiar

- `landing.html`: eliminar ese `<p>` completo del hero (no el resto de los eyebrows, que quedan igual: "Core AI & Adaptive Engine", "Under the hood", "Privacy", "FAQ").
- Si al sacarlo queda un hueco o margen raro arriba del `<h1>`, ajustar solo el margen del hero para que el título quede prolijo. Nada de rediseño.
- Nada más.

## Verificación

```bash
cd /home/juan/b2first-tracker
grep -c 'Cambridge B2 First · AI feedback' landing.html   # 0
grep -c '<h1' landing.html                                # 1

cd tests
uv run --no-project --quiet --with playwright --with httpx python test_landing.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_landing_honest.py; echo exit=$?
```

Ambos exit=0. Mirar `tests/out/landing-360x740-light.png` y `tests/out/landing-1280x800-dark.png`: el h1 debe arrancar sin aire de más ni pegado al borde.

## Cierre

Commit `style(landing): sacar el eyebrow del hero`. Árbol limpio. Sin deploy.
