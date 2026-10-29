# PROMPT — Fase 6: plan semanal generado desde el diagnóstico + errores

Sos un ingeniero senior. Repo `/home/juan/b2first-tracker` (cwd correcto). Español
rioplatense. **Este turno es para CODIFICAR, no para narrar.**

## Por qué

El tracker ya sabe qué partes falla el usuario (`D.diag.weakest`, `D.errs[].tax`) pero el
plan de la pestaña PLAN sigue siendo una rotación genérica. Un plan que no mira los datos
es decoración. Esta fase conecta las dos cosas — **sin IA**, con reglas deterministas y
explicables (así se puede testear y el usuario ve POR QUÉ le toca cada cosa).

## Tarea A — `buildWeeklyPlan(D)` en `index.html`

Función pura, sin efectos secundarios, en la sección PLAN del `<script>`:

```js
function buildWeeklyPlan(){ /* devuelve {slots:[5], reason:{}, source:{}} */ }
```

Entrada: `D.diag.weakest` (array de partes, peor primero), `D.errs` (taxonomía),
`D.log` (últimos 14 días), `D.settings.weekGoal` (default 5).

Reglas (en este orden, deterministas):
1. **Prioridad por debilidad**: las 3 partes más débiles del diagnóstico ocupan 3 de los 5
   slots. Si no hay diagnóstico (`D.diag` vacío), devolver `{slots:[], needDiag:true}`.
2. **Escritura obligatoria**: 1 slot SIEMPRE es Writing (`type:'w'`). Si el usuario nunca
   hizo Writing (`D.log` sin `type:'w'`), ese slot va primero y `reason` dice
   `"nunca practicaste Writing y es 25% del examen"`.
3. **Listening de refuerzo**: 1 slot es Listening (`type:'l'`), preferentemente la parte
   con más `D.errs` de tipo `T-MIS`.
4. **Ajuste por taxonomía** del resto:
   - mayoría `L-GAP` → slots de UoE parte 1 y 3 (léxico / word formation)
   - mayoría `G-ERR` → UoE parte 2 y 4 (gramática / transformación)
   - mayoría `T-MIS` → Reading parte 5 y 6 (inferencia / cohesión)
   - mayoría `T-LIM` → cualquier slot con `timed:true` (avisar "modo examen, cronómetro")
   - empate o sin errores → rotación por `D.settings.rueCycle`
5. **Duración**: 45 min por slot (`D.settings.slotMin` si existe, default 45). Total semanal
   = `weekGoal` slots, nunca más que eso.
6. **Sin repetir la misma parte el mismo día**: días asignados en orden lun→vie.

Cada slot: `{day:'lun', part:1, type:'ue', min:45, timed:false, reason:'...'}`.
`reason` es una frase corta en español rioplatense que cita el dato que la justifica
(ej.: `"parte 3 es tu punto más flojo (1/2 en el diagnóstico)"`).

**Prohibido** llamar a ninguna IA acá. Reglas puras.

## Tarea B — UI en la pestaña PLAN

Nueva card arriba de todo, **"Plan de la semana"**:

- 5 filas: `lun · Parte 3 · UoE word formation · 45 min` + el `reason` en gris debajo.
- Botón `Empezar` en cada fila → navega a la pestaña PARTES con el filtro de esa parte
  (usá el mecanismo existente; no inventes otro).
- Botón `Regenerar` (fuerza recálculo) y `¿Por qué esto?` que abre un `<details>` con
  la lista de datos usados: diagnóstico (partes + aciertos), conteo por taxonomía,
  sesiones en 14 días, y `weekGoal`.
- Si `needDiag`: la card muestra *"Hacé el diagnóstico de 10 min y armo tu semana"* con
  botón que lleva a `#view-diag`.
- Si no hay datos suficientes (sin diagnóstico y sin errores), no inventar plan.

## Tarea C — `tests/test_plan.py` (Playwright, servicio en 8088)

Sembrar `localStorage` con fixtures inyectados por `page.evaluate` (patrón de `test_streak.py`),
no usar datos reales del owner. Asserts (≥7):
1. sin diagnóstico → `needDiag` visible, 0 slots
2. con diagnóstico `weakest:[3,2,7]` → esas 3 partes aparecen en los slots
3. siempre exactamente 1 slot de Writing y 1 de Listening
4. `weekGoal:3` → 3 slots; `weekGoal:6` → 6 slots
5. mayoría `L-GAP` → aparece parte 1 o 3; mayoría `G-ERR` → parte 2 o 4
6. ninguna parte repetida en el mismo día
7. `reason` de cada slot no está vacío y menciona el dato (contiene 'diagnóstico' o 'errores'
   o 'Writing')
8. `errores_js: []`

Los tests deben limpiar `localStorage` al empezar y no tocar `data/`.

## Prohibido

- Llamar a la IA para armar el plan. Reglas puras y testeables.
- Tocar `prompts.py`, `server.py`, el corrector de Writing, el diagnóstico ni el quick-log.
- Agregar dependencias. `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
cd tests && uv run --with playwright python test_plan.py 2>&1 | tail -16
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -5
cd tests && uv run --with playwright python test_diag.py 2>&1 | tail -4
```

## Commit

```
feat(plan): plan semanal determinista derivado del diagnóstico y la taxonomía de errores
```

Respondé al final **sólo** con: archivos tocados, salida literal de los 4 comandos, hash del commit.
