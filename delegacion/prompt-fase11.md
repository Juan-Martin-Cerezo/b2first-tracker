# PROMPT — Fase 11: blindaje (auditoría de seguridad aplicada)

Sos un ingeniero senior de seguridad. Repo `/home/b2first-tracker`. **Este turno es para CODIFICAR.**
Todo en inglés.

## Contexto: la app ya está pública

`https://vps-server.tail40095b.ts.net` corre en una Raspberry Pi doméstica, con registro abierto
y datos de usuarios reales en archivos JSON. `server.py` es `ThreadingHTTPServer` + stdlib.

## Auditoría hecha por el orquestador — qué ya está y qué falta

| Control | Estado |
| --- | --- |
| Passwords hasheadas (pbkdf2-sha256, 200k, salt por usuario) | **OK, no tocar** |
| Auth en el server, no sólo front (Bearer + `_auth()`) | **OK** |
| Rate limit en login/register/password/progress | **OK** |
| Secretos fuera del repo (`~/.config/b2first/ai.env`) | **OK** |
| Timeout en la llamada externa de IA (`AI_TIMEOUT`) | **OK** |
| Un usuario no puede leer el id del otro (403) | **OK + test** |
| Tokenless owner path bloqueado si hay proxy | **OK + test** |
| **Sanitizar `user` de la query** | **FALTA** (hoy se usa crudo en `os.path.join`) |
| **Lock de escritura por usuario / store** | **FALTA** (read-modify-write sin lock) |
| **Headers de seguridad + CORS explícito** | **FALTA** |
| **Request id en logs, sin tokens** | **FALTA** |
| **`/api/health` que revise el storage** | **FALTA** |
| **`schema_version` + migración versionada del progreso** | **FALTA** |
| **429 en saturación, nunca 500** | **Parcial** |
| **Reset de contraseña por el dueño** | **FALTA** |
| Pagos idempotentes · índices · N+1 · pool · transacciones SQL | **N/A: no hay base de datos ni pagos** |

## Tarea A — Sanitizar identificadores (path traversal)

- `_safe_uid(raw)`: acepta sólo `[A-Za-z0-9._-]{1,64}`, rechaza `..`, `/`, `\`, leading dot.
  Aplicarlo a **todo** `user` que venga de query, body o path, antes de cualquier `os.path.join`.
- Si el id no es válido → `400 {"error":"invalid user id"}` (nunca 500, nunca tocar disco).
- Verificá también `store.py`: `_prog_file`, `_bk_dir`, `_users_file` no deben construir rutas con
  input sin pasar por `_safe_uid`. Un id inválido debe levantar `ValueError`, no escribir afuera.
- Test: `?user=../../etc/passwd`, `?user=..%2f..%2froot`, `?user=.hidden`, `?user=` (vacío),
  `?user=` + 200 chars → todos `400` y **ningún archivo creado fuera de `data/users/`**
  (el test verifica con `os.path.exists` sobre rutas candidatas).

## Tarea B — Escrituras concurrentes

- `_STORE_LOCK = threading.Lock()` en `store.py`, tomado en `create_user`, `delete_user`,
  `update_user` y en el read-modify-write de `users.json`.
- Lock por usuario para el progreso: `_prog_lock(uid)` (dict de `Lock` con guard) alrededor de
  backup + escritura, para que dos PUT simultáneos no se pisen el backup.
- Test: 20 `PUT` concurrentes del mismo usuario en 20 threads → el archivo final es JSON válido,
  `users.json` sigue siendo JSON válido, y no quedan `.tmp` huérfanos.

## Tarea C — Headers y CORS

En `_send`/`_send_json`, agregar siempre:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy: geolocation=(), camera=(), microphone=()
Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'
Cache-Control: no-store   (sólo en /api/*)
```

- **CORS cerrado**: sin `Access-Control-Allow-Origin` en las respuestas. Si llega un `OPTIONS`,
  responder `204` sin headers CORS permisivos. Nada de `*`.
- Test: los 6 headers presentes en `/` y en `/api/config`; `OPTIONS /api/progress` no devuelve
  `Access-Control-Allow-Origin`; la página sigue funcionando (JS inline permitido por CSP).

## Tarea D — Logs con request id, sin datos sensibles

