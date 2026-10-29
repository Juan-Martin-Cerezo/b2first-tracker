# PROMPT — Fase 7: UI overhaul + dark mode real + toda la app en inglés

Sos un ingeniero senior de frontend + diseñador de producto. Repo
`/home/juan/b2first-tracker` (cwd correcto). **Este turno es para CODIFICAR.**

## Leé esto primero (obligatorio, antes de escribir una línea)

```
/home/juan/.hermes/skills/software-development/make-interfaces-feel-better/SKILL.md
```

Es la guía de diseño del proyecto. Aplicá sus principios, no los resumas.

## Los tres problemas reales (quejas textuales del usuario)

1. **La UI es fea.** No es un problema de "falta un degradado": es jerarquía, espaciado,
   tipografía y estados. Hoy hay estilos inline por todos lados (`style="background:var(--bg)..."`)
   mezclados con clases, y el resultado es inconsistente.
2. **El modo oscuro es malo.** Existe (`data-theme="dark"` + tokens en `:root`), pero está
   hecho con negros planos y contraste desparejo. Tiene que verse como producto, no como
   invertir colores.
3. **Todo está en español** y el proyecto es público. **La app entera va en inglés.**

## Tarea A — Sistema de diseño (CSS, sin frameworks)

Consolidá el CSS en un bloque de tokens + clases utilitarias del propio proyecto. **Prohibido**
introducir Tailwind, preprocessors o dependencias.

### Tokens (oklch, dos temas)

```css
:root[data-theme="light"]{
  --bg: oklch(0.99 0.002 250);      /* nunca blanco puro */
  --surface: oklch(0.975 0.003 250);
  --surface-2: oklch(0.955 0.004 250);
  --line: oklch(0.90 0.006 250);
  --txt: oklch(0.22 0.01 250);
  --txt-2: oklch(0.46 0.01 250);
  --acc: oklch(0.55 0.16 255);
  --ok: oklch(0.60 0.14 150);
  --warn: oklch(0.72 0.15 75);
  --bad: oklch(0.58 0.19 25);
}
:root[data-theme="dark"]{
  --bg: oklch(0.19 0.006 255);      /* gris azulado, NO #000 */
  --surface: oklch(0.23 0.008 255);
  --surface-2: oklch(0.27 0.009 255);
  --line: oklch(0.33 0.01 255);
  --txt: oklch(0.94 0.004 255);
  --txt-2: oklch(0.72 0.008 255);
  --acc: oklch(0.72 0.13 255);
  --ok: oklch(0.74 0.13 150);
  --warn: oklch(0.80 0.13 80);
  --bad: oklch(0.70 0.16 25);
}
```

Reglas duras:
- **Contraste**: todo texto ≥ 4.5:1, y `--txt-2` ≥ 4.5:1 sobre `--surface` en ambos temas.
  Verificalo con la fórmula de luminancia relativa (escribí un mini script y pegá la tabla).
- Elevación con **box-shadow en capas con transparencia**, no con `border`. Los bordes quedan
  sólo para estructura (divisores) y estado (focus, seleccionado).
- **Radio concéntrico**: `outer = inner + padding`. Sin radios iguales anidados.
- `font-variant-numeric: tabular-nums` en TODO número que cambia (racha, contadores, timer,
  puntajes, tablas de stats).
- `-webkit-font-smoothing: antialiased` en `html`.
- `text-wrap: balance` en títulos, `text-wrap: pretty` en párrafos.
- `transition-property` explícito siempre; **nunca `transition: all`**.
- `active` en botones: `scale(0.96)`, `transition: transform 120ms ease-out`.
- Hit area ≥ 44×44 en mobile, ≥ 40×40 en desktop. Extendé con pseudo-elemento si el control
  visible es más chico. Los hit areas no se solapan.
- Iconos: SVG inline con `currentColor`, stroke 1.5px junto a texto regular, 2px junto a
  semibold. Un solo set.
- Foco visible SIEMPRE: `:focus-visible` con `outline: 2px solid var(--acc); outline-offset: 2px`.
  Nunca `outline: none` sin reemplazo.
- `prefers-reduced-motion: reduce` → desactivar animaciones no esenciales.

### Tipografía

