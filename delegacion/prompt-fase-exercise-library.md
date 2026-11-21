# Fase exercise-library — más ejercicios, ordenados y a la vista

Repo: `/home/juan/b2first-tracker`, HEAD `36806f8`.

## Pedido

Juan quiere **más lugares con ejercicios**, y que se muestren **ordenados para que el usuario elija** (nada aleatorio, eso ya se eliminó). Hoy hay materiales en bloques por destreza y 26 fuentes en Exam, pero faltan ejercicios reales y una vista donde verlos todos, ordenados y filtrables.

## 1. Ampliar el catálogo de fuentes reales

En `index.html`, `const PRACTICE_SOURCES` (~18800): sumar fuentes reales y gratuitas hasta **≥50 entradas** (hoy 26), repartidas entre rue / w / l / sp, cada una con `n`, `url`, `skill`, `kind` (`free`|`freemium`), `part` (lista o `[]`), `what` (una línea) y `mins`.

Reglas:
- **Solo URLs que respondan 200 al verificarlas** con `curl -s -o /dev/null -w "%{http_code}" -L -A "Mozilla/5.0"`. Si una da 403 por bot pero es un sitio real conocido, anotarlo en el reporte y no incluirla si no se puede confirmar.
- Nada de páginas inventadas ni de agregadores dudosos. Priorizar: Cambridge English, British Council, BBC Learning English, Exam English, Flo-Joe, Test-English, Write & Improve, Youglish, LyricsTraining, Conversation Exchange, Tandem, HelloTalk, y sitios con práctica B2 por parte.
- Sin duplicar URLs ya presentes.
- Documentar en el reporte la lista de URLs nuevas con su código HTTP.

## 2. Vista "Exercises" (biblioteca)

Nueva vista navegable, accesible desde:
- un botón "Browse all exercises / Ver todos los ejercicios" al final de cada panel de Materials de Today,
- un botón equivalente en la tarjeta de fuentes de Exam,
- y el menú, como ítem "Exercises" (o dentro de Practice como pestaña "Library"; elegir la opción que no rompa la navegación existente).

Contenido:
- Junta **material local** (de `MATERIALS`: papers, keys, lesson plans, audios, examiner notes) y **fuentes online** (`PRACTICE_SOURCES`) en una sola lista.
- Agrupada por paper (Reading & Use of English, Writing, Listening, Speaking) y, dentro, ordenada por **parte ascendente** y luego por tipo (paper, key, lesson, audio, online) y por minutos.
- Cada fila: nombre, tipo, parte(s), minutos, origen (local/online) y link "Open" (local abre el archivo servido por la app; online abre en pestaña nueva). Toda la fila clickeable.
- Controles arriba: buscador, chips de paper, chips de parte (1–4 + todas), toggle "Free only", y selector de orden **Exam order (default) / Shortest first / A–Z**.
- Contador visible ("128 exercises") y estado vacío claro cuando el filtro no devuelve nada.
- Sin botones de "dame uno" ni azar.

Mobile 390×844: una columna, filas ≥44 px, sin overflow horizontal, light y dark. i18n EN/ES simétrico. Sin handlers inline (`data-action`).

## 3. Reglas

- Solo `index.html`, tests y capturas. Sin backend nuevo, sin dependencias, sin tocar plan, límites, corrector, speaking, listening propio, cuentas, CSP ni landing.
- No reintroducir nada del sistema aleatorio eliminado.
- Los links locales deben salir del índice `MAT`, no de rutas hardcodeadas.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_exercise_library.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_exam_sources_blocks.py; echo exit=$?
```

Nuevo `tests/test_exercise_library.py`:
1. `PRACTICE_SOURCES.length >= 50`, sin URLs duplicadas y todas con `https://`.
2. La vista lista **todas** las entradas (local + online) y el contador coincide con la cantidad renderizada.
3. Orden por defecto: paper en orden fijo y, dentro, parte ascendente.
4. Cambiar a "Shortest first" reordena por `mins` ascendente; "A–Z" ordena alfabéticamente.
5. Filtros: paper Listening deja solo Listening; parte 2 deja solo parte 2; "Free only" excluye `freemium`; buscador filtra por nombre.
6. Cada fila tiene un `href` no vacío; las locales empiezan con `/material/` o el endpoint real que use la app.
7. 390×844 sin overflow y EN/ES con los mismos controles.
8. Los botones de entrada desde Today y Exam abren la vista.

Capturas: `library_390_light.png`, `library_390_dark.png`, `library_1280_light.png`.

## Cierre

Commit `feat(practice): biblioteca de ejercicios ordenada y catálogo ampliado`. Sin deploy.
