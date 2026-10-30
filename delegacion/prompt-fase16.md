# PROMPT — Fase 16: endurecer el servidor contra ataques de red

Sos ingeniero senior de infraestructura/seguridad. Repo `/home/b2first-tracker`. **CODIFICAR.** Inglés.

Contexto: `server.py` es `ThreadingHTTPServer` de stdlib, expuesto a internet por un proxy TLS
(Tailscale Funnel → `127.0.0.1:8088`). Un atacante puede mandar basura a mano; hoy el server no
tiene límites de conexión, ni timeout de socket, ni control de headers, y escucha en `0.0.0.0`.

## A — Superficie de red

- `H.timeout = 15` (segundos) para cortar clientes lentos (**slowloris**).
- Semáforo global de **200 conexiones simultáneas** (`threading.BoundedSemaphore`): si se agota,
  responder `503 {"error":"busy","retry_after":5}` + `Retry-After: 5` y cerrar. Nunca dejar el
  hilo colgado.
- Bind configurable: `B2_HOST` (default **`127.0.0.1`**). Documentar que LAN requiere
  `B2_HOST=0.0.0.0` y que el firewall de nftables sigue siendo la barrera real.
- URI > **2048** chars → `414`. Más de **60 headers** → `431`. `Content-Length` > **3 MB** →
  `413` **antes** de leer el cuerpo.

## B — Validación de la request

- Métodos permitidos: `GET, HEAD, POST, PUT, DELETE, OPTIONS`. Cualquier otro → `405` +
  `Allow: GET, HEAD, POST, PUT, DELETE, OPTIONS`. `TRACE` explícitamente `405`.
- Path: rechazar (400) si contiene byte nulo, `..` en cualquier forma (crudo o percent-encoded,
  incluyendo `%2e%2e`, `%2E%2E`, doble encoding), backslash, o segmentos vacíos `//`.
- Denegar archivos ocultos (`.env`, `.git`, `.events_salt`) con `403` sin revelar existencia.
- Normalizar con `unquote` **una sola vez** y comparar contra rutas conocidas; el 404 por defecto
  no debe listar directorios ni rutas candidatas.
- Host header: si `B2_ALLOWED_HOSTS` está seteado (lista separada por comas), rechazar `421`
  los Host desconocidos. Por defecto vacío = no chequea (documentado).

## C — Headers de respuesta adicionales

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
X-Permitted-Cross-Domain-Policies: none
```
Mantener los que ya existen (CSP, nosniff, DENY, referrer, permissions). En `/index.html` y `/`
agregar `Cache-Control: no-cache` (revalidar) y a los estáticos de `material/`
`Cache-Control: public, max-age=3600`.

## D — Errores que no filtran

- Ninguna respuesta incluye stack traces, rutas absolutas del filesystem, ni versión de Python.
- `500` siempre `{"error":"internal","rid":"..."}` (ya existe: verificá que se cumpla también en
  los caminos nuevos de esta fase).
- Los `400/405/413/414/431` no escriben nada en `data/`.

## E — `tests/test_server_hardening.py` (≥14 asserts, server propio temporal)

1. URI de 3000 chars → `414`
2. 70 headers → `431`
3. `Content-Length: 5000000` en `POST /api/events` → `413` sin leer cuerpo
4. `TRACE /` → `405` con header `Allow`
5. método inventado `FROB /` → `405`
6. `/../../etc/passwd` → `400`
7. `/%2e%2e%2f%2e%2e%2fetc%2fpasswd` → `400`
8. `/..%2f..%2fetc/passwd` (doble encoding) → `400` o `404`, nunca `200`
9. `/.env`, `/.git/config`, `/.events_salt` → `403`/`404` sin contenido del archivo
10. `/material/%00.txt` → `400`
11. `GET /` trae `Strict-Transport-Security`, `Cross-Origin-Opener-Policy`,
    `Cross-Origin-Resource-Policy`
12. `GET /` **no** trae `Server` con versión ni `X-Powered-By`
13. respuesta de error 500 (monkeypatch) no contiene `Traceback` ni `/home/`
14. ninguna request inválida de las anteriores creó archivos nuevos en `DATA_DIR`
    (comparar el listado antes/después)
15. `B2_HOST` default es `127.0.0.1` (leer el módulo y comprobar la constante)

## Prohibido

Dependencias, romper auth/telemetría/plan/corrector, deploy, systemd, Docker, nftables.
Bajar el límite de conexiones por debajo de 50.

## Verificación (pegá salida literal)

```bash
cd /home/b2first-tracker
cd tests && python3 test_server_hardening.py 2>&1 | tail -20
cd tests && python3 test_hardening.py 2>&1 | tail -2
cd tests && python3 test_security2.py 2>&1 | tail -2
cd tests && python3 test_legacy_guard.py 2>&1 | tail -2
```

Commit: `security(server): connection cap, socket timeout, request limits, traversal and hidden-file guards`
