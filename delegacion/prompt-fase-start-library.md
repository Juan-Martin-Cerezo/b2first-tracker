# Fase start-library — un solo Start, con los contenidos dentro de la sesión

Repo: `/home/juan/b2first-tracker`, HEAD `15576a7`.

## Pedido

Juan no quiere que haya "Start" y "Library" como dos cosas separadas. Quiere **un solo Start**: al tocarlo entrás a la sesión, y dentro de esa sesión están los contenidos de esa unidad (papers, keys, audio, lesson plans y fuentes online de esa parte).

## Estado actual a cambiar

- Practice tiene dos tabs: "By part" y "Library".
- En "By part", cada fila de parte tiene un botón "Start" y además un botón "Library".
- Today (paneles de Materials) y Exam tienen botones "Browse all exercises" que abren la biblioteca global.

## Comportamiento esperado

1. **Practice muestra solo "By part"**: se eliminan los tabs By part / Library y el botón "Library" de cada fila. Cada unidad tiene **un único botón "Start"**.
2. Al tocar Start se abre la **vista de sesión** de esa unidad, con dos tabs internos: **Session** (lo que ya hace hoy: timer, ejercicio, guardar resultado) y **Contents** (los materiales de esa parte).
3. **Contents** es la biblioteca filtrada por la destreza y la parte de la unidad abierta, con el mismo orden y buscador de la biblioteca: paper + key, lesson plan, audio/tapescript, y las fuentes online de esa parte. Cada ítem clickeable; los locales abren el archivo de la app y los online en pestaña nueva. Un contador ("12 contents") y un link discreto "See all in this paper" que filtra por el paper completo (sin salir de la sesión).
4. Lo mismo cuando se entra desde el botón de Today o desde el plan: la sesión abierta trae sus Contents.
5. Se eliminan los botones "Browse all exercises" de Today y de Exam. La biblioteca completa queda accesible desde el link "See all in this paper" de Contents.
6. Al cerrar la sesión se vuelve a Practice, sin dejar estado a medias.

## Alcance

- Solo `index.html`, tests y capturas. Sin backend, sin dependencias, sin tocar plan/rotación, límites, corrector, speaking, listening propio, CSP ni landing.
- Sin handlers inline (`data-action`), i18n EN/ES simétrico, targets ≥44 px, 390×844 sin overflow, light/dark.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_start_contents.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_practice_split.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_exercise_library.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_today_unit_start.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
```

Nuevo `tests/test_start_contents.py`:
1. En Practice no existe ningún botón "Library" por fila ni tabs de biblioteca; cada unidad tiene exactamente un Start.
2. Tocar Start de Reading part 2 abre la sesión y muestra los tabs Session / Contents.
3. Contents lista solo ítems de esa destreza y parte, con contador coincidente y al menos un paper local, su key y las fuentes online disponibles.
4. "See all in this paper" amplía a todo el paper sin cerrar la sesión.
5. Cambiar a Session y volver a Contents conserva el estado.
6. No hay ningún botón "Browse all exercises" en Today ni en Exam.
7. 390×844 sin overflow, EN/ES con los mismos tabs.

Capturas: `tests/out/start_contents_390_light.png`, `start_contents_390_dark.png`, `start_contents_1280_light.png`.

## Cierre

Commit `feat(practice): un solo Start que abre la sesión con sus contenidos`. Sin deploy.
