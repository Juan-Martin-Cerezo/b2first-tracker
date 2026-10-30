# PROMPT — Fase 12: blindaje ronda 2 (defensa en profundidad)

Sos ingeniero senior de seguridad. Repo `/home/juan/b2first-tracker`. **CODIFICAR.** Inglés.

El repo ya tiene: ids sanitizados, locks, headers, request id, `/api/health`, migración v1→v2,
reset por CLI, rate limits, cuotas. **No rehagas eso.** Esta ronda cierra los huecos que quedan.

## A — Fuerza bruta y comparación segura

- Contador de fallos por **username** además de por IP: tras 5 fallos, ese username queda bloqueado
  15 min (`423`→ usá **429** con `retry_after`) incluso si cambia la IP. Contador exitoso resetea.
- Comparación de hash **siempre** con `hmac.compare_digest` (tiempo constante). Verificá que el
  camino de "usuario inexistente" tarde lo mismo que el de "password incorrecta" (hash dummy).
- Delay progresivo: 0 / 0.2 / 0.5 / 1 s a partir del 3º fallo del mismo username (con `time.sleep`,
  máximo 1 s, nunca bloqueando el lock global).

## B — Tokens en reposo

- `data/tokens.json` guarda **sha256(token)**, no el token. `_auth()` hashea el header y busca.
  Migración transparente: si encuentra un token plano viejo, lo hashea al primer uso exitoso.
- Cada token guarda `issued`, `last_seen`, `ua_hash` (sha256 del User-Agent). Si cambia el UA de
  forma brusca, no bloquees: logueá `ua_changed` en el audit log.
- Rotación: al cambiar contraseña, se invalida todo salvo el token actual (ya existe, verificá).

## C — Validación de payload del progreso (schema)

`PUT /api/progress` hoy acepta cualquier JSON bajo 2 MB. Agregá `_validate_progress(data)`:

- debe ser `dict`; claves desconocidas se **conservan** (no romper usuarios futuros)
- `log` y `errs`: listas, máx **5000** items cada una; cada item `dict`
- strings: máx **500** chars (excepto `note`/`text` → 4000)
- `settings`, `profile`: `dict` o `null`; profundidad máxima 6 (`_depth()`)
- números finitos, sin `NaN`/`Infinity`
- si falla → `422 {"error":"invalid progress","field":"log[12].min"}` (campo exacto, sin volcar el body)

## D — Límite global por IP

Además de los límites por endpoint: **300 requests/min por IP** en todo `/api/*` → `429`.
Excluí `/api/health`. Con `X-Forwarded-For` sólo si el peer es loopback/LAN (ya implementado).

## E — Audit log de eventos de auth

`data/audit.log` (append, JSON por línea, `0600`):
`{"ts":..., "rid":..., "event":"login_ok|login_fail|register|password_change|account_delete|quota_hit|ua_changed", "user":"...", "ip":"..."}`

- **Nunca** tokens, passwords ni hashes. Rotación: si supera 5 MB, se renombra a `audit.log.1`.
- Endpoint `GET /api/audit?limit=50` **sólo para el usuario `owner`** (auth requerida): devuelve
  los últimos eventos **del propio usuario** (nunca de otros, salvo agregados sin datos personales).
- En la UI, en Account: sección `Recent activity` que muestra esos eventos en una lista.

## F — Fortaleza de contraseña

Rechazar en register y password change (`400` con mensaje claro): menos de 8 caracteres, o presente
en una lista corta embebida de ~200 passwords comunes (`password123`, `12345678`, `qwertyui`,
`b2first`, el propio username). **Sin dependencias ni descargas**: lista literal en el código.

## G — Tests `tests/test_security2.py` (≥14 asserts)

1. 5 fallos del mismo username desde **3 IPs distintas** → el 6º intento correcto da 429
2. username inexistente y password incorrecta tardan dentro de 2x entre sí (medido, tolerancia amplia)
3. `tokens.json` **no** contiene el token en claro (buscar el string del header en el archivo)
4. token plano legado migra a hash y sigue funcionando
5. `PUT` con `log` de 5001 items → 422
6. `PUT` con string de 600 chars en un campo normal → 422
7. `PUT` con `NaN` → 422 (o rechazo del parser), nunca 500
8. `PUT` con profundidad 8 → 422
9. `PUT` con clave desconocida `foo` → 200 y la clave se conserva al leer
10. 301 requests a `/api/config` en un minuto desde la misma IP → 429 en la última
11. `/api/health` no cuenta para el límite global (sigue 200)
12. `GET /api/audit` sin token → 401; con token de usuario común → 200 pero **sin** eventos de otro usuario
13. tras `password_change` aparece el evento en el audit log
14. password `password123` → 400; `correct-horse-9` → 200

## Prohibido

Dependencias, tocar plan/diagnóstico/corrector, deploy, systemd, Docker. Romper las suites existentes.

## Verificación (pegá salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/a.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/a.js
cd tests && python3 test_security2.py 2>&1 | tail -20
cd tests && python3 test_hardening.py 2>&1 | tail -3
cd tests && python3 test_legacy_guard.py 2>&1 | tail -2
cd tests && uv run --with playwright python test_multiuser.py 2>&1 | tail -3
```

Commit: `security: brute-force lockout, hashed tokens, payload schema, audit log`
