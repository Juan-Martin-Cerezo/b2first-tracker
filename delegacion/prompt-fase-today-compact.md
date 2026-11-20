# Fase today-compact — los recursos de Today, más cortos y cómodos en móvil

Repo: `/home/juan/b2first-tracker`, HEAD tras la fase exam-sources.

## Problema

Al pasar "Where to find" a bloques (`mount(...)` en index.html, renderGuides ~18820), cada material quedó como una tarjeta con título grande + clave + hint + link, todo apilado a una columna. En Today eso empuja el resto de la sesión demasiado abajo: la tarjeta de R&UoE, Listening y Speaking ocupa ~800–1000 px solo en recursos, y en un teléfono hay que scrollear mucho para llegar a las acciones.

## Objetivo

Que los recursos se distribuyan bien y sean cómodos en móvil, sin perder la estructura (paper + keys, Full paper, Online):

1. **Contraer por defecto**: cada sección "Where to find / Materials" muestra un encabezado compacto con un resumen: `Materials · 10 resources` y un caret. Tap/click expande. Estado recordado en `localStorage` por destreza (`b2f_wtf_open_rue`, etc.), por defecto cerrado.
2. **Dentro, grilla densa**: filas de 44–56 px de alto, nombre del paper a la izquierda y su clave a la derecha, hint en una sola línea truncada (ellipsis con `title` completo). Dos columnas en ≥720 px, una columna en móvil. Gap vertical de 8–10 px entre filas, 16 px entre grupos.
3. **Full paper y Online**: quedan como dos filas destacadas al final del panel expandido (no tarjetas altas), con su link y un hint de una línea.
4. **Altura total**: con el panel cerrado, ninguna sección de recursos debe superar ~64 px. Con el panel abierto en 390×844, el alto del panel debe ser menor a 1,6× el alto con el diseño actual (medir con `getBoundingClientRect().height`).
5. **Cómodo en móvil**: targets ≥44 px, sin scroll horizontal, texto de 13–14 px para hints, contraste AA en light y dark. Nada de `position: absolute` para el caret que rompa el flujo.
6. Mantener deep links por parte, bloque Full paper apuntando al full test, bloque Online separado, y que "Log session" y las acciones de la sesión queden visibles sin scrollear media pantalla.
7. i18n EN/ES para "Materials · N resources" / "Materiales · N recursos" y el aria (`aria-expanded`).

## Reglas

- Solo `index.html` y tests. Reutilizar `mount()`/estilos existentes; no duplicar renderers.
- No tocar backend, plan, límites, listening propio, cuentas, CSP ni landing.
- Sin handlers inline: usar `data-action` como el resto.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_where_to_find.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_today_compact.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
```

Nuevo `test_today_compact.py`:
1. Panel cerrado: alto ≤64 px por sección y `aria-expanded="false"`.
2. Al expandir, aparecen todas las filas; cada fila mide entre 40 y 64 px.
3. 390×844: alto del panel expandido < 1,6× el alto del layout anterior (medir con una constante documentada en el test) y sin scroll horizontal.
4. El estado abierto/cerrado persiste tras recargar (localStorage).
5. Deep links intactos: R&UoE S1 apunta a su archivo y Full paper al full test.
6. EN/ES: el resumen dice "Materials · N resources" / "Materiales · N recursos".

Capturas 390×844 light/dark cerrado y abierto, y 1280×800.

## Cierre

Commit `feat(today): recursos compactos y colapsables`. Sin deploy.
