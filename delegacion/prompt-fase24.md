# PROMPT — Fase 24: seguridad de la aplicación a nivel certificable

Sos auditor senior de seguridad de aplicaciones (OWASP ASVS / Mozilla Observatory mentalidad).
Repo `/home/juan/b2first-tracker`. **CODIFICAR.** Inglés en código/commits/docs.

**Objetivo real:** que la app sea defendible frente a una auditoría externa, y que el resultado
sea **verificable por máquina**, no una promesa en un README. Nada de "certificado": una tabla
ASVS L2 con PASS/FAIL por ítem y un `tools/audit.sh` que lo comprueba.

## Regla de honestidad

Si un control **no se puede** implementar sin romper la arquitectura (ej.: CSP sin
`unsafe-inline` requiere reescribir 3.600 líneas de `onclick=`), se documenta como riesgo
residual en `SECURITY.md` con el plan de migración y el impacto. **No se marca PASS.**

## A — Headers y transporte

- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`.
- CSP: mantené el `'unsafe-inline'` que hoy es necesario, pero **eliminá `'unsafe-eval'` si
  existe** y agregá `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`,
  `form-action 'self'`. Documentá en `SECURITY.md` por qué `unsafe-inline` queda (con la lista de
  handlers inline a migrar y el orden de magnitud).
- `COOP: same-origin`, `CORP: same-origin`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy` mínima (microphone=(self) solo donde se usa).
- `X-Request-Id` ya existe: agregale un `Server-Timing` con el tiempo interno de la request.

## B — Sesiones y credenciales

- PBKDF2 200k → **600.000** iteraciones (OWASP 2023), con **migración transparente**: al loguearse
  un usuario con hash viejo, se re-hashea y se guarda; nadie queda afuera.
- TTL absoluto de sesión: 30 días de sliding **más** un tope absoluto de 90 días
  (`absolute_exp`) que no se extiende nunca.
- Cambio de contraseña → revoca **todas** las sesiones (ya existe: verificá que incluya la
  actual y que el cliente no quede con un token muerto sin avisar).
- Política de contraseña: mínimo 10 caracteres, rechazo de las **200** más comunes (lista embebida
  en `store.py`, sin dependencias), y aviso de fortaleza en el registro. No inventes una lista de
  10.000: 200 explícitas y el resto por longitud.
- Bloqueo por usuario ya existe: agregá **backoff exponencial** tras el 3.er fallo (5s, 15s, 60s)
  antes del lockout de 15 min.

## C — Integridad y trazabilidad

- **Audit log encadenado**: cada línea agrega `prev` = sha256 de la línea anterior → un log
  alterado se detecta. Escribí `tools/verify_audit.py` que valide la cadena y salga non-zero si
  está rota. El primer registro usa `prev:"0"*64`.
- Log de eventos de seguridad nuevos: `ai_blocked` (existe), `rate_limited_by_user`,
  `pa_rejected`, `token_minted`, `session_revoked`. Todos con `rid`, sin datos personales, sin
  contenido del usuario.
- Nunca loguear tokens, keys, ni el texto del alumno (ya se cumple: agregá el test que lo prueba).

## D — Superficie

- `/.well-known/security.txt` con contacto y política de divulgación (RFC 9116), y el link desde
  `SECURITY.md`. Si no hay mail verificado, usá el placeholder documentado, no inventes uno.
- Verificá que estos paths devuelvan 403/404 **sin** distinguir existencia: `.env`, `.git/config`,
  `data/users.json`, `data/tokens.json`, `server.py`, `store.py`, `*.bak`.
- Todo error 500 debe devolver `{"error":"internal"}` + `rid`, **nunca** un traceback ni una ruta
  del filesystem. Test que fuerza una excepción interna y verifica la respuesta.
- Límite de body por ruta: 3 MB global sigue, pero `/api/speaking/pa` 2 MB y `/api/progress` 2 MB
  deben rechazar **antes de leer el body** (Content-Length), no después.

## E — `tools/audit.sh` de 14 a 25+ checks

Agregá (contra la URL pública, sin credenciales):
HSTS incluye preload · CSP tiene `object-src 'none'` y `base-uri 'none'` · COOP · CORP ·
`security.txt` 200 · cada path sensible 403/404 · `Server` sin versión · `X-Request-Id` presente ·
`404` no filtra stack · `TRACE` 405 · método raro 405 · `..` URL-encoded 400 · body > 3 MB 413 ·
`permissions-policy` presente · respuesta `/api/health` sin datos sensibles.
**Cada check imprime PASS/FAIL y una línea de evidencia.** Exit non-zero si alguno falla.

## F — Documento verificable

`docs/SECURITY-CHECKLIST.md`: tabla con columnas
`control | ASVS ref | estado (PASS/FAIL/N-A) | dónde se implementa | cómo se prueba`.
Cubrí al menos los capítulos de ASVS L2: autenticación, sesión, control de acceso,
validación de entrada, criptografía, manejo de errores, logging, headers/comunicaciones,
archivos/recursos. **N/A es una respuesta válida y honesta** (ej.: "no hay uploads de archivos").

## G — Verificación y cierre

- `tests/test_security3.py` (nuevo, ≥ 16 asserts): re-hash a 600k al loguearse, TTL absoluto,
  backoff exponencial, audit chain rota detectada, `security.txt`, paths sensibles, 500 genérico
  con rid, Content-Length pre-check, revocación total al cambiar contraseña.
- `bash tools/audit.sh` → **25/25 PASS** (o el número real, escrito en el commit).
- Suites existentes verdes: `test_hardening`, `test_security2`, `test_server_hardening`,
  `test_legacy_guard`, `test_final`.
- Dos commits: `feat(security): ASVS L2 app hardening...` y `docs(security): verifiable checklist`.
