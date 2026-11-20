# Fase practice-variety — ejercicios reales y variados sin repetir, también en Exam

Repo: `/home/juan/b2first-tracker`, HEAD `e582654`.

## Problema

El usuario siente poca variedad: siempre los mismos sample papers y las mismas fuentes. Quiere poder hacer **ejercicios reales y existentes**, en la práctica infinita (sin repetir), y que la pestaña **Exam** también le dé esos recursos, no solo la lista de links.

## Alcance

### 1. Pool de ejercicios (compartido)
Crear en `index.html` un pool único que junte dos cosas y exponga `exercisePool(skill, part)`:
- **Material local** (`MATERIALS`, cargado por `/api/material`): sample papers, keys, lesson plans, audios, examiner notes. Cada entrada con `id` = `rel` del material, `skill`, `part` (derivado del nombre/carpeta: `R&UoE`, `Writing`, `Listening`, `Speaking`, `lesson-plans` → parte por regex), `href`, `mins` estimado y `hint` de uso.
- **Fuentes online** (`PRACTICE_SOURCES`): ya tienen `skill`, `part`, `mins`, `what`.

Requisitos del pool:
- Al menos **60 entradas** en total con el catálogo actual (local + online), y ≥8 por destreza. Si el catálogo local no alcanza, no inventar ejercicios: bajar el mínimo del test a lo que exista y reportarlo.
- Cada entrada tiene `kind: 'local'|'online'`, `part: 'all'|1..4`, `mins`, `label`, `href`, `hint`.
- Deduplicar por `href` + `label`.

### 2. Selector sin repetición
`pickExercise(skill, part)`:
- Filtra el pool por destreza y, si `part` es numérico, incluye esa parte y las de `part:'all'`.
- Ordena por uso: `D.mat[id].n` ascendente, después `last` más viejo, después aleatorio estable.
- Excluye las **últimas 5 elecciones** de ese `skill+part`, guardadas en `D.pick[skill+part]` (persistido con `save()`).
- Devuelve `null` solo si el pool filtrado está vacío.
- Botón "Give me another" / "Dame otro" vuelve a elegir y nunca devuelve el mismo dos veces seguidas.

### 3. UI en Today
En cada tarjeta de destreza, arriba de los materiales, un bloque compacto:
- Botón primario "Practise a real exercise" / "Practicá un ejercicio real".
- Al tocar, muestra una tarjeta con: nombre del ejercicio, tipo (paper/lesson/online), tiempo estimado, hint de uso y link "Open" (abre en pestaña nueva o en la vista de materiales según `kind`).
- Debajo, "Give me another" y "Mark as done" (usa `matDone` si `kind==='local'`; si es online, registra `D.mat[id]` con el mismo formato).
- En 390×844 ocupa ≤180 px de alto.

### 4. UI en Exam
- Misma sección de materiales locales que Today (bloques colapsables con paper + keys, Full paper y Online), **reutilizando el renderer existente**, no una copia.
- Arriba de "Real mocks", un bloque "Practise a real exercise": selector de paper (R&UoE / Writing / Listening / Speaking) + parte opcional, botón "Give me one" y la tarjeta del ejercicio elegido con su link y hint. Debe usar el mismo `pickExercise`.
- Mantener intactos: Real mocks, `startFullMock`, `startRealMock`, `openSpeakingExam`, el selector manual `#exPaper`, la lista de fuentes con buscador y el botón "Open the full source library".

### 5. Reglas
- Solo `index.html` y tests. Sin backend nuevo. Sin dependencias. Sin handlers inline (`data-action`).
- No tocar límites, plan, listening propio, cuentas, owner, CSP ni landing.
- i18n EN/ES simétrico para todo lo nuevo. Light/dark, `prefers-reduced-motion`, targets ≥44 px.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_practice_variety.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_exam_sources_blocks.py; echo exit=$?
```

Nuevo `tests/test_practice_variety.py`:
1. `exercisePool` devuelve ≥60 entradas totales y ≥8 por destreza (o el mínimo real del catálogo, documentado en el test).
2. 10 llamadas seguidas a `pickExercise('rue', null)` devuelven ≥8 ids distintos y nunca dos iguales consecutivas.
3. Las últimas 5 elecciones no se repiten; al agotar el pool, cicla por los menos usados (LRU) sin quedar trabado.
4. "Mark as done" incrementa `D.mat[id].n` y la próxima elección evita ese ejercicio si hay otros.
5. Exam: el bloque "Practise a real exercise" existe, "Give me one" muestra una tarjeta con link y hint, y la sección de materiales locales aparece con el mismo renderer (bloques colapsables).
6. 390×844: sin overflow, EN/ES, 0 pageerrors.

Capturas: `practice_pick_390_light.png`, `exam_pick_390_dark.png`, `exam_materials_1280_light.png`.

## Cierre

Commit `feat(practice): ejercicios variados sin repetir, también en Exam`. Sin deploy.