- Generar `rid = secrets.token_hex(4)` por request, guardarlo en `self._rid`.
- Formato de log (stdout, una línea):
  `2026-10-30T12:00:00Z rid=ab12cd34 GET /api/progress 200 12ms ip=1.2.3.4`
- **Nunca** loguear `Authorization`, tokens, passwords, ni el cuerpo del request.
  Redactar: si el body se loguea por debug, `"***"` en `password`, `token`, `key`.
- Devolver `X-Request-Id` en la respuesta.
- Test: 3 requests → cada línea de log tiene `rid=`, ninguna contiene el token usado, y la
  respuesta trae `X-Request-Id` distinto por request.

## Tarea E — `/api/health`

`GET /api/health` → `200` sólo si:
- `DATA_DIR` existe y es escribible (crear y borrar un archivo de prueba de 8 bytes),
- `users.json` parsea como JSON,
- cada `uid` de `users.json` tiene su carpeta (o se reporta `missing_dirs`),
- devuelve `{"ok":true,"users":N,"data_dir":"...","version":"1.0.0","uptime_s":N}`.

Si algo falla → `503 {"ok":false,"error":"...","check":"data_dir|users_json|dirs"}`.
Sin auth (es un health check), pero **sin filtrar rutas absolutas** si `B2_PUBLIC_HEALTH=0`.
Test: 200 con datos sanos; 503 si `DATA_DIR` es de sólo lectura (chmod 0500).

## Tarea F — Migración versionada del progreso

- `PROGRESS_SCHEMA = 2`. Al leer un progreso sin `schema_version`, aplicar migración:
  `1→2` (agregar `profile: null`, `onboarded: false`, `settings.__v: 2`), guardar de nuevo con
  `schema_version: 2`, y dejar el original en `backups/pre-migration-<ts>.json`.
- Idempotente: correr dos veces deja el mismo resultado y **no** duplica backups.
- Nunca borrar campos desconocidos (los usuarios futuros pueden tener más).
- Test: fixture v1 → GET devuelve `schema_version=2`; segunda GET no crea otro backup.

## Tarea G — Errores nunca 500 por saturación

- Envolver el router en `try/except`: `ConnectionResetError`/`BrokenPipeError` → log y cerrar sin
  escribir; `TimeoutError` → `504`; excepción inesperada → `500 {"error":"internal","rid":"..."}`
  (con rid, sin stack trace al cliente).
- Si un lock no se puede tomar en 5 s → `429 {"error":"busy","retry_after":2}` + `Retry-After: 2`.
- Test: forzar excepción en un handler (monkeypatch) → 500 con `rid` y sin `Traceback` en el body.

## Tarea H — Reset de contraseña por el dueño (sin email)

- Script `tools/reset_password.py` (stdlib, se corre en la Pi):
  `python3 tools/reset_password.py <username> [--generate]`
  imprime la contraseña nueva (o usa la pasada), la hashea igual que `server.py`, invalida todos
  los tokens de ese usuario. **No** imprime el hash. Funciona con `DATA_DIR` por env.
- No exponer endpoint HTTP de reset (no hay email verificado → sería un agujero).
- Test: crear usuario, resetear, login con la nueva funciona, la vieja falla (401).

## Tarea I — `tests/test_hardening.py` (≥16 asserts)

Un solo archivo, server propio en puerto libre con `DATA_DIR` temporal. Cubre A–H. Imprimí un
bloque JSON `{"assert": "OK ..."}` como los otros tests, y `errores_js` no aplica acá.

## Prohibido

- Dependencias nuevas. Tocar la lógica de plan/diagnóstico/corrector/racha.
- Deployar, reiniciar servicios, tocar systemd/Docker/Coolify/`~/.config`.
- Loguear secretos. Romper `test_multiuser.py`, `test_legacy_guard.py`, `test_sync.py`, `test_demo.py`.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
cd tests && python3 test_hardening.py 2>&1 | tail -24
cd tests && python3 test_legacy_guard.py 2>&1 | tail -3
cd tests && uv run --with playwright python test_multiuser.py 2>&1 | tail -4
cd tests && uv run --with playwright python test_demo.py 2>&1 | tail -3
```

## Commit

```
security: validate ids, lock writes, harden headers, request ids and health check
```
