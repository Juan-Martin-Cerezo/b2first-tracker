# Fase practice-first — la pestaña Practice abre en la Library, no en la lista de drills

Repo: `/home/juan/b2first-tracker`, base HEAD `0344e47`.

## Problema verificado

Al tocar **Practice** en el header (desktop 1280×800, mobile 390×844) se abre `#v-practice`, pero lo primero y único visible es “Exercises by part”: una lista de 17 partes con inputs y Save. La Library nueva (`#practiceLibraryCard`) existe pero queda **debajo**, con 14.416 px de alto acumulado, así que el usuario nunca la ve. El subtítulo además sigue diciendo “Timed drills by exam part”, que describe la pantalla vieja. El dueño dice: “la pestaña de practice del header no es la correcta”.

## Cambio de producto

Practice deja de ser una lista de drills y pasa a ser **el hub de práctica**:

1. **Orden**: `#practiceLibraryCard` (Library completa, con buscador, filtros y contador) va **primero**, inmediatamente debajo del page-head. `#practiceParts` va después, como bloque secundario.
2. **“Exercises by part” colapsado por defecto** con `<details>` (summary visible: “Exercises by part · save your score”), para que no empuje la Library 14k px hacia abajo. Al abrirlo se comporta igual que hoy (Start, inputs, Save). Estado abierto/cerrado no persiste entre sesiones.
3. **Dos intenciones visibles arriba de la Library**, en una fila de 2 tarjetas/botones (no tabs, no wizard):
   - **Full mock** → abre `#v-exam` y el pre-flight del full mock (`data-action` existente, sin duplicar lógica).
   - **Practise by part** → abre el `<details>` de partes y hace scroll al primer grupo, o simplemente ancla a `#practiceParts`.
   Cada una con una línea: “4 papers, official timing” / “One part, exact resources”.
4. **Copy honesto**:
   - Título: `Practice` (sin cambiar la key).
   - Subtítulo: “Choose a full mock or a part. Every option opens its papers, keys, audio and free online practice.”
   - ES: “Elegí un full mock o una parte. Cada opción abre sus papers, keys, audio y práctica online gratis.”
5. **Nav**: el botón Practice del header y el de mobile siguen apuntando a `#v-practice`; al entrar, `activateNavView('practice')` debe renderizar **también** la Library (hoy sólo llama `renderParts()`), garantizando que el contador y las filas estén pintados sin depender de `refreshAll`.
6. Mobile 390×844: en el primer viewport se tienen que ver el título, las 2 tarjetas de intención y el buscador/contador de Library. Sin overflow horizontal. El FAB de Log session no debe tapar el buscador ni las tarjetas.

## Alcance

- Solo `index.html` + tests + capturas. No tocar backend, límites, speaking, pre-flight del full mock (se reusa), CSP, landing.
- Sin handlers inline (`data-action`), i18n EN/ES simétrico, targets ≥44 px, sin ids duplicados.

## Tests

Actualizar `tests/test_practice_flow.py` y `tests/test_start_contents.py` para el nuevo orden:
1. Al hacer click en el nav Practice, `#practiceLibraryCard` es visible en el primer viewport (bounding box top < 844) y su contador > 0.
2. `#practiceLibraryCard` aparece antes que `#practiceParts` en el DOM.
3. `#practiceParts` está dentro de un `<details>` cerrado por defecto; al abrirlo aparecen los 17 Start.
4. Las 2 tarjetas de intención existen; “Full mock” abre `#v-exam` con el pre-flight visible; “Practise by part” abre el details.
5. Library sigue mostrando 187 contents en EN y el mismo orden; filtros siguen funcionando dentro de Practice.
6. 390×844: sin overflow horizontal, buscador visible sin scroll, FAB no lo tapa (comparar bounding boxes).
7. EN/ES simétrico; sin handlers inline; sin errores de consola.

Verificación obligatoria (todas exit 0):

```bash
cd /home/juan/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_practice_flow.py
uv run --no-project --quiet --with playwright --with httpx python test_start_contents.py
uv run --no-project --quiet --with playwright --with httpx python test_practice_split.py
uv run --no-project --quiet --with playwright --with httpx python test_mobile.py
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py
```

Capturas: `tests/out/practice_hub_390_light.png`, `practice_hub_390_dark.png`, `practice_hub_1280_light.png`. Revisarlas: la Library tiene que verse sin scrollear en mobile.

## Cierre

Un commit: `fix(practice): la pestaña abre en la Library y las partes quedan colapsadas`. Sin deploy.
