# Fase landing-ia — Rediseño de la landing centrado en las features de IA

Repo: `/home/juan/b2first-tracker`. Base: HEAD `26dbb7f`, rama `feat/speaking-continuous`.

Juan pidió: "Delegá un rediseño de la landing page de https://firsttracker.app/, donde se prepare todo para que lo vean los de hackaton, centrado en las features de IA que incluye, siendo responsive, y con un CTA a empezar a usarlo".

Significa: reescribir `landing.html` como una página nueva, con la IA como argumento principal (corrector de Writing con rubric Cambridge, examinador de voz de 4 partes con Gemini Live, plan adaptativo desde el diagnóstico), pensada para que la lea un jurado de hackatón en 60 segundos, responsive de 360 a 1280, con CTA claro a `/app`.

## Alcance

1. `landing.html` — reescritura completa (una sola página estática, CSS y JS inline).
2. `tests/test_ui_batch2.py` — actualizar SOLO el assert del h1 al texto nuevo (ver abajo). Nada más.
3. `delegacion/` — el log que genere el runner, no hace falta commitearlo.

## Estructura pedida

1. **Nav**: logo, links a `#ai`, `#how`, `#writing`, `#speaking`, `#faq`; `Sign in` y `Create an account` (texto exacto) a `/app`; toggle de tema y menú móvil.
2. **Hero**: un solo `<h1 id="hero-title">` que diga el beneficio de IA (el assert viejo se actualiza). Eyebrow "Cambridge B2 First · AI feedback". Subcopy honesto: corrección con bands Cambridge, examinador de voz, plan adaptativo. CTAs: "Start the free diagnostic" y "See how the AI works" (anclas internas o `/app`).
3. **Tira de prueba**: 3–4 datos verificables del producto (4 bands 0–5, 4 speaking parts con 2/4/4/4 min, 12-item diagnostic, 17 exam parts). Sin métricas inventadas.
4. **Sección IA (el corazón)** con 3 bloques grandes, cada uno con un mockup/panel ilustrativo hecho en HTML+CSS (no imágenes):
   - **Writing rubric corrector**: bands nombradas (Content, Communicative Achievement, Organisation, Language), evidencia citada del draft, 2 weak spots, 3 rewrites. Mostrar un panel de ejemplo rotulado como "Illustrative example".
   - **Voice examiner (Gemini Live)**: Parts 1–4, timers 2/4/4/4, partner voice en Part 3, transcript y report bandeado. Dejar explícito que es práctica, no certificado.
   - **Adaptive plan**: el diagnóstico de 12 ítems elige la parte más débil y arma la sesión del día y la rotación semanal.
5. **"Under the hood"** para jueces, en tono técnico pero corto: token efímero de Gemini Live minteado en el servidor (la API key nunca llega al browser), audio nunca se guarda en disco, si la evaluación de pronunciación no está configurada el report muestra **not measured** en vez de inventar un score, planificador determinístico, sin trackers ni analytics de terceros, export JSON y borrado de cuenta. Enlazar al repo de GitHub (única URL externa permitida además de firsttracker.app y schema.org).
6. **Privacy** corta (podés reusar el copy actual, condensado).
7. **FAQ** de 3–4 preguntas: bands no son oficiales de Cambridge, cuenta sin email, qué pasa al borrar la cuenta, cómo se usa la IA.
8. **CTA final** ancho completo: "Take the 12-item diagnostic." + botón "Create an account" → `/app`.
9. Footer con legal (`/privacy`, `/terms`, `/security`), GitHub y disclaimer de Cambridge (mantener el texto actual).

## Reglas duras (tests existentes)

- **Un solo** `<h1>`, con `id="hero-title"`. El assert de `tests/test_ui_batch2.py` hoy busca "Someone finally marks your writing": actualizalo al texto nuevo exacto que uses.
- Deben existir `#navMenuBtn`, `#mobileMenu` (con atributo `hidden` cuando cerrado) y `#themeToggle`. El tema se guarda en `localStorage['b2first_theme']` y se aplica como `data-theme` en `<html>`; default = preferencia del sistema. Nada de flash raro.
- Todos los `<script>` inline, sin `src`. Sin stylesheets ni fuentes externas. Cero CDN.
- Un único bloque `<script type="application/ld+json">`, sin `offers`, `price` ni `isAccessibleForFree`, sin "self-hostable".
- URLs externas permitidas: solo `https://github.com/Juan-Martin-Cerezo/b2first-tracker`, `https://firsttracker.app...` y `https://schema.org`.
- Links ancla con texto exacto `Sign in` y `Create an account` deben apuntar a `/app` (pueden repetirse).
- Prohibidas estas cadenas en TODO el archivo, incluso en comentarios, case-insensitive: `14ms`, `RPi`, `Raspberry`, `POSIX`, `bare-metal`, `PBKDF2`, `cluster`, `SHA256 SYNC`, `$12`, `$5`, `pricing`, `upgrade`, `redeem`, `demo`, `buy`, `activation code`. Ojo con "demo": usar "preview", "example" o "walkthrough".
- Contraste de todo `<p>` ≥ 4.5:1 contra su fondo efectivo, en light y dark.
- Sin scroll horizontal a 360×740 ni a 1280×800, en ambos temas. Cero errores de consola/pageerror.
- No inventar features, métricas, benchmarks, testimonios ni logos de terceros. Nada de "99% accuracy". Lo que no exista, no se dice.

## Diseño

- Dark-first, pero con tema claro completo. Fondo oscuro en oklch, nunca `#000` puro. Un solo acento de marca (el azul actual del producto, familia `#1b4e9b` / oklch equivalente). Cero violetas "AI", cero gradientes arcoíris, cero glassmorphism genérico.
- Tipografía del sistema (sin fuentes externas). Jerarquía fuerte, mucho aire, bordes finos, tarjetas planas. Los paneles de ejemplo se construyen con HTML/CSS (barras, chips, quotes).
- Mobile primero 360×740; el hero y los CTAs tienen que quedar usables sin scroll horizontal.
- Copy en inglés, claro y concreto. Nada de relleno tipo "revolutionize".

## Verificación obligatoria (correr, no reportar de memoria)

```bash
cd /home/juan/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_landing.py
uv run --no-project --quiet --with playwright --with httpx python test_landing_honest.py
uv run --no-project --quiet --with playwright --with httpx python test_no_purchase.py
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py
```

Las cuatro en verde. `test_landing_honest.py` deja capturas en `tests/out/landing-360x740-{light,dark}.png` y `tests/out/landing-1280x800-{light,dark}.png`: mirarlas (leer los PNG) y corregir lo que se vea roto antes de commitear.

Chequeo extra propio, con números:

```bash
grep -c '<h1' landing.html            # 1
grep -ciE 'demo|pricing|upgrade|redeem|buy' landing.html   # 0
```

## Cierre

Commit único: `feat(landing): rediseño centrado en las features de IA para el hackatón`.
Árbol limpio. **Sin deploy.**
