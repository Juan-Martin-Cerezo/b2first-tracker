# PROMPT — Fase 3: Diagnóstico inicial (cold-start placement de 12 ítems)

Sos un ingeniero senior. Repo `/home/juan/b2first-tracker` (cwd correcto). Español
rioplatense. **Este turno es para CODIFICAR, no para narrar.**

## Por qué existe esta fase (dato real)

El usuario tiene **5 sesiones registradas en 67 días, 0 errores, 0 Writing, 0 Speaking**.
El tracker le muestra un plan genérico porque no tiene datos. Un plan sin diagnóstico es
adivinanza. El diagnóstico genera esos datos en **10 minutos**.

## Tarea A — `material/diagnostico.json`

12 ítems **originales** (escritos por vos para este proyecto), nunca copiados de exámenes
Cambridge. Formato:

```json
{"version":1,"min":10,"items":[
  {"id":"d01","part":1,"skill":"Multiple-choice cloze","stem":"... ______ ...","options":["A","B","C","D"],"answer":2,
   "taxonomy":"L-GAP","explain":"...por qué la correcta lo es y por qué la trampa típica falla..."},
  ...
]}
```

Cobertura obligatoria (12 ítems):
- parte 1 ×2 (cloze de opción múltiple — léxico)
- parte 2 ×2 (Open cloze — gramática: preposiciones, verbos, determinantes)
- parte 3 ×1 (Word formation)
- parte 4 ×1 (Key word transformation)
- parte 5 ×2 (Reading: comprensión literal e inferencia)
- parte 6 ×1 (Gapped text: cohesión)
- parte 7 ×2 (Multiple matching)

Reglas de los ítems:
- Nivel **B2 real**, no C1 disfrazado ni A2 disfrazado.
- `answer` es el índice 0–3 de la opción correcta.
- `taxonomy` ∈ `L-GAP` (léxico) · `G-ERR` (gramática) · `T-MIS` (no entendió el texto) · `T-LIM` (se quedó sin tiempo, lo setea el front al expirar).
- `explain` en español rioplatense, ≤ 240 caracteres, y **sólo se muestra después** de responder todo (si no, contamina el diagnóstico).
- Sin marcas, nombres comerciales ni referencias a libros.

## Tarea B — `server.py`: servir el diagnóstico

- `GET /diagnostico.json` → devuelve `material/diagnostico.json` con
  `Content-Type: application/json`. Usá el mismo patrón que la ruta de `libros.json`
  (leer el archivo, cachear en memoria, 404 claro si falta). **Sin auth**: es material público.
- Validación al leer: si el JSON no tiene 12 items o algún `answer` está fuera de 0–3,
  responder 500 con `{"error":"diagnostico invalido"}`. No servir datos rotos.
- No tocar ninguna otra ruta.

## Tarea C — Frontend: flujo de diagnóstico en `index.html`

1. **Entrada**: banner en la vista HOY (`renderToday`) visible sólo si
   `D.log.filter(x=>x.type==='diag').length===0`. Texto: *"Diagnóstico inicial · 10 min ·
   12 preguntas"* + botón `Empezar`. También accesible desde el nav como
   `<button data-view="diag">🧭 Diag</button>` (idempotente: no lo dupliques si ya existe).
2. **Vista `#view-diag`**: una pregunta a la vez. Muestra `Parte N/total`, el `stem`,
   4 botones de opción, contador `⏱ mm:ss` global de 10 min y botón `Saltar`.
   Sin feedback durante la prueba.
3. **Al terminar las 12 (o al agotarse los 10 min)**:
   - `correct` = aciertos; los ítems no respondidos o respondidos después del timeout
     cuentan como incorrectos con `taxonomy: "T-LIM"`.
   - Guardar en `D.log`: `{type:'diag', date:dayKey(new Date()), correct, total:12, min: Math.round(elapsedMin), note:'diagnóstico inicial'}`.
   - Por cada ítem incorrecto, agregar a `D.errs`:
     `{date, tax: item.taxonomy, part: item.part, note: item.explain.slice(0,120), src:'diag'}`.
   - Guardar `D.diag = {date, correct, total, byPart:{1:{ok,n},...}, weakest:[top 3 parts]}`.
   - `save()` + `refreshAll()`.
4. **Pantalla de resultados** (dentro de `#view-diag`):
   - Total `X/12` con color (≤4 rojo, 5–8 ámbar, ≥9 verde).
   - Tabla por parte: `Parte | aciertos/total | barra`.
   - **3 debilidades** ordenadas por peor ratio, cada una con 1 recomendación concreta
     y un botón que lleva a la pestaña PARTES con ese filtro aplicado
     (usá el mecanismo existente de `PARTS[]`; no inventes otro).
   - Botón `Repetir diagnóstico` (borra `D.diag` y vuelve a empezar) y `Ver plan`.
5. Si el fetch de `/diagnostico.json` falla: mostrar error claro y **no** romper la app.

## Tarea D — `tests/test_diag.py` (Playwright, contra el servicio en 8088)

Asserts obligatorios (≥7):
1. `/diagnostico.json` → 200 y `len(items)==12`
2. los 12 ítems tienen 4 opciones y `answer` en 0–3
3. las 7 partes están cubiertas y los conteos coinciden con la tabla de la Tarea A
4. un `explain` **no** aparece en el DOM antes de terminar
5. responder todo correcto (usando `answer` del JSON) → `D.log` tiene un `type:'diag'`
   con `correct===12` y `D.errs` vacío
6. responder todo mal → 12 entradas nuevas en `D.errs` con `tax` válida y `src:'diag'`
7. `D.diag.byPart` tiene 7 claves y `weakest.length===3`
8. el banner del diagnóstico **desaparece** de HOY después de completarlo
9. `errores_js` vacío al final

Los tests deben limpiar `localStorage` al empezar (patrón de los tests existentes) y no
tocar `data/` real.

## Prohibido

- Copiar texto de exámenes Cambridge (copyright). Ítems propios.
- Agregar dependencias. Tocar `store.py`, `data/`, `tests/test_final.py` u otros tests.
- Romper el corrector de Writing ni la racha.
- `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import json;d=json.load(open('material/diagnostico.json'));print('items',len(d['items']),'partes',sorted({i['part'] for i in d['items']}))"
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
curl -s -o /dev/null -w 'diag json -> %{http_code}\n' http://127.0.0.1:8088/diagnostico.json
cd tests && uv run --with playwright python test_diag.py 2>&1 | tail -15
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -5
```

## Commit

```
feat(diag): diagnóstico inicial de 12 ítems con mapeo a taxonomía de errores y recomendaciones
```

Respondé al final **sólo** con: archivos tocados, salida literal de los 5 comandos, hash del commit.
