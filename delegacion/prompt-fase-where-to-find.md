# Fase where-to-find — materiales en bloques, con claves al lado y online aparte

Repo: `/home/juan/b2first-tracker`, HEAD `4f1b694`.

## Problema

Las secciones "Where to find" de Today (Unidad de uso de inglés/Reading, Writing, Listening y Speaking) muestran hoy una fila de chips sueltos: `R&UoE S1`, `S2`, `FS1`, `Keys S1`, `Keys S2`, `Online`, etc. (`renderGuides()` en index.html ~18597, `chips()` ~18588, `listeningTestCards()` para Listening). No se entiende qué va con qué, ni cómo usarlo, y el link "Online" queda mezclado con los PDFs.

## Diseño pedido

En **las cuatro** secciones "Where to find" de Today, cada material va en **bloques separados verticalmente**, con este patrón:

```
R&UoE 1 — KEYS 1
(espacio)
R&UoE 2 — KEYS 2
(espacio)
...
Online: <link> — para qué sirve y cómo usarlo
```

## Reglas concretas:
0. **Todo a un toque, sin buscar**: si el material es por parte, el bloque tiene que linkear directo a esa parte (su PDF/audio/página concreta, con el ancla o el archivo exacto, no a la carpeta ni al índice). Si es full paper, el bloque linkea a un lugar donde se pueda practicar el full paper completo (el PDF del full test y, si existe, el online con el full mock), no a una parte suelta.
1. **Cada bloque es una fila propia con aire arriba/abajo** (no chips en línea). Dentro del bloque, el paper y su clave van juntos, separados por un guion o dos columnas: `R&UoE S1 — Keys S1`, `Writing FS1 — Keys FS1`, `Listening Test 1 — Answer key`, `Speaking S1 — Examiner notes`.
2. Si un material no tiene clave (por ejemplo un lesson plan o un visual), va igual como bloque propio, sin inventar pareja.
3. Los **botones de audio/tapescript** de Listening quedan dentro del bloque del test, en una segunda línea del mismo bloque, no en filas separadas.
4. **Online va aparte**, al final, en un bloque visualmente distinto (borde o fondo suave + etiqueta "Online"), con una frase de cómo usarlo. Ejemplos:
   - R&UoE: "Practise a timed part online; it does not count for the tracker — log it only if you finish it."
   - Writing: "Model answers and timed prompts; use it to compare structure, not to replace the paper."
   - Listening: "Extra audio with automatic marking; do one part at a time."
   - Speaking: "Sample questions to record yourself; then check your silences in Live Studio."
5. Cada bloque de paper lleva una línea chica de **cómo usarlo** (una frase, no párrafo): p. ej. "30 min timed → check with the key → log the score". Reusar el mismo texto para el mismo tipo de material.
6. Mobile 390×844: una columna, sin overflow horizontal, targets ≥44px. Light y dark con el mismo lenguaje visual de la app (oklch). i18n EN/ES: las instrucciones y las etiquetas nuevas deben estar en ambos idiomas; los nombres de archivo (R&UoE S1, Keys S1) quedan como están.
7. **Bloque "Full paper"** en cada sección, separado del resto: "Practise the whole paper" con link al full test (PDF o página que lo tenga completo) y, si hay versión online del full paper, un segundo link ahí mismo. Si el catálogo no tiene full paper para esa destreza, no inventar: mostrar solo lo que existe. Nunca linkear un full paper a una parte suelta.

## Alcance técnico

- Reemplazar el render de chips por un renderer de bloques compartido (una función, usada por las cuatro secciones): recibe filas `[{left, right?, extra?, hint}]` y un bloque online `{label, href, hint}`.
- Mantener los links a los PDFs/audio tal como los resuelve el índice `MAT` y `listeningTestCards()`; no cambiar rutas ni el catálogo.
- El botón de marcar material como hecho (`matDone`/`matUndo`) no se toca.
- No tocar backend, límites, plan, listening propio, cuentas, CSP ni landing.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_today_unit_start.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
```

Nuevo `tests/test_where_to_find.py`:
1. Con catálogo stub, cada una de las 4 secciones renderiza bloques (`display:block`/flex column con gap), no una fila de chips.
2. En R&UoE, `R&UoE S1` y `Keys S1` están en el **mismo** bloque; `S2` en otro; la distancia vertical entre bloques es > 8 px.
3. Listening: el bloque del Test 1 contiene Questions, Audio, Tapescript y Answer key.
4. Online: existe un bloque separado con etiqueta "Online" y una frase de uso; no está dentro de la fila del último paper.
5. 390×844: sin overflow horizontal, todos los links clickeables, texto de uso presente en EN y ES.
6. Deep links: el link de un bloque por parte apunta al archivo/página de esa parte (el `href` contiene el nombre de esa parte), y el bloque "Full paper" apunta al full test, no a una parte. Verificar al menos R&UoE S1 vs Full paper y Listening Test 1 vs Full test.

Capturas 390×844 light/dark de las cuatro secciones y 1280×800 de una.

## Cierre

Commit `feat(today): materiales en bloques con claves y online separado`. Sin deploy.
