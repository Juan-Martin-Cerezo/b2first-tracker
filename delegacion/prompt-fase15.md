# PROMPT — Fase 15: telemetría de producto + política de privacidad

Sos ingeniero senior full-stack. Repo `/home/b2first-tracker`. **CODIFICAR.** Inglés.

## Objetivo del usuario

> "Agregues todo un seguimiento de las cosas que hace el usuario para poder ver posibles
> errores y recopilar cierta info. Agrega política de privacidad."

Quiere saber **qué hace la gente en la app y qué se rompe**, sin convertir esto en un spyware.
La regla que gobierna toda la fase: **se registran eventos, nunca contenido**. Nada de texto de
respuestas, nada de writings, nada de contraseñas, nada de tokens.

## A — Cliente: `track(event, props)` en `index.html`

- Buffer en memoria, flush cada **10 s** o al llegar a **20 eventos**, con `navigator.sendBeacon`
  (fallback `fetch(..., {keepalive:true})`) a `POST /api/events`.
- **Lista blanca de eventos** (cualquier otro nombre se descarta en el cliente):
  `app_open`, `view_change`, `onboarding_step`, `onboarding_done`, `onboarding_skip`,
  `quicklog_open`, `quicklog_save`, `session_save`, `diag_start`, `diag_finish`,
  `plan_generate`, `ai_request`, `ai_success`, `ai_error`, `ai_blocked`, `theme_toggle`,
  `export_data`, `delete_account`, `login`, `register`, `js_error`, `fetch_error`, `slow_view`.
- Props permitidas (escalares, ≤64 chars): `view`, `part`, `kind`, `ms`, `count`, `ok`, `code`,
  `step`, `theme`, `ver`. **Prohibido**: cualquier texto libre, email, nombre, token, contenido.
- `sid`: id de sesión aleatorio por pestaña (`crypto.randomUUID()`), no persistente entre pestañas.
- Captura de errores: `window.onerror` y `unhandledrejection` → `js_error` con
  `{message_trunc:120, stack_hash, view}`. **Sin** stack completo ni variables.
- `fetch_error`: status + endpoint (sin query string).
- `slow_view`: si `refreshAll()` tarda más de 800 ms.
- Si `navigator.doNotTrack === "1"` → **no manda nada** (la app sigue igual). Respetarlo es parte
  de la política de privacidad.

## B — Servidor: `POST /api/events`

- Acepta `{sid, events:[{n, t, p}]}`, máx **50 eventos** y **32 KB** → si excede, `413`.
- Valida contra la misma lista blanca y el mismo tipo de props; descarta lo que no cumpla
  (nunca 500 por un evento raro).
- Guarda JSONL append-only en `data/events/YYYY-MM-DD.jsonl`:
  `{"ts":..., "sid":..., "uid":<id o null>, "n":"...", "p":{...}, "ip_hash":"<sha256(ip+salt)[:16]>"}`
  — el salt vive en `data/.events_salt` (`0600`, generado solo). **La IP nunca se guarda en claro.**
- Retención **7 días**: al escribir, si hay archivos de más de 7 días, se borran.
- Sin auth obligatoria (los eventos de `app_open` de un visitante sirven), pero si hay token se
  asocia `uid`; si el token es inválido se ignora y se guarda `uid:null` (nunca 401 acá).
- Rate limit propio: 60 batches / hora / IP → `429`.

## C — `GET /api/metrics` (sólo `owner`, con token)

Devuelve, para las últimas 24 h y 7 días:
`{"events":{n:count}, "errors":[{n, count, last_message_trunc}], "views":{view:count},
  "ai":{"requests":N,"success":N,"errors":N,"blocked":N}, "users_active":N, "p50_view_ms":N}`
Sin datos personales: sólo agregados y el `message_trunc` de los errores (nunca stacks).

En la UI, en **Account**, sección `Diagnostics` (visible sólo si el usuario es `owner`):
tabla de eventos, top errores con su mensaje, y el contador de IA.

## D — Política de privacidad

- Página `GET /privacy` servida por el servidor (HTML propio, mismo estilo que la app, dark mode,
  en inglés), linkeada desde el footer de la app y desde el formulario de registro:
  *"By creating an account you agree to the Privacy Policy."*
- Contenido real y verificable, no plantilla genérica. Secciones:
  1. **What we store** — cuenta (nombre, hash de contraseña con salt), progreso de estudio, tokens
     de sesión hasheados, eventos de uso agregados, audit log de accesos.
  2. **What we do not store** — no emails, no real names, no payment data, no third-party
     analytics, no advertising, no cookies de tracking.
  3. **Why** — para que la app funcione y para detectar errores.
  4. **Retention** — eventos 7 días · audit log hasta 5 MB · progreso hasta que borres la cuenta
     · backups 14 días (local) + semanal.
  5. **Your rights** — exportar (`GET /api/export`), borrar cuenta (`DELETE /api/account`),
     y que el borrado elimina los archivos del servidor.
  6. **AI** — qué se manda (el texto que elegís corregir) a qué proveedor, y que no se guarda en
     el servidor más allá del request.
  7. **Do Not Track** respetado.
  8. **Contact** — el email del dueño (placeholder explícito `TODO_OWNER_EMAIL` que el README
     documenta cómo completar; **no inventes un email**).
  9. **Ley aplicable** — mencionar Ley 25.326 (Argentina) sin afirmar cumplimiento certificado.
- `docs/PRIVACY.md` con el mismo texto en markdown, y el README linkeando a `/privacy`.

## E — Tests

`tests/test_telemetry.py` (≥12 asserts, server propio con `DATA_DIR` temporal):
1. batch válido de 5 eventos → 200 y aparecen 5 líneas en el JSONL del día
2. evento con nombre fuera de la lista blanca → se descarta, no aparece en el archivo
3. prop con texto de 500 chars → se trunca o se descarta, y **no** aparece completa
4. mandar `{"password":"x"}` en un evento → ese campo **no** se guarda
5. archivo JSONL no contiene la IP en claro (buscar `127.0.0.1` en el contenido → ausente)
6. batch de 51 eventos → 413
7. batch de 40 KB → 413
8. 61 batches en una hora → 429
9. `GET /api/metrics` sin token → 401; con token de usuario común → 403; con `owner` → 200 y
   las claves `events/errors/ai/users_active`
10. retención: crear un archivo de hace 8 días en `data/events/` y verificar que se borra
11. `GET /privacy` → 200, `text/html`, contiene "Privacy Policy" y "Ley 25.326"
12. la app incluye el link a `/privacy` en el footer (Playwright) y `errores_js` vacío
13. con `navigator.doNotTrack = "1"` (Playwright `add_init_script`) → **no** se manda ningún
    request a `/api/events`

## Prohibido

Dependencias, servicios externos de analytics, cookies de tracking, tocar auth/plan/corrector.
Inventar un email de contacto. Romper las suites existentes.

## Verificación (pegá salida literal)

```bash
cd /home/b2first-tracker
python3 -c "import re;open('/tmp/a.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/a.js
cd tests && uv run --with playwright python test_telemetry.py 2>&1 | tail -20
cd tests && python3 test_hardening.py 2>&1 | tail -2
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -3
curl -s -o /dev/null -w "privacy: %{http_code}\n" http://127.0.0.1:8088/privacy
```

Commit: `feat(telemetry): privacy-first product events, diagnostics view and privacy policy`
