# Fase mock-guided — el mock es un recorrido guiado: pop-up → materiales → timer

Repo: `/home/juan/b2first-tracker`, base: HEAD vigente (después de `fullmock-oneplace`). Leer primero el diff de esa fase.

## Pedido del dueño

Hacer un mock no puede terminar en “abrir materiales y nada más”. Tiene que ser un **pop-up que explica** y después te lleva **automáticamente materiales → timer**, con todo guiado. Aplica a mock de un paper y a full mock.

## Flujo único (wizard dentro del pop-up existente)

Un solo overlay `#mockStartModal` con 3 pasos y barra de progreso “1 Materiales · 2 Timer” (el paso 1 es la explicación). Nada de navegar a Library ni a otra vista.

### Paso 1 — Explicación
- Título: nombre del mock (“Reading & Use of English”, “Full mock”).
- Cuerpo: qué vas a hacer, duración y orden (“75 minutos. Abajo tenés el paper, la key y el audio. Cuando el material esté abierto, pasás al timer.”). Full mock: “195′ escritos en orden + 14′ Speaking”.
- Botones: **“Continuar a los materiales →”** (primario) y “Cancelar”. Sin “Abrir materiales” suelto.
- “Continuar” NO arranca el timer: avanza al paso 2 y, detrás del modal, deja visible y resaltado el panel de materiales del mock (preflight en full; panel inline en paper). Scroll mínimo, mismo viewport.

### Paso 2 — Materiales
- El modal muestra los links reales del mock (paper, key, audio por part, tapescript, speaking cards) en una lista scrolleable; cada link abre en pestaña nueva y **no cierra el modal**.
- Copy: “Abrí el paper. La key y el audio quedan acá.”
- Botones: **“Ya tengo el material →”** (primario) y “← Volver”.
- No se puede quedar en un callejón: el paso 2 siempre tiene salida al 3.
- Si el panel de fondo ya tiene los mismos links (fullmock-oneplace), no duplicar datos: el modal puede renderizar la misma fuente (`fullMockMaterialsFor(paper)`) pero la lista visible es una sola por contexto (modal en mobile; panel de fondo en desktop ancho). Nunca dos listas idénticas en el mismo viewport.

### Paso 3 — Timer
- Título: “Listo para empezar”.
- Muestra duración y “El contador arranca cuando toques Empezar”.
- Botones: **“Empezar contador”** (primario, ≥48 px), “← Materiales” y “Cancelar”.
- “Empezar contador” cierra el modal y llama al único `exStart()`/runner existente. Para full mock, el runner toma el control y avanza solo papel por papel. Para paper, queda el timer grande con “Pausa/Reset”.
- Escape y click afuera cierran sin arrancar; foco atrapado; recordar foco previo.

## Reglas

- Un único punto de entrada: tarjetas de paper y botón “Empezar full mock” abren el wizard en paso 1.
- Eliminar los botones sueltos “Abrir materiales” del modal y de `#exGuide`; no queda ningún camino que abra Library desde el arranque del mock.
- El temporizador **no** arranca en pasos 1–2; sólo en el 3.
- Repetir un mock vuelve al paso 1.
- Mobile 390×844: modal ocupa el ancho útil, lista de materiales con scroll interno (`max-height:45vh`), botones full-width; sin scroll horizontal. Desktop: modal 520 px, misma estructura.
- i18n EN/ES simétrico, sin handlers inline, dark/light.

## Tests

Actualizar/crear `tests/test_mock_guided.py`:
1. Click en tarjeta de paper → paso 1 con título y duración; timer sin cambios en 2 s.
2. “Continuar” → paso 2 con ≥3 links del paper; los links tienen `target=_blank`; el fondo muestra el panel de materiales del mock y `#v-exam` sigue activa.
3. “Ya tengo el material” → paso 3; “Empezar contador” arranca (`#exTimer` cambia en 2 s) y cierra el modal.
4. “Volver” desde paso 2/3 no arranca el timer; Escape tampoco.
5. Full mock: mismo recorrido; al empezar aparece el runner, avanza de paper con el hook de test y no vuelve a abrir el wizard entre papers.
6. No existe ningún control “Abrir materiales” que navegue a Library desde el inicio del mock; 0 links duplicados visibles en el mismo viewport.
7. 390×844 sin overflow; botones ≥48; EN/ES simétrico; 0 errores de consola.

Actualizar `test_mock_start.py`, `test_fullmock_oneplace.py`, `test_exam.py`, `test_i18n.py` por los controles movidos.

```bash
cd /home/juan/b2first-tracker/tests
for f in test_mock_guided.py test_mock_start.py test_fullmock_oneplace.py test_exam.py test_mobile.py test_i18n.py test_index_handlers_exist.py; do
  uv run --no-project --quiet --with playwright --with httpx python "$f" || echo "FAIL $f"
done
```

Capturas: `tests/out/mock_guided_step1_390_light.png`, `mock_guided_step2_390_light.png`, `mock_guided_step3_390_light.png`, `mock_guided_step2_1280_light.png`.

## Cierre

Un commit: `feat(exam): arranque de mock guiado materiales → timer`. Sin deploy.
