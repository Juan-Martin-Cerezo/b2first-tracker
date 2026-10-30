# PROMPT — Fase 23: capacidad real (cientos de usuarios)

Sos ingeniero senior de performance en Python. Repo `/home/juan/b2first-tracker`. **CODIFICAR.**
Inglés en código/commits. Backend sigue siendo **stdlib only**.

## Medición que motivó esta fase (real, en `localhost`, 100 concurrentes)

```
/            -> 130 req/s, p50 358 ms, p95 2235 ms, max 6935 ms
/api/health  -> 2262 OK y 3638 x 503   (el 503 era el rate limit, no el CPU)
/cabeza      -> Content-Encoding: gzip, Content-Length: 109307, Cache-Control: no-cache, SIN ETag
```

Tres causas identificadas en el código:

1. `server.py:2095` — `gzip.compress(body, 6)` **en cada request**, sobre ~342 KB de
   `index.html`. ~15-20 ms de CPU por visita en un Pi 5.
2. No hay `ETag` ni `Last-Modified`: cada recarga vuelve a bajar los 109 KB completos.
3. `server.py:2178` — `_rate_limited("api:" + _real_ip(self), 300, 60)` aplica a **todas** las
   rutas `/api/*`, incluso autenticadas. Detrás de CGNAT o de un WiFi de escuela, 50 alumnos con
   una sola IP = 15.000 req/min contra un techo de 300. **Es el bloqueante #1 para "cientos de
   usuarios"**, y no es de capacidad del servidor.

## A — Cachear el payload comprimido

- Cache en memoria (`dict`) por ruta + `mtime` + `size` del archivo: `{body_gz, etag}`.
- `ETag` = hash corto del contenido comprimido (no del mtime a secas: dos deploys con el mismo
  mtime no deben compartir ETag).
- Si `If-None-Match` coincide → **`304` sin body** y sin recomprimir.
- `Last-Modified` desde el mtime + soporte de `If-Modified-Since`.
- Mantené `Vary: Accept-Encoding` (si falta, un proxy puede servir gzip a un cliente que no lo
  acepta). Si el cliente no acepta gzip, serví el cuerpo original desde la misma cache.
- No caches respuestas con `Authorization`, ni `/api/*`, ni nada dinámico. Solo estáticos.
- Cache invalidation: el cache se valida por `(ruta, mtime, size)`, sin TTL. Un `touch` del archivo
  debe invalidarlo **en el request siguiente**, sin reiniciar el servicio.

**Medición obligatoria antes/después** con `tests/load_spk.py`… no: usá
`tests/test_capacity.py` (lo escribís vos). Debe correr el servidor real, medir con `httpx`
(vía `uv run --with httpx`) y **fallar si no se cumple**:

- `GET /` con 100 concurrentes, 10 s: **p95 < 700 ms** y **0 respuestas 503/429**
  (hoy: p95 2235 ms).
- Segunda pasada de `GET /` con `If-None-Match` → todas `304`, body vacío.
- Un `touch index.html` → el ETag cambia.
- CPU: el p95 de la primera pasada debe ser al menos **2x mejor** que el baseline medido en el
  mismo test con la cache apagada (`B2_NO_CACHE=1`, que tenés que implementar para poder medir).

**Ojo con el test**: el rate limit por IP va a ensuciar la medición. Para medir capacidad, el
test debe correr con `B2_RATE_IP_API` alto (env var nueva) o desactivado, y **documentar** que el
límite real se prueba aparte en el punto B.

## B — Rate limit por usuario, no por IP

- Rutas **autenticadas**: límite por `user_id` (default **600 req/min**), no por IP. La IP sigue
  contando para `login`, `register`, `password` y todo lo que no tenga token válido (anti-abuso).
- Env vars: `B2_RATE_USER_API` (600), `B2_RATE_IP_AUTH` (30/min para login+register+password),
  `B2_RATE_IP_ANON` (300, lo que hoy es el global).
- El `429` debe seguir devolviendo `Retry-After` y un JSON `{"error":"too many requests"}`.
- Un usuario con token **nunca** puede comerse un 429 por culpa de la IP compartida: test
  explícito de dos usuarios distintos detrás de la misma IP, uno abusando y el otro no → el que
  no abusa tiene que seguir recibiendo 200.
- `/api/metrics` suma `rate_limited_by_user` y `rate_limited_by_ip` para poder verlo en producción.

## C — Sockets

- `CONNECTION_LIMIT` 200 → 512, `request_queue_size` 64 → 256, `daemon_threads = True`.
- Si el semáforo se agota, `503` con `Retry-After: 1` (no un cuelgue).
- Hilo por conexión: medí el RSS del server a 300 concurrentes y **dejalo escrito en el commit**.
  Si el RSS supera 200 MB, no subas el límite: bajalo y explicá por qué.

## D — Verificación y cierre

- `tests/test_capacity.py` (nuevo, ≥ 10 asserts, incluye los números de arriba).
- Las suites existentes siguen verdes: `test_final`, `test_sync`, `test_hardening`,
  `test_speaking_live`.
- Actualizá `README.md` con una tabla de capacidad **medida** (no estimada) y `HANDOFF.md`:
  el host es un **Pi 5 de 8 GB** (no 4 GB: `free -m` da 8062 MB y `nproc` 4), con fecha de la
  medición. Si un número no lo mediste, no lo escribas.
- Un commit `perf(server): cached gzip + ETag/304, per-user rate limits, 512 sockets`.
