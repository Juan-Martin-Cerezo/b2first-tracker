# PROMPT — Fase 8: cuenta real (no demo) con registro cerrado

Sos un ingeniero senior. Repo `/home/juan/b2first-tracker` (cwd correcto). **Este turno es para
CODIFICAR.** Todo en inglés: código, comentarios, mensajes y commits.

## Por qué

El usuario necesita **usar la app de verdad**, no el modo demo: sesiones que persisten, login,
sincronización entre celular y PC. Pero la instancia va a quedar expuesta en internet, así que
el registro tiene que poder cerrarse: sólo su cuenta, nadie más se da de alta.

## Tarea A — `server.py`: flag de registro

Variable de entorno `B2_REGISTER` con valores `open` (default) y `closed`.

- Con `closed`, `POST /api/register` → **403** `{"error":"registration is closed"}`.
  `login`, `logout`, `me` y `/api/progress` siguen funcionando normal (es exactamente lo que
  falta hoy entre "demo" y "abierto a cualquiera").
- `GET /api/config` devuelve además `"register": "open"|"closed"` (mantené `demo` y `version`).
- Si `B2_DEMO=1`, `register` se reporta como `"closed"` igual (en demo no hay cuentas).

## Tarea B — Cambio de contraseña (necesario para una cuenta real)

- `POST /api/password` `{current, next}` con auth por Bearer token.
  Valida `current`, exige `next` ≥ 8 caracteres, re-hashea con el mismo `pbkdf2_hmac` y el mismo
  esquema `algo` que ya usa el login. Responde `200 {"ok":true}` o `400`/`401`.
- **Invalida los otros tokens** del usuario (deja sólo el actual): así una contraseña filtrada no
  mantiene sesiones abiertas.
- En la UI: dentro de la vista de cuenta/perfil, un formulario mínimo (3 inputs + botón) con
  estados `idle/loading/ok/error`.

## Tarea C — Frontend

- Si `config.register === "closed"`: ocultá el link/botón de "Create account" y mostrá en su
  lugar: *"Registration is closed. This instance is private."*
- El formulario de login no cambia. El badge de sync del footer sigue igual.
- Todo el texto nuevo en inglés.

## Tarea D — `tests/test_register.py`

Arrancá el server con `B2_REGISTER=closed`, `B2_DEMO=0`, `PORT` libre y `DATA_DIR` temporal
(patrón de `test_sync.py`: importar el módulo y setear globales antes de levantar).

Asserts (≥7):
1. `/api/config` → `register === "closed"`, `demo === false`
2. `POST /api/register` → **403**
3. crear un usuario **por API interna/archivo** (no por la ruta cerrada) y hacer `POST /api/login`
   → **200** con token
4. `GET /api/progress` con ese token → **200**
5. `PUT /api/progress` con ese token → **200** y el archivo en `DATA_DIR` cambia
6. `POST /api/password` con `current` incorrecto → **401**
7. `POST /api/password` con `next` de 5 chars → **400**
8. cambio exitoso → **200**, el login viejo falla (401) y el nuevo funciona (200), y el token
   anterior distinto del actual queda inválido
9. con `B2_REGISTER=open` (segundo arranque): `/api/config` → `"open"` y register acepta un alta válida

## Prohibido

- Tocar la lógica de IA, racha, diagnóstico, plan o la UI visual (fase 7 ya la dejó lista).
- Agregar dependencias. Guardar o loguear claves.
- Deployar ni tocar Docker/systemd/Coolify (eso lo hace el orquestador).
- `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
cd tests && uv run --with playwright python test_register.py 2>&1 | tail -14
cd tests && uv run --with playwright python test_sync.py 2>&1 | tail -4
cd tests && uv run --with playwright python test_demo.py 2>&1 | tail -4
```

## Commit

```
feat(auth): closable registration and password change for private instances
```

Respondé al final **sólo** con: archivos tocados, salida literal de los comandos, hash.
