# Fase contents-order — los contenidos de la sesión empiezan por lo de esa parte

Repo: `/home/juan/b2first-tracker`, HEAD `03f6cb2`.

## Problema

Al abrir Contents de una unidad (por ejemplo Reading Part 2), la lista arranca con los sample papers completos ("All parts") y lo específico de la parte queda abajo. Juan espera ver primero el material de esa parte: paper/key de la parte, lesson plan de la parte, audio o fuente online de esa parte. Los papers completos van después, como referencia.

## Cambio

Dentro de **Contents de la sesión** (`#sessionContents` o el contenedor que corresponda):
1. Orden por defecto de esa lista (sin tocar la biblioteca global):
   - 1º ítems cuya `part` coincide exactamente con la parte de la unidad,
   - 2º ítems de la misma destreza sin parte específica (lesson plans generales),
   - 3º papers completos ("All parts"),
   - 4º fuentes online de esa parte,
   - 5º fuentes online generales de la destreza.
   Dentro de cada grupo, por tipo (paper, key, lesson, audio, online) y minutos.
2. El contador sigue mostrando el total real.
3. Si la unidad es de paper completo (full section), no hay parte: se mantiene el orden actual.
4. La biblioteca global (`Library` fuera de la sesión) no cambia su orden.

## Alcance

Solo `index.html` y `tests/test_start_contents.py`. Sin backend ni otros archivos.

## Verificación

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_start_contents.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
```

Añadir a `test_start_contents.py`: al abrir Contents de Reading Part 2, la primera fila debe tener `Part 2` (no `All parts`), y ningún ítem "All parts" puede aparecer antes de un ítem de Part 2. Lo mismo para Writing Part 1 y Listening Part 3.

## Cierre

Commit `fix(practice): los contenidos de la sesión priorizan la parte abierta`. Sin deploy.
