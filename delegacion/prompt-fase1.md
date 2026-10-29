# PROMPT — Fase 1: Quick-log de 3 toques + racha (streak)

Sos un ingeniero senior. Trabajás en `/home/juan/b2first-tracker` (cwd ya correcto).
Español rioplatense. **Este turno es para CODIFICAR, no para narrar.**

## Contexto medido (no lo re-investigues)

- `index.html` = single-file, HTML + CSS + JS vanilla inline, **~4.250 líneas**. Cero
  frameworks, cero build. El `<script>` tiene secciones comentadas en este orden:
  `SETTINGS_DEFAULT` → `USUARIOS` (login/token) → `TIMER` → `SAVE HANDLERS` (`saveUE`,
  `saveW`, `saveL`, `saveSP`, `saveRUE`) → `LOG TABLE` (`renderLog`) → `GATES` →
  `ERRORS` → `BOOKS` → `GRÁFICOS` → `PLAN` → `EXAMEN+PARTES` → `TODAY VIEW` (`renderToday`) → `NAV + INIT`.
- Nav inferior (≈línea 989-996): botones `<button data-view="hoy|exam|partes|prog|graf|plan|err|libros">`.
- `SETTINGS_DEFAULT` ≈línea 2252. `save()` ≈2473 (persiste en localStorage **y** dispara
  `syncPush()`). `refreshAll()` ≈4173 es el render central: **todo render nuevo se agrega ahí**.
- Modelo: `D.log[]` con `{type, date, part?, correct?, total?, min?, score?, kind?, note?}`.
  `date` es string `YYYY-MM-DD` local. `D.settings` es la bolsa de configuración.
- Hay overlay de auth (`#authOverlay`) y de onboarding (`#onboardingOverlay`).
- Servicio systemd `b2first` en el puerto 8088, `WorkingDirectory` = este repo.

## Tarea A — FAB + modal de quick-log

1. Botón flotante `#qlFab` con `+`, fijo abajo a la derecha:
   `position:fixed;right:16px;bottom:76px;width:56px;height:56px;border-radius:50%;z-index:60`.
   En `@media (min-width:900px)`: `bottom:24px;right:24px`. No debe tapar el nav inferior.
2. Modal `#qlModal` (clase `overlay` existente) con 3 pasos y las clases del tema actual.
   **Paso 1**: chips de tipo — `Use of English` (`ue`), `Listening` (`lp`), `Writing` (`w`),
   `Speaking` (`sp`), `Examen completo` (`rue`). **Paso 2**: numpad numérico
   (`<input inputmode="numeric">` + chips de atajo 0-5/6-10/11-15/16-20/21-25/26-30) para
   `correct`/`total` (o nota 0-5 en `sp`, o `kind` en `w`). **Paso 3**: minutos,
   **precargados desde `D.settings`** (`ueMin` 50 · `listenMin` 40 · `writeMin` 35 · `sp`
   = `sp1Sec+sp2Sec` en min · `rue` = `even`/`odd`), más nota opcional libre.
3. Al confirmar: `D.log.push({type,date,part,correct,total,min,note})` → `save()` → `refreshAll()` →
   cerrar modal + feedback visual breve (toast o flash del FAB). Debe funcionar en celular
   a 360px de ancho.
4. Funciones nuevas con prefijo `ql`: `openQuickLog()`, `qlSetType(t)`, `qlNext()`,
   `qlSave()`, `closeQuickLog()`. Sin listeners inline que rompan el CSP actual (usá `onclick`
   como el resto del archivo, es coherente).

## Tarea B — Racha (streak) DERIVADA de `D.log`

Sección nueva `STREAK` en el `<script>`, después de `renderToday`, con:

```js
function dayKey(d)        // 'YYYY-MM-DD' en hora LOCAL (d.toLocaleDateString('sv-SE'))
function sessionDays()    // Set de dayKeys únicos de D.log, ignorando fechas futuras
function calcStreak()     // {current,longest,todayDone,atRisk,lastDate,freezeUsed,weekCount}
function renderStreak()   // pinta tarjeta en TODAY + pill en el footer
```

