# PROMPT — Fase 10: multiusuario real (sin demo) listo para exponer en internet

Sos un ingeniero senior backend + seguridad. Repo `/home/juan/b2first-tracker`. **Este turno es
para CODIFICAR.** Todo en inglés: código, comentarios, mensajes, commits.

## El objetivo, en palabras del usuario

> "Quiero que lo puedan usar usuarios y que no sea demo."

Hoy hay dos mitades: el modo demo (usa la app pero no guarda nada) y las cuentas (registro abierto,
datos por usuario en `data/users/<uid>/`). Falta que **la instancia pública sea la app real**:
alguien se registra, usa la app, cierra el navegador, vuelve desde el celular y su progreso sigue.

El riesgo es concreto: la app corre en una Raspberry Pi doméstica y usa una key de IA del dueño
con **US$3.67** de saldo. Sin límites, un script la vacía en un minuto. Esta fase hace que la
instancia sea real y que un abuso no la tumbe ni la funda.

## Tarea A — Límites (en `server.py`, stdlib, en memoria)

Un helper reutilizable tipo `_rate(key, limit, window_s) -> bool` con dict + `deque`, protegido con
`threading.Lock` (el server es `ThreadingHTTPServer`). Limpiar entradas viejas en cada chequeo.

| Endpoint | Límite |
| --- | --- |
| `POST /api/register` | 5 / hora / IP |
| `POST /api/login` | 10 / 10 min / IP **y** 20 / hora / username |
| `POST /api/password` | 5 / hora / IP |
| `PUT /api/progress` | 60 / min / usuario |
| `POST /api/ai/writing` | ver Tarea C |

Al exceder: **429** con `{"error":"too many requests","retry_after":N}` y header `Retry-After: N`.
IP real: usar `X-Forwarded-For` **sólo** si el request viene de loopback/red interna (el proxy de
Coolify), si no `self.client_address[0]`.

## Tarea B — Límites de payload y de disco

- `PUT /api/progress`: cuerpo > **2 MB** → `413 {"error":"progress too large"}`.
  Antes de escribir, si el JSON serializado supera 2 MB → mismo 413. Nunca truncar en silencio.
- `POST /api/ai/writing`: cuerpo > **32 KB** → `413`.
- `GET /api/progress` con token inválido/expirado → `401` (no 500, no 200 vacío).
- `data/` con permisos `0700` para el directorio de cada usuario; los archivos `0600`
  (`os.makedirs(..., mode=0o700)` + `os.chmod`). Verificalo en el test.

## Tarea C — Cuota de IA (protege la key del dueño)

Variables: `B2_AI_DAILY_PER_USER` (default **8**), `B2_AI_DAILY_TOTAL` (default **80**).
Contador diario en memoria, con la fecha como clave (`date.today().isoformat()`), resetea solo.
Al exceder → **429** `{"error":"daily AI quota reached","reset":"YYYY-MM-DD"}`.

Si el usuario manda **su propia key** en el request (ya existe el campo), **no** descuenta cuota
del servidor y **no** usa la key del dueño. Ese es el camino para el que quiere corregir más.

## Tarea D — Cuentas: exportar y borrar

- `GET /api/account` → `{"uid":..., "created":..., "progress_bytes":N, "ai_left_today":N}` (auth).
- `GET /api/export` → descarga `application/json` con el progreso completo (`Content-Disposition`).
- `DELETE /api/account` `{password}` → valida contraseña, borra `data/users/<uid>/` completo y su
  registro en `users.json`, invalida sus tokens. Responde `200 {"ok":true}`; contraseña mal → `401`.
- En la UI: sección **Account** con `Export my data`, `Change password`, `Delete my account`
  (doble confirmación escribiendo `DELETE`).

## Tarea E — Tokens con vencimiento

- TTL **30 días** desde la emisión, deslizante: cada request autenticado extiende la fecha
  (persistida en `data/tokens.json`, junto al resto).
- Token vencido → `401 {"error":"session expired"}` y el frontend limpia el token y muestra login.

## Tarea F — Modo real en la UI (se va el cartel de demo)

- `config.demo === false` → no hay banner de demo. En su lugar:
  - **sin sesión**: pantalla de entrada `Log in` / `Create account` (una card, dos tabs), con
    reglas de contraseña visibles (`8+ characters`), y la línea:
    *"Your progress is stored on this server, not in a cloud."*
  - **con sesión**: badge `Synced` / `Saving…` / `Offline` en el footer (ya existe: reusalo).
- `config.register === "closed"` → oculta `Create account` (ya hecho en fase 8).
- Errores de auth en inglés y accionables: `Wrong username or password.` · `That username is taken.`
  · `Password must be at least 8 characters.` · `Session expired, please log in again.`
- La app debe seguir siendo usable **sin sesión** en modo demo público, pero con sesión en modo real:
  si `demo === false` y no hay token, se ve la pantalla de entrada y nada más.

## Tarea G — `tests/test_multiuser.py` (≥16 asserts)

Server propio, `DATA_DIR` temporal, `B2_DEMO=0`, `B2_REGISTER=open`.

1. `POST /api/register` (user A) → 200/201 con token
2. mismo username otra vez → 409
3. `POST /api/login` A → 200
4. `PUT /api/progress` A con `{"log":[{"type":"ue"}]}` → 200
5. `GET /api/progress` A → devuelve lo escrito
6. registrar B, `GET /api/progress` B → **no** ve nada de A (aislamiento)
7. A con token inválido → 401
8. token vencido (forzar `expires` en el archivo) → 401 `session expired`
9. `PUT /api/progress` con 2.1 MB → 413
10. `POST /api/ai/writing` sin key y con cuota 0 (`B2_AI_DAILY_PER_USER=0`) → 429
11. con `B2_AI_DAILY_PER_USER=1`: primer request consume, segundo → 429
12. con key propia del usuario → 200 aunque la cuota del servidor esté agotada (mockear el upstream)
13. 11 logins fallidos al mismo username → 429 en el 11º
14. `DELETE /api/account` con contraseña mal → 401
15. `DELETE /api/account` con contraseña bien → 200 y `data/users/<uid>/` ya no existe
16. `GET /api/export` → `application/json` con el progreso
17. permisos: `data/users/<uid>` es `0700` y `progress.json` `0600`
18. `errores_js` vacío en la UI con sesión iniciada

## Prohibido

- Dependencias nuevas (nada de Flask, bcrypt, jwt).
- Guardar contraseñas en claro, loguear tokens o keys.
- Romper `test_sync.py`, `test_demo.py`, `test_register.py`, `test_ai.py`.
- Tocar racha, plan, diagnóstico, corrector (sólo envolver con cuota).
- `pkill`, `rm -rf`, reiniciar servicios, tocar Docker/systemd/Coolify.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
cd tests && uv run --with playwright python test_multiuser.py 2>&1 | tail -22
cd tests && uv run --with playwright python test_sync.py 2>&1 | tail -4
cd tests && uv run --with playwright python test_demo.py 2>&1 | tail -4
cd tests && uv run --with playwright python test_ai.py 2>&1 | tail -4
```

## Commit

```
feat(auth): real multi-user instance with rate limits, quotas and account control
```

Respondé al final **sólo** con: archivos tocados, salida literal de los comandos, hash.
