# Fase cloudflare-analytics — permitir el beacon de Cloudflare y decir la verdad en el copy

Repo: `/home/juan/b2first-tracker`. Base: HEAD `82f0187`.

Juan quiere mantener Cloudflare Web Analytics, que hoy está bloqueado por CSP: en producción aparece `Loading the script 'https://static.cloudflareinsights.com/beacon.min.js/...' violates ... script-src`. Cloudflare inyecta ese script en el borde, así que no está en `landing.html` ni en `index.html`.

Además el copy actual dice "Zero analytics SDKs" y "sin third-party analytics", lo que deja de ser cierto. Hay que declararlo con precisión: analítica agregada de Cloudflare, sin cookies, sin ads.

## Qué cambiar

1. `server.py`, `CSP_TEMPLATE` (~línea 3926):
   - Agregar `https://static.cloudflareinsights.com` a `script-src`.
   - Agregar `https://cloudflareinsights.com https://static.cloudflareinsights.com` a `connect-src` (el beacon manda el POST a cloudflareinsights.com).
   - Quitar `'strict-dynamic'` de `script-src`: con `strict-dynamic` el navegador ignora las allowlists de host y el beacon seguiría bloqueado. Se mantienen `'self'` y los hashes sha256 de los bloques inline.
   - Actualizar los comentarios de arriba para explicar por qué el host está permitido y que no hay otros scripts externos.
2. `landing.html` (~1095-1096):
   - Título: `No ad trackers, no CDNs`.
   - Texto: dejar claro que la única analítica es la agregada y sin cookies de Cloudflare (páginas vistas, país, referrer), que no perfila al usuario y que no hay ads, pixels ni fuentes externas.
3. `README.md`, sección de privacidad (buscá "No advertising trackers" o similar): misma aclaración en una línea.
4. `tests/test_csp.py` y cualquier test que assertee el CSP (`tests/test_security3.py`, `tests/test_hardening.py`): actualizar lo que haga falta para que el CSP nuevo sea el esperado. Si un test exige `'strict-dynamic'`, se cambia por el contrato nuevo: `'self'`, hashes, y el host de Cloudflare en script-src/connect-src. Nunca borrar el assert: invertirlo o ajustarlo.
5. Si `tests/test_landing_honest.py` cuenta scripts externos o URLs, verificá que sigue pasando (el beacon no está en el archivo, no debería afectar).

## Reglas

- No agregar ningún otro origen externo al CSP.
- No tocar `plans.py`, límites, onboarding ni la lógica de speaking.
- El copy no puede prometer "zero analytics": tiene que declarar Cloudflare aggregate.
- Español neutro en comentarios, inglés en el copy del producto.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_csp.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_security3.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_hardening.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_landing.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_landing_honest.py; echo exit=$?
```

Los cinco exit=0.

Después del restart lo verifico yo: en producción no debe quedar el error de CSP y el beacon tiene que cargar (o al menos no ser bloqueado).

## Cierre

Commit `feat(privacy): permitir la analítica agregada de Cloudflare en el CSP`. Sin deploy.
