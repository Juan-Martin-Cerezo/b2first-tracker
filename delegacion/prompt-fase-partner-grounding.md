# Fase partner-grounding — el partner escucha y responde a lo que decís

Repo: `/home/juan/b2first-tracker`, HEAD `bcf0ab8`.

## Problema real

El partner (Alex) contesta, pero puede sonar rutinario: el backend (`server.py` ~6788, rama `partner`) recibe `candidate_said` y le pide "react", sin exigir que use un detalle concreto ni conocer lo que Alex ya dijo. Resultado posible: frases genéricas ("That's interesting, I agree") o repetir su propia línea anterior. Juan quiere que el partner **reciba lo que dijo el usuario y hable en base a eso**, que se note que escuchó, y que la conversación de todos cambie según lo que se va diciendo.

## Alcance

### 1. Backend `/api/speaking/partner` (modo partner)
- Aceptar además `partner_said` (lista de hasta 3 líneas previas de Alex) y `candidate_context` (ya existe; usarlo también en modo partner, no solo examiner). Sanear igual que `candidate_said` (texto plano, sin control chars, tope 300 por línea, 3 líneas).
- Reescribir la instrucción del partner:
  - Debe reaccionar a **un detalle concreto** de `candidate_said` (una palabra o frase que esté realmente ahí: el medio de transporte, el lugar, el motivo, la actividad, etc.), no a la idea general.
  - Tomar postura (acordar y sumar un motivo/ejemplo, o discrepar con respeto) y, si viene al caso, devolver una pregunta corta.
  - Máximo 35 palabras, una o dos frases, inglés británico natural, sin listas ni comillas.
  - Prohibido: empezar con muletillas tipo "That's interesting", "I see", "I agree" sin contenido; repetir literalmente la línea del candidato; reutilizar una línea que ya esté en `partner_said` (parafraseada tampoco).
  - Si el candidato no dijo nada (`candidate_said` vacío), devolver `{"line": ""}` sin llamar al modelo.
- Guard de grounding: después de generar, verificar que la línea comparte al menos una palabra de contenido (≥4 letras, sin stopwords) con `candidate_said`; si no, reintentar una vez con una instrucción más estricta y el detalle entre comillas. Si el segundo intento tampoco engancha, devolver igual la mejor línea (nunca 5xx). Si la línea coincide con alguna de `partner_said` (similitud por tokens ≥0.8), reintentar una vez.
- Mismo tratamiento para el modo `examiner`: ya usa `candidate_context`; sumar el detalle concreto y prohibir repetir la pregunta anterior.

### 2. Cliente (`index.html`)
- En `spxPartnerFromProvider` enviar `partner_said: (SP_EXAM.partnerSaid||[]).slice(-3)` y `candidate_context: spxCandidateContext()` en todas las partes (hoy solo Part 4).
- Enviar `candidate_said` con la transcripción **más reciente** al momento del turno del partner (`SPK.heard.final` o la última línea de `SPK.lines` con `who==='candidate'`), no una copia vieja de estado.
- Asegurar que la línea del partner se **dice en voz alta** (`spxSay('partner', …)`), y que en el panel queda visible junto a la del candidato: después de cada turno del usuario, mostrar "You / Vos: <transcripción>" y la respuesta del partner debajo, para que se vea que la conversación avanza. Si no hay reconocimiento de voz disponible, mostrar el texto igual cuando lo haya.
- Mantener el fallback del banco solo cuando no hay proveedor de IA; si hay IA y devuelve vacío, reintentar una vez y recién ahí usar el fallback.

### 3. Reglas
- Sin tocar límites, plan, listening, cuentas, owner, CSP ni landing.
- Sin dependencias nuevas. `python3` stdlib. No loguear contenido del usuario.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_speaking_custom_task.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_v2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_exam.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_duo.py; echo exit=$?
```

Nuevo `tests/test_partner_grounding.py`:
1. Con `candidate_said="I'd rather go by coach because it's much cheaper"`, la línea devuelta menciona coach/cheap/bus/money (al menos un token de contenido del original) y no es una muletilla vacía.
2. Con `candidate_said="I prefer flying because it's much faster"`, la línea es distinta de la anterior y menciona flying/fast/plane.
3. Con `partner_said` ya conteniendo la línea generada, una segunda llamada no devuelve la misma frase.
4. `candidate_said` vacío → 200 con `line: ""` y sin llamada al modelo (usar stub de red).
5. La respuesta nunca excede 35 palabras y es una o dos frases.
6. En la UI, tras un turno del candidato, el panel muestra su transcripción y la del partner (test con `SPX_TEST` y provider stub).

## Cierre

Commit `feat(speaking): el partner responde a lo que dice el candidato`. Sin deploy.
