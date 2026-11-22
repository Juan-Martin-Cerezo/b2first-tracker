# Fase unify-library — una sola biblioteca en lugar de Exercises + Resources

Repo: `/home/juan/b2first-tracker`, HEAD `db08dcd`.

## Decisión de producto

"Exercises" (biblioteca nueva, 175 ítems) y "Resources" (vista vieja con `#resourcesList` y `resourceGrid`) son lo mismo visto dos veces: papeles, keys, audios, sample cards y fuentes. Juan quiere **unificarlas y reducir la superficie**. Queda **una sola** biblioteca, dentro de Practice.

## Alcance

### 1. Una vista única
- La vista `v-exercise-library` (o como se llame la nueva) pasa a ser una **pestaña dentro de Practice**: `Practice` con dos tabs: "By part" (lo actual, `#partsList`) y "Library" (la biblioteca). Default: "By part".
- La biblioteca incluye **todo**:
  - materiales locales (papers, keys, lesson plans, audios, examiner notes),
  - fuentes online (`PRACTICE_SOURCES`),
  - y lo que hoy vive en Resources: sample cards, libros y links de referencia (`resourceGrid`/`RES_PAPERS`), agrupados al final como sección "Reference" dentro de la biblioteca, con el mismo filtro/buscador.
- Conservar buscador, chips de paper y parte, "Free only", orden (Exam order / Shortest first / A–Z), contador y estado vacío.

### 2. Eliminar redundancia
- Borrar la vista `#v-resources` y su lógica (`renderResources`, `RES_PAPERS`, `resourceGrid` si queda sin uso, `clearResourcesFilter`), salvo lo necesario para alimentar la sección Reference.
- Quitar del menú y del "More" sheet las entradas "Resources" y "Exercises"; que Practice quede como único punto de entrada.
- Redirigir cualquier `showView('resources')` existente a `showView('practice')` + tab Library, sin romper links viejos ni tests que los usen (actualizarlos).
- Eliminar claves i18n huérfanas de Resources/Exercises y sus `ACTIONS`.

### 3. Textos
- Renombrar títulos: Practice → "Practice", tabs "By part" / "Library"; subtítulo de Library: "Every paper, key, audio and verified source in one ordered list."
- Actualizar README (sección de materiales/vista), landing si menciona "Resources" como pestaña, y `docs/` si aplica.
- i18n EN/ES simétrico.

### 4. Reglas
- Solo `index.html`, tests, README y docs. Sin backend, sin dependencias, sin tocar plan, límites, corrector, speaking, listening propio, CSP ni landing más allá de un nombre de pestaña si aparece.
- Mobile 390×844 sin overflow, targets ≥44 px, light/dark, sin handlers inline.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_exercise_library.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_practice_split.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_sources.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
```

`test_exercise_library.py` actualizado: la biblioteca incluye las entradas de referencia, el contador total coincide, y ya no existe `#v-resources` ni entrada de menú "Resources".

Capturas: `library_390_light.png`, `library_390_dark.png`, `practice_tabs_1280_light.png`.

## Cierre

Commit `refactor(practice): una sola biblioteca con Practice y Resources unificados`. Sin deploy.