Usá una sola familia de sistema (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto`),
escala de 5 tamaños (`12 / 14 / 16 / 20 / 28`) y sólo 2 pesos (400, 600). Nada de 5 tamaños
distintos en una misma card.

### Layout

Mobile-first. Un solo ancho de contenido (`max-width: 1080px`) centrado, con `padding-inline:
clamp(16px, 4vw, 32px)`. Nav en mobile abajo con 5 ítems máximo + "More"; en desktop arriba.
El FAB de quick-log no tapa contenido: `bottom: calc(env(safe-area-inset-bottom, 0px) + 16px)`.

## Tarea B — Toda la app en inglés

Traducí **todo** el texto visible: nav, títulos, botones, placeholders, mensajes de error,
tooltips, labels de gráficos, el banner de demo, la card del plan, el diagnóstico, el corrector,
los `alert()/confirm()`. Tono: directo, sin marketing, como el README.

- `es-AR` → `en`. Fechas con `toLocaleDateString('en-GB')`, y **`dayKey()` sigue usando hora
  local** (no cambiar la lógica de racha, sólo el formato visible).
- **Comentarios de código y `agents.md` también en inglés.**
- Mensajes del server (`detail`, `error`) en inglés, y los tests actualizados.
- Los `reason` del plan semanal: en inglés, citando el dato (*"part 3 is your weakest (1/2 in
  the diagnostic)"*).

## Tarea C — Rediseño de las vistas

Todas las vistas: `today`, `exam`, `parts`, `prog`, `graf`, `plan`, `err`, `libros`, `ia`, `diag`.

Requisitos por vista (mínimo):
- **Today**: jerarquía clara — 1) qué hacer ahora (el slot del plan de hoy), 2) streak + meta
  semanal, 3) countdown al examen, 4) últimas sesiones. El FAB abre quick-log.
- **Plan**: la card "Week plan" con 5 filas; cada una con `Escribir`→`Start` y `reason` en
  `--txt-2` tamaño 12.
- **Diag**: una pregunta a la vez, opciones como botones grandes (48px alto), progreso `3/12`
  como barra fina arriba, timer discreto a la derecha.
- **IA**: textarea con contador de palabras, 4 tarjetas de banda con número grande, feedback,
  `weaknesses` en lista ámbar, `quotes` en `<details>`.
- **Graf**: los SVG existentes sobre tokens nuevos; grid tenue, sin ejes recargados.
- **Tablas** (log, stats): `tabular-nums`, filas de 44px, hover sutil, sin zebra agresivo.

Estados obligatorios en todo lo interactivo: `hover`, `focus-visible`, `active`, `disabled`,
`loading`, `empty`. Un `empty` nunca es un espacio en blanco: es una frase + acción.

## Tarea D — Tests

- Actualizá **todos** los tests que buscan texto en español a las cadenas nuevas en inglés
  (`test_final.py`, `test_diag.py`, `test_plan.py`, `test_streak.py`, `test_demo.py`).
- Agregá a `test_final.py` (o un `test_theme.py`) 6 asserts nuevos:
  1. toggle de tema: light → dark → persiste en `localStorage`
  2. en dark, `getComputedStyle(document.body).backgroundColor` NO es `rgb(0,0,0)`
  3. ningún elemento interactivo tiene `outline: none` sin `:focus-visible` reemplazo
     (chequeo heurístico: al menos 3 controles clave responden a foco)
  4. contraste calculado de `--txt` sobre `--bg` ≥ 4.5 en ambos temas (ejecutá la fórmula en JS)
  5. el nav mobile no tapa el FAB (`bottom` del FAB > alto del nav)
  6. `errores_js` vacío en las 10 vistas recorridas

## Prohibido

- Frameworks, preprocessors, fuentes externas, icon fonts, dependencias nuevas.
- Cambiar lógica de negocio: racha, diagnóstico, plan, corrector y sync se comportan igual.
- Tocar `server.py` salvo traducir strings de error; nada de endpoints nuevos.
- Romper `test_sync.py`, `test_ai.py`, `test_demo.py`.
- `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
python3 - <<'PY'
print("contraste txt/bg:", )
PY
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -6
cd tests && uv run --with playwright python test_diag.py 2>&1 | tail -4
cd tests && uv run --with playwright python test_plan.py 2>&1 | tail -4
cd tests && uv run --with playwright python test_demo.py 2>&1 | tail -4
```

## Commit

```
feat(ui): design tokens, real dark mode and full English interface
```

Respondé al final **sólo** con: archivos tocados, salida literal de los comandos, la tabla de
contraste medida, y el hash.