### Reglas exactas (implementalas tal cual)

1. Un día cuenta si tiene **≥1** entrada en `D.log`, de cualquier tipo y duración.
2. `current` = días consecutivos hacia atrás desde **hoy**.
3. Si hoy no hay sesión pero **ayer sí**: `current` se mantiene, `atRisk = true`.
4. `longest` = máxima racha histórica sobre todo el log.
5. **Escudo**: `D.settings.streakFreeze` (default **1**) = días muertos que se pueden
   saltear **por semana ISO** sin cortar la racha. Mostrar `🛡` cuando se usa.
6. **Meta semanal**: `D.settings.weekGoal` (default **5**) = días con sesión de lunes a domingo.
   Se muestra como anillo/barra `3/5`. No corta racha.
7. Días en `D.examDates` (array opcional de `YYYY-MM-DD`, default `[]`) **no cortan** la racha.
8. **Nunca** uses `toISOString()` para el dayKey: corre a UTC y rompe la racha de noche.
9. Log vacío → `current = 0` y la UI dice `Sin racha — empezá hoy`.
10. Si `D.settings.streakFreeze` y `D.settings.weekGoal` no existen, agregalos a
    `SETTINGS_DEFAULT` con 1 y 5, e inputs numéricos en la pestaña PLAN (regla del proyecto:
    todo lo configurable va a `settings` + PLAN).

### UI de la racha (en la vista TODAY, arriba del plan)

```
🔥 7 días     récord 12     🛡 1
[ ████████░░░░ ] 3/5 esta semana
⏰ hoy sin sesión — se corta a medianoche      ← sólo si atRisk
```

- Colores del tema actual (índigo/dark). Nada de emojis extra ni confetti.
- Animación permitida: un solo `transform:scale(1→1.06→1)` de 150ms al incrementar.
- Pill compacto `🔥 7` en el footer junto al badge de sync.
- `renderStreak()` se agrega a `refreshAll()`.

## Tarea C — test automatizado `tests/test_streak.py`

Seguí el patrón de los tests existentes (Playwright sync/async, `uv run --with playwright
python tests/test_streak.py`). Inyectá datos y verificá el DOM:

```python
await page.evaluate("""() => {
  D.log = [
    {type:'ue', date:'2026-10-27', correct:12, total:20, min:50},
    {type:'lp', date:'2026-10-28', correct:8, total:10, min:40}
  ];
  save(); refreshAll();
}""")
```

Casos obligatorios (7 asserts): (a) log vacío → `Sin racha`; (b) hoy+ayer → `2`;
(c) hueco de 1 día con escudo disponible → racha viva y `🛡`; (d) hueco de 2 días → cortada;
(e) fecha futura ignorada; (f) récord histórico correcto; (g) `weekCount` correcto.
Usá un usuario de prueba; **no toques `data/` del dueño**.

## Prohibido

- Agregar dependencias o build step.
- Reescribir el archivo: hacé ediciones quirúrgicas. `index.html` sigue siendo single-file.
- Tocar `server.py`, `store.py`, `data/`, o los otros tests.
- Notificaciones push, service worker, puntos, badges.
- `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria antes de terminar (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
curl -s -o /dev/null -w 'GET / -> %{http_code}\n' http://127.0.0.1:8088/
cd tests && uv run --with playwright python test_streak.py 2>&1 | tail -12
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -6
```

`test_streak.py` **y** `test_final.py` tienen que pasar. Si `test_final.py` falla por algo
que ya fallaba antes de tu cambio, decilo explícitamente en el resumen.

## Commit

```
feat(quicklog+streak): registro de sesión en 3 toques y racha derivada del log
```

Respondé al final **sólo** con: archivos tocados, salida literal de los 4 comandos, y hash
del commit.
