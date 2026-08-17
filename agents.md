# AGENTS.md — Guía para quien trabaje en este proyecto

> Leé esto completo antes de tocar nada. 15 minutos acá ahorran horas.

## Quién es el usuario

**Juan**, 16 años, estudiante de secundaria técnica (ET21 Computación, CABA).
Se prepara **solo** para el Cambridge B2 First apuntando a **Grade A / C1**.
El producto lo usa él en su celular y su PC, en **español rioplatense**. Todo el
código, comentarios y mensajes van en español.

## Reglas duras del proyecto

1. **Sin piratería, jamás.** No linkear, buscar ni sugerir copias piratas de libros
   o exámenes. Siempre: material oficial gratuito de Cambridge, o comprar barato
   (MercadoLibre usado / Buscalibre).
2. **Nada de datos inventados.** Precios, métricas, resultados: todo verificado.
   Si no podés verificar algo, decilo y no lo pongas.
3. **Precios ARS verificados en la página de producto** (en Buscalibre el `data-precio`
   del listado miente ~1.5-1.6x; el real está en la página del producto).
4. **Avisar antes de borrar/reiniciar** cosas del sistema (el usuario lo pidió
   explícitamente). El deploy con `systemctl restart b2first` es seguro y esperado.
5. **No tocar** `.env`/config de fcc-claude ni servicios ajenos (docker-proxy en 8080).

## Stack (a propósito, mínimo absoluto)

- **Frontend**: un solo `index.html` (HTML+CSS+JS vanilla). **Cero frameworks,
  cero build, cero node_modules.** Así se abre desde cualquier dispositivo y se
  testea con Playwright sin cadena de compilación.
- **Backend**: `server.py`, Python **solo stdlib** (http.server). No hace falta
  pip install. No agregues dependencias sin hablar antes.
- **Datos**: todo en `localStorage` del navegador (clave `b2first_tracker_v1`).
  La sincronización PC↔celular es Exportar/Importar JSON manual (PROGRESO).
  No hay base de datos ni backend de datos — así se mantiene.

## Modelo de datos (resumen)

El objeto `D` persiste en localStorage. Ver el header de `<script>` en `index.html`
para la referencia completa con ejemplos:

- `D.log[]` — historial de práctica: `{type, date, part?, correct?, total?, min?, score?, kind?, s1?, s2?, p2?, note?}`
  - types: `ue` (UoE parte 1-7) · `w` (Writing con `kind`) · `l` (Listening completo /30, `p2`=errores Part 2) · `lp` (Listening por parte) · `sp` (Speaking) · `rue` (R&UoE completo, modo examen) · `fw` (Full Writing)
- `D.errs[]` — errores con taxonomía: `L-GAP` / `G-ERR` / `T-MIS` / `T-LIM`
- `D.stage` — etapa 0..2 · `D.overrides` — gates marcadas a mano · `D.weekOverrides` — rotación elegida a mano
- `D.settings` — TODO configurable (SETTINGS_DEFAULT en el JS): horarios, timers,
  ciclos de rotación (`rueCycle`/`wCycle`/`lCycle`/`spCycle`), umbrales de gates (`e0`/`e1`/`e2`)

**Regla de oro al agregar features**: cualquier cosa nueva que el usuario quiera
"poder cambiar" va a `D.settings` + inputs en la pestaña PLAN, con default sano.

## Estructura del código (orden en el `<script>`)

```
header (arquitectura + modelo de datos)
SETTINGS_DEFAULT / load / save / helpers
TIMER          → makeTimer + timers de sesión (leen D.settings)
SAVE HANDLERS  → saveUE / saveWR / saveL / saveSP / saveFull
LOG TABLE      → renderLog + edición inline + renderStats
GATES          → calcGates (lee D.settings) / renderGates / advanceStage
ERRORS         → renderErrs + registro con taxonomía
BOOKS          → BUY_BOOKS (25 libros, precios verificados) + MATERIAL (libros.json)
PLAN           → renderPlan / savePlan / resetPlan / applyTimers
EXAMEN+PARTES  → modo examen (EX_DUR, tiempos reales) + PARTS[] (15 ejercicios)
TODAY VIEW     → renderToday (rotación + banner) / setOv
NAV + INIT     → refreshAll central / loadMaterial
```

**refreshAll()** es el render central: se llama después de cada cambio de datos.
Si agregás un render nuevo, agregalo a refreshAll().

## Cómo probar

```bash
# El servicio debe estar activo (http://127.0.0.1:8088)
cd tests
uv run --with playwright python test_final.py    # suite principal
# test_exam.py y test_rot.py cubren modo examen y rotación
```

Los tests limpian sus propios datos de prueba. Antes de correrlos, asegurate de que
el server responda (curl http://127.0.0.1:8088/).

## Pitfalls conocidos (no los repitas)

- **PDFs de Writing 2022 = solo-imagen** (sin capa de texto): no se pueden extraer
  consignas con pypdf. Se resuelve con links directos + ubicación aproximada en la guía.
- **Puerto 8080 ocupado** por docker-proxy → el servicio corre en **8088**.
- **Tailscale MagicDNS apagado** → usar IP directa `100.112.213.66` (la Pi se llama `vps-server`).
- **MercadoLibre bloquea por IP** desde la Pi/VPS (muro + 403). La única vía legítima
  es el Chrome real del usuario vía CDP (ver skill `linux-desktop-control`).
- **Buscalibre**: precio real = página de producto, no el del listado.
- Los nombres de archivo del material tienen espacios → usar `quote()` en las URLs.
- `node --check` para validar el JS extraído del HTML (nunca deployar con syntax error).

## Deploy

El repo es la fuente única: `systemd` corre `server.py` desde acá
(WorkingDirectory=/home/juan/b2first-tracker). Después de editar:

```bash
python3 -c "import re;open('/tmp/app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/app.js
sudo systemctl restart b2first
```

## Roadmap / ideas pendientes (hablá con Juan antes)

- Repo remoto (GitHub) para que otro agente trabaje desde su máquina.
- Corrección de Writing automática por el asistente (rol examinador Senior Cambridge).
- Simulación de Speaking Parts 3-4 con la IA como compañero.
- Más material (los libros comprados → escanear/agregar PDFs a ~/Descargas/b2-first).
