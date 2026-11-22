# Fase schedule-sync — agregar un día desincroniza Today (encabezado vs caja de ejercicio)

Repo: `/home/juan/b2first-tracker`, HEAD `af18370`.

## Reproducción reportada por Juan

Plan con lunes y viernes. Agrega domingo. Today muestra arriba "Sunday · Full writing", pero la caja de ejercicio de abajo dice "Monday · Full speaking". Encabezado y ejercicio no coinciden. Sospecha: al cambiar la cantidad de días, algo queda cacheado o mapeado por índice fijo.

## Diagnóstico esperado (verificar, no asumir)

Puntos a revisar en `index.html`:
- `renderToday()` (~21161) filtra `plan.slots` por `sl.day === todayLabel`; `todayTitleLabel(sl)` usa `sl.day` + `todayUnitBody(sl)`.
- Los estudios se seleccionan por id fijo: `selectSessionStudio('mon-a'|'mon-b'|'fri-a'|'fri-b')` y `UNIT_STUDIO`, con títulos tipo "Monday"/"Friday" en `CORE_SESSIONS`. Las tarjetas de estudio (`studioMonA`, `studioFriB`, …) conservan el día viejo aunque el plan ya sea domingo.
- `openPlanUnit(u)` pinta el estudio con la unidad planeada pero selecciona una tarjeta con nombre de día fijo.
- `repaintScheduleDrivenViews()` (~20638) repinta preview, weekly plan, Today y PracticeNow, pero **no** repinta los estudios ni su encabezado.
- `getSlotSession`/`planUpcomingRows` asignan skill por índice de cola (`start+i`) y día por `days[i % days.length]`: al agregar un día cambia el reparto; hay que confirmar que todas las vistas usen la misma fuente (el slot del plan) y no índices cacheados.

El bug real puede ser uno o varios de esos; arreglar la causa, no el síntoma.

## Comportamiento esperado

1. Al agregar, quitar o cambiar un día/hora, **todas** las vistas se recalculan: Today (encabezado, unidad, minutos), "What comes next", plan semanal, Practice now y los estudios (título y contenido).
2. El encabezado de Today y la caja de ejercicio salen del **mismo objeto slot**: mismo día, misma destreza, misma parte y mismos minutos. Nunca "Sunday full writing" arriba y "Monday full speaking" abajo.
3. Las tarjetas de estudio dejan de mostrar nombres de día fijos cuando se abren desde el plan: muestran el día y la unidad reales del slot abierto (por ejemplo "Sunday · Full Writing, 80 min"). Si se abren desde el menú de estudios, muestran un rótulo neutro ("Session A" / "Session B"), sin "Monday/Friday" hardcodeado.
4. Al cambiar la cantidad de días, la cola sigue siendo continua (no se reinicia ni repite unidades ya hechas), y ninguna vista queda con datos del schedule anterior.
5. Persistencia: recargar la página después de agregar el día mantiene la coherencia.

## Alcance

- Solo `index.html` y tests. No tocar backend, límites, corrector, speaking, listening propio, CSP ni landing.
- Sin handlers inline. i18n EN/ES para los rótulos nuevos.
- Mobile 390×844 sin overflow.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_schedule_sync.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_today_unit_start.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_plan_rotation_continuous.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
```

Nuevo `tests/test_schedule_sync.py`:
1. Con schedule `[Mon 15:30, Fri 15:30]`, capturar el encabezado de Today y la unidad de la caja.
2. Agregar `Sun 17:00` desde la UI (`data-action="addScheduleRow"` + set del select) y verificar que el encabezado y la caja siguen coincidiendo en día, destreza y minutos.
3. Cambiar el día de un slot a otro y verificar lo mismo.
4. Quitar un día y verificar que no queda ninguna referencia al día eliminado en Today ni en el preview.
5. Recargar y confirmar persistencia de la coherencia.
6. Los estudios abiertos desde el plan muestran el día real del slot, no "Monday" fijo.

Captura: `tests/out/schedule_sync_390_light.png` con domingo agregado.

## Cierre

Commit `fix(plan): agregar o cambiar un día mantiene Today sincronizado`. Sin deploy.
