# B2 First Tracker — Sistema de Alto Rendimiento

Tracker web para preparar el **Cambridge B2 First (FCE)** con inmersión real:
rotación automática de los 15 ejercicios del examen, timers con los tiempos
oficiales de Cambridge, metric gates por etapas, estadísticas por ejercicio y
catálogo de material (PDFs + audio) servido desde la misma Pi.

> **Idioma del proyecto: español rioplatense.** El plan de estudio completo vive en
> [plan.md](plan.md). Si vas a trabajar en el código, leé primero [agents.md](agents.md).

## Arquitectura

```
┌─────────────┐   GET /   ┌────────────────────────────────────────────┐
│  PC / cel  │ ─────────► │  server.py  (stdlib Python, puerto 8088)  │
│  Tailscale │            │  · /          → index.html (tracker)      │
└────────────┘            │  · /libros    → material con visor+audio │
                          │  · /libros.json → catálogo para el tracker │
                          │  · /files/…   → PDF/MP3 con Range (audio) │
                          │  · /api/progress → progreso (GET/PUT)     │
                          └───────────────────┬────────────────────────┘
                                              │ escanea dinámicamente
                                      ~/Descargas/b2-first/
                                      (6 exámenes oficiales + handbook)
```

- **Frontend**: `index.html` — app single-file (HTML + CSS + JS inline, ~1.300 líneas). Cero dependencias, cero frameworks. Datos en `localStorage` (clave `b2first_tracker_v1`) + **sincronización con la Pi**.
- **Backend**: `server.py` — HTTP server **solo stdlib** (sin pip install). Sirve el tracker, el material y el JSON del catálogo.
- **Persistencia**: el progreso se guarda en la Pi (`data/progress.json`) con **backups automáticos** en `data/backups/` (último que guarda gana). Cada `save()` del tracker hace push a la Pi; al abrir la página se baja lo más reciente. El estado se ve en el footer (✔ sincronizado / ⚠ modo local).
- **Servicio**: `b2first.service` — unidad systemd (Restart=always), corre desde este repo.

## Archivos

| Archivo | Rol |
|---|---|
| `index.html` | El tracker completo (UI + lógica + comentarios del modelo de datos en el header del `<script>`) |
| `server.py` | Portal HTTP (comentado línea por línea) + persistencia del progreso |
| `data/progress.json` | Progreso sincronizado (se crea solo con el primer guardado) |
| `data/backups/` | Backups automáticos de cada guardado (los últimos 20) |
| `b2first.service` | Unidad systemd (copiar a `/etc/systemd/system/`) |
| `plan.md` | **El plan de inglés completo** (objetivo, sesiones, gates, rúbrica, material) |
| `agents.md` | Onboarding para el próximo agente/desarrollador |
| `tests/` | Suite de regresión (Playwright + Chromium headless) |

## Deploy (en la Pi)

```bash
# Dependencias: ninguna (solo Python 3 stdlib). El material va en ~/Descargas/b2-first/
sudo cp b2first.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now b2first
```

Verificá: `systemctl status b2first` → `active` · `curl http://127.0.0.1:8088/` → 200.

## Acceso

| Desde | URL |
|---|---|
| La propia Pi | http://127.0.0.1:8088 |
| Red Tailscale | http://100.112.213.66:8088 (IP directa; MagicDNS apagado en el tailnet) |
| LAN | http://<ip-local-de-la-pi>:8088 |

## Testing

```bash
cd tests && uv run --with playwright python test_final.py   # suite principal (viewport móvil)
uv run --with playwright python test_sync.py                # persistencia + backups
uv run --with playwright python test_graf.py                # gráficos
```

Los tests abren la página servida con Chromium headless y verifican: sin overflow
horizontal en 390×844, tabs funcionando, rotación, gates, stats, modo examen,
cero errores JS, sincronización con la Pi y los 4 paneles de gráficos.
`test_sync.py` y `test_graf.py` levantan su propio server de prueba en un puerto
alternativo con datos temporales — no tocan el servicio real ni tu progreso.
Se ejecutan contra `http://127.0.0.1:8088` (servicio arriba).

## Material

`~/Descargas/b2-first/` contiene 6 exámenes oficiales completos (Sample 1, Sample 2,
For Schools 1, For Schools 2 + 2 del handbook) con PDFs, audio (MP3) y claves, más el
handbook. El server lo escanea en cada visita: **agregar un PDF/MP3 = aparece solo**.

## Sincronización

El tracker guarda en el navegador (`localStorage`) y **además sincroniza con la Pi**:
cada vez que guardás algo se sube automáticamente a `data/progress.json`, y al abrir
la página se baja lo más reciente. El footer muestra el estado (✔ sincronizado con la
Pi / ⚠ modo local si la Pi no responde). Regla: **último que guarda gana**, con backup
automático de la versión anterior (los últimos 20 en `data/backups/`). El Exportar/
Importar JSON manual de PROGRESO sigue disponible como respaldo extra.

## Notas operativas

- **Puerto 8088** (el 8080 lo ocupa un docker-proxy existente — no tocar).
- **Tailscale**: MagicDNS apagado → usar la IP directa.
- Los PDFs oficiales de Writing 2022 son **solo-imagen** (sin capa de texto) → las
  consignas se linkean directamente, no se extraen.
- El repo es la **única fuente de verdad**: al editar, reiniciar el servicio con
  `sudo systemctl restart b2first` (el WorkingDirectory ya apunta acá).
