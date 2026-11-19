# Fase readme-ia — sección de IA y "how to try" para el jurado del hackatón

Repo: `/home/juan/b2first-tracker`. Base: HEAD `4cc4564`.

Juan presenta el proyecto en "Build Your First AI App" (Devpost). Los jueces piden explícitamente: qué modelo/API se usa y cómo contribuye, y un README con setup, features, tecnologías y cómo probarlo. El README actual cubre setup, arquitectura, privacidad y límites, pero no tiene una sección de implementación de IA ni un camino corto para que un jurado lo pruebe.

## Qué agregar en `README.md`

1. Sección `## AI implementation`, después de `## The Speaking exam` y antes de `## What it does not do`. Tiene que ser concreta, en inglés, sin marketing. Incluir una tabla o lista con:
   - **Gemini 3.8 Live** (`B2_SPK_GOOGLE_MODEL`, Live API): examinador de voz en tiempo real; el servidor solo acuña tokens efímeros (`POST /api/speaking/token`), el audio va del navegador a Google y nunca pasa por el servidor ni se guarda.
   - **Gemini 2.5 Flash + 2.5 Flash TTS**: camino por turnos cuando Live no está disponible; una llamada por turno para transcribir/responder y otra para la voz.
   - **DeepSeek V4.1 Flash** (formato OpenAI, `B2_AI_PROVIDER=deepseek`): corrector de Writing contra las cuatro bandas Cambridge y report final de Speaking (JSON estricto, salida acotada a 8 KB).
   - **Azure Pronunciation Assessment** (opcional): única fuente de la banda de Pronunciation; sin key el report dice `not measured` y el endpoint responde 503 `speech_not_configured` — el modelo nunca inventa esa banda.
   - Keys solo en el entorno del servidor (`/home/juan/.config/b2first/ai.env`, `chmod 600`); ninguna llega al navegador ni al repo. Los tests corren con stubs, sin red.
   - Topes de costo vigentes: 5 evaluaciones de Writing y 1 mock de Speaking (15 min) por cuenta y día; 20 llamadas de texto y 25 minutos de voz por instancia y día. Citar `plans.py` y `B2_AI_DAILY_TOTAL`/`B2_SPK_MIN_DAILY_TOTAL`.
   - Una línea de honestidad: las bandas son estimaciones de práctica calibradas contra las escalas publicadas, no notas oficiales de Cambridge.

2. Sección `## How to try it in two minutes`, antes de `## Quick start`:
   - URL: https://firsttracker.app
   - "Create an account" solo pide usuario y contraseña de 12+ caracteres; no hay email.
   - Onboarding: fecha de examen → notas por habilidad → "Skip for now" en el chequeo de 12 preguntas (se puede hacer después).
   - Para ver la IA: un draft de 140–190 palabras en Writing y un mock corto de Speaking; los topes diarios están en la sección de IA.

3. No inventar features, métricas ni benchmarks. No incluir claves, rutas absolutas del servidor ni datos de usuarios reales.

## Reglas

- Solo `README.md`. No tocar código, tests, landing ni config.
- Inglés, oraciones cortas, sin emojis.
- Mantener el tono existente del README (directo, sin superlativos).

## Verificación

```bash
cd /home/b2first-tracker
python3 - <<'PY'
import re
t=open('README.md').read()
assert '## AI implementation' in t
assert '## How to try it in two minutes' in t
assert 'gemini-3.8-live' in t and 'deepseek' in t.lower()
assert 'not measured' in t
print('readme ok', len(t))
PY
cd tests && uv run --no-project --quiet --with httpx python test_readme_limits.py; echo exit=$?
grep -rniE '(api[_-]?key|sk-[a-z0-9]{10})' README.md | head   # vacío
```

`test_readme_limits.py` exit=0 y el grep sin resultados.

## Cierre

Commit `docs(readme): implementación de IA y cómo probarlo para el hackatón`. Sin deploy.
