# Fase dot — sacar el punto azul del eyebrow del hero

Repo: `/home/juan/b2first-tracker`. Base: HEAD `3bcdce3`.

Juan pidió: "el puntito azul con Cambridge B2 First · AI feedback sacalo". Es el `<span class="eb-dot">` que precede al texto del eyebrow en el hero.

## Qué cambiar

- `landing.html`, línea ~719: borrar el `<span class="eb-dot" aria-hidden="true"></span>` dejando el texto `Cambridge B2 First · AI feedback` intacto, sin espacio inicial.
- Borrar todas las reglas CSS de `.eb-dot` (aparece 6 veces en total, incluida la del `<span>`): base, dark y media queries. Si alguna regla es compartida con otro selector, dejar ese otro selector.
- Nada más. No tocar otros eyebrows, colores, layout ni textos.

## Verificación

```bash
cd /home/juan/b2first-tracker
grep -c 'eb-dot' landing.html        # 0
grep -c '<h1' landing.html           # 1

cd tests
uv run --no-project --quiet --with playwright --with httpx python test_landing.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_landing_honest.py; echo exit=$?
```

Ambos exit=0. Revisar la captura `tests/out/landing-1280x800-dark.png` y confirmar que el eyebrow arranca con "Cambridge" y no quedó hueco raro.

## Cierre

Commit `style(landing): sacar el punto del eyebrow`. Árbol limpio. Sin deploy.
