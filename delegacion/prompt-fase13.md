# PROMPT — Fase 13: documentación de seguridad + auditoría externa reproducible

Sos ingeniero senior + technical writer. Repo `/home/juan/b2first-tracker`. **CODIFICAR.** Inglés.

## A — `SECURITY.md` (nuevo, en la raíz)

Estructura obligatoria:

1. **Scope** — qué protege el sistema: progreso de estudio por usuario, credenciales, la key del
   proveedor de IA. Qué NO protege: no hay datos de pago, no hay PII más allá del nombre elegido.
2. **Threat model** — tabla `Activo | Amenaza | Control | Dónde está en el código`. Mínimo 8 filas:
   robo de credenciales, enumeración de usuarios, fuerza bruta, IDOR entre usuarios, path traversal,
   abuso de la key de IA, DoS por payload, XSS/CSRF.
3. **Controls implemented** — tabla con el checklist del usuario, marcando `Implemented`,
   `N/A (no database)` o `Partial` + razón:
   validación de entrada · SQL injection (N/A) · hashing de contraseñas · secretos fuera del repo ·
   auth server-side · rate limit login/reset · timeouts externos · reintentos sólo transitorios ·
   idempotencia de pagos (N/A) · transacciones (equivalente: locks + `os.replace`) · índices (N/A) ·
   N+1 (N/A) · pool de conexiones (N/A) · migraciones versionadas · no borrar columnas en el mismo
   deploy (N/A) · logs con request id · health check · 429 no 500 · backups + restore probado ·
   CORS cerrado · un usuario no lee el id del otro.
4. **Backups and restore** — cómo se generan, retención 14, la verificación con parseo de JSON en
   cada corrida, y el comando exacto para restaurar paso a paso (probado).
5. **Reporting a vulnerability** — contacto y qué esperar.

## B — `tools/audit.sh` (ejecutable, sin dependencias)

Audita la instancia pública y **falla con exit 1** si algo no cumple:

- TLS válido y HTTP/2 en `https://vps-server.tail40095b.ts.net`
- headers presentes: `x-content-type-options`, `x-frame-options`, `referrer-policy`,
  `content-security-policy`, `x-request-id`
- **ausencia** de `access-control-allow-origin`
- `GET /api/progress?download=1` sin token → **401**
- `GET /api/progress?user=../../etc/passwd` → **400**
- `GET /api/health` → 200 con `"ok":true`
- `OPTIONS /api/progress` no devuelve headers CORS permisivos
- respuesta de `/` sin `Server:` con versión y sin `X-Powered-By`

Imprimí una tabla `CHECK | RESULT | DETAIL` y al final `PASS`/`FAIL`. Sin curl verbose.

## C — README

Agregá después de `## Tests` una sección corta `## Security` que resuma: cuentas aisladas,
límites, cuotas, tokens hasheados en reposo, audit log, backups verificados, y link a `SECURITY.md`.
Y en la tabla de features, la fila `Recent activity` si la fase 12 la agregó.

## D — `docs/VIDEO-SCRIPT.md`

Revisalo y actualizá el guion para que refleje la app de hoy: intake de 6 pasos, plan que cita tus
respuestas, corrección de Writing con las 4 bandas, y el hecho de que es multiusuario (no demo).
Mantené 6 tomas, 90–110 s, con `Qué se ve` / `Qué se dice` por toma.

## Prohibido

Tocar código de la app (`server.py`, `index.html`, `store.py`). Deploy, systemd, Docker.
Inventar resultados: el audit se corre de verdad y se pega la salida.

## Verificación (pegá salida literal)

```bash
cd /home/juan/b2first-tracker
bash tools/audit.sh; echo "AUDIT_EXIT=$?"
ls -l SECURITY.md tools/audit.sh
```

Commit: `docs: security model, reproducible external audit, refreshed video script`
