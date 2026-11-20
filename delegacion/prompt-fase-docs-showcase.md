# Fase docs-showcase — README y documentación de presentación

Repo: `/home/juan/b2first-tracker`, HEAD `cddc570`.

## Contexto

El proyecto se presenta en el hackatón **Build Your First AI App** de Devpost (deadline 2026-11-27 17:00 EST) y el repo es público (MIT). El README actual es correcto pero plano: sin hero visual, sin capturas del producto actual, sin tabla de funciones de IA, sin quick start real. Hay documentación dispersa en `docs/` con afirmaciones viejas.

## Objetivo

Dejar **todo el texto del repo** (README, docs, metadatos) presentable, coherente y verificado contra el producto real. Sin inventar features ni métricas.

## 1. README.md (reescritura completa, en inglés)

Estructura pedida:

1. **Hero**: logo (`assets/logo-192.png`), título, una línea de tagline ("Practice the Cambridge B2 First with an AI examiner, a writing corrector and a plan that knows what you did yesterday"), badges reales (Live, Python 3.11 stdlib, vanilla JS no build, MIT, tests count, AI: Gemini + DeepSeek), link a la app.
2. **Screenshot gallery**: 3–4 capturas reales del producto actual (Today, Speaking exam, Writing corrector con barra de progreso, Exam sources) en una tabla o `<picture>` responsive. Generarlas con Playwright desde el harness de tests si las existentes no reflejan la UI nueva; guardar en `docs/screenshots/` como webp liviano (<250 KB cada una).
3. **What it does**: 5–6 bullets con las features reales: exam plan diario, writing corrector en 4 bandas con citas, AI examiner Cambridge (4 partes, partner, tarea propia), Live Studio (VAD local, silencios y tiempo), materiales en bloques con claves y full papers, motor de variedad sin repetición (157 ejercicios), progreso por parte y tipo de error.
4. **How the AI is used** (clave para el hackatón): tabla proveedor → tarea → modelo → costo aproximado → fallback. Mencionar que las claves viven server-side, que el usuario puede traer su propia key, y que el audio de Live Studio no se graba (VAD local).
5. **Architecture**: diagrama ASCII o mermaid (browser → server.py stdlib → store.py JSON → Gemini Live / DeepSeek), y tabla de archivos principales con una línea cada uno.
6. **Quick start**: clonar, `python3 server.py`, variables de entorno mínimas, crear cuenta, modo demo si existe. Verificar que los comandos funcionen de verdad en este repo.
7. **Configuration**: tabla de env vars reales (`B2_AI_PROVIDER`, `B2_AI_MODEL`, `B2_AI_KEY`, `B2_SPK_LIVE`, límites diarios, `B2_OWNER_UIDS`) con default y efecto. Sin valores secretos.
8. **Limits & cost**: tabla de límites por usuario y guard mensual, y el costo estimado por sesión (writing, speaking turnos, Live).
9. **Testing**: comando exacto de las suites (`uv run --no-project --with playwright --with httpx python tests/test_x.py`), cuántas suites hay, qué cubren.
10. **Privacy & security**: resumen de una línea + links a `docs/PRIVACY.md`, `docs/TERMS.md`, `SECURITY.md`.
11. **Roadmap** (honesto, 3–5 ítems reales) y **License**.

Tono: claro, concreto, sin superlativos vacíos, sin emojis decorativos fuera de los badges, sin rastros de IA. Inglés.

## 2. docs/ (todos los documentos)

Revisar y actualizar, sin romper links:
- `docs/PRIVACY.md`, `docs/TERMS.md`, `SECURITY.md`, `docs/SECURITY.md`, `docs/DATA-MAP.md`, `docs/REPO-ABOUT.md`, `docs/SECURITY-CHECKLIST.md`.
- Crear `docs/README.md` como índice: qué es cada documento y cuándo leerlo.
- `docs/internal/*`: mantener, pero agregar `docs/internal/README.md` que explique que es documentación interna de desarrollo y no parte del producto.
- Eliminar o corregir afirmaciones obsoletas (por ejemplo "zero analytics", límites viejos, features que ya no existen). Verificar cada claim contra el código: `grep` de env vars, límites en `plans.py`, rutas de `server.py`.
- `docs/REPO-ABOUT.md` debe quedar listo para pegar en la descripción de GitHub: una línea corta, tags sugeridos, y el "About" en inglés.

## 3. Metadatos y textos fuera de la app

- `sitemap.xml`, `robots.txt`: revisar que las URLs sean las reales (`https://firsttracker.app/`).
- `LICENSE`: mantener MIT, agregar el año y el nombre correcto si falta.
- `SECURITY.md` raíz: política de reporte clara con contacto.
- `delegacion/`: es documentación de prompts internos. Agregar `delegacion/README.md` aclarando que son briefs de desarrollo, no documentación de usuario.

## 4. Reglas

- Solo documentación y capturas. **No tocar** `index.html`, `landing.html`, `server.py`, `plans.py`, tests ni assets de la app.
- No exponer claves, tokens, mails privados ni rutas absolutas del servidor.
- Nada de capturas falsas: todas generadas de la app real.
- Links internos relativos y válidos; verificar con un chequeo automático simple (script Python que lea los `.md` y compruebe que los paths existan).

## Verificación obligatoria

```bash
cd /home/b2first-tracker
python3 - <<'PY'
# comprobar links relativos de todos los .md
PY
cd tests
uv run --no-project --quiet --with playwright --with httpx python test_readme_limits.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_landing_honest.py; echo exit=$?
```

`test_readme_limits.py` debe seguir verde: si el README nuevo menciona límites, tienen que coincidir con `plans.py`.

## Cierre

Commit `docs: README de presentación y documentación al día`. Sin deploy.
