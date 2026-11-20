# Fase copy-showcase — landing y textos dentro de la app

Repo: `/home/juan/b2first-tracker`, HEAD tras la fase docs-showcase.

## Objetivo

Dejar **todo el texto visible** (landing y app) al nivel de presentación para el hackatón: mismo tono, sin claims viejos, sin restos de features eliminadas, EN/ES simétrico y metadata lista para compartir.

## 1. landing.html

Reescribir el copy (no el diseño ni el CSS salvo ajustes mínimos) con esta estructura:

- **Hero**: titular claro + subtítulo de una línea + CTA "Start free" y secundario "See how it marks". Badge chico: "Free while in beta".
- **How it works** en 3 pasos: 1) It plans today's session from your diagnostic and your log. 2) You write or speak; the AI marks it against the Cambridge bands and quotes your own sentences. 3) The plan adjusts tomorrow from what you actually did.
- **AI features** (4 tarjetas): Writing corrector, AI examiner (4 parts + partner + your own task), Live Studio (silences and speaking time, VAD local), Adaptive plan and variety engine (157 real exercises, no repeats).
- **Materials**: sample papers with keys, full papers, official online sources — all one tap away.
- **Privacy**: audio never leaves the tab for Live Studio; keys server-side; no ad trackers. Coherente con `docs/PRIVACY.md`.
- **Pricing**: free in beta, one account, no card.
- **FAQ** (5–6): Is it really Cambridge format? Does the AI replace a teacher? Do you store my audio? Can I use my own tasks? What does it cost? Does it work on a phone?
- **Footer**: links a Privacy, Terms, Security, GitHub.

Además:
- `<title>`, `meta description`, `og:*`, `twitter:card`, canonical y `JSON-LD` `SoftwareApplication` con nombre, URL, precio 0, categoría EducationApplication.
- Copy en inglés; el toggle ES de la landing debe quedar completo y natural (no traducción literal).
- Sin testimonios inventados, sin métricas falsas, sin "zero analytics".

## 2. Textos dentro de la app (index.html, solo strings)

- Revisar las claves de `I18N.en` / `I18N.es`: mismas claves, mismo significado, sin inglés en la versión ES ni al revés.
- Eliminar referencias a cosas que ya no existen (por ejemplo "Phase 2 · C1 Polish", "Live examiner" duplicado, selects viejos de Speaking) y a límites o features desactualizadas.
- Unificar estilo: sentence case en botones y títulos, sin dobles espacios, sin signos de exclamación múltiples, sin emojis fuera de los que ya usa la app.
- Revisar las cadenas de estados del corrector, del examen de speaking y de los materiales nuevos para que suenen a producto, no a debug ("correcting…" puede quedar, "idle" no: reemplazar por "Ready" / "Listo").

## 3. Fuera de la app

- `README.md`: si la fase anterior dejó el hero o las features, ajustar solo si el copy de la landing cambió de nombre.
- `docs/REPO-ABOUT.md`: descripción corta alineada con el hero.

## Reglas

- No tocar lógica, endpoints, límites, plan ni tests existentes; si un test depende de un string exacto, actualizarlo junto con el copy (no debilitar asserts).
- Sin handlers inline. Sin dependencias. Sin secretos.
- No romper CSP (`test_csp.py`) ni las suites de landing.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_landing.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_landing_honest.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_no_purchase.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_csp.py; echo exit=$?
```

Capturas: `docs/screenshots/landing.webp` (1280) y `landing-mobile.webp` (390), actualizadas.

## Cierre

Commit `feat(copy): landing y textos de la app listos para presentar`. Sin deploy.
