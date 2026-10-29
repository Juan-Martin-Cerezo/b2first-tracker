# PROMPT — Fase 0.2 + 0.3: seam de almacenamiento + hash pbkdf2

Sos un ingeniero senior. Trabajás en el repo `/home/juan/b2first-tracker` (cwd ya
correcto). Español rioplatense en comentarios y mensajes. **Este turno es para CODIFICAR,
no para narrar.**

## Contexto medido del repo (no lo re-investigues)

- `server.py` = 671 líneas, Python **solo stdlib**, `ThreadingHTTPServer`.
- Accesos a datos dispersos: `data/users.json`, `data/users/<uid>/progress.json`,
  `data/users/<uid>/backups/`, `data/tokens.json`. Constante `DATA_DIR`, `TOKENS_FILE`,
  `BK_KEEP` (20 backups) ya existen.
- Endpoints vivos: `/`, `/libros`, `/files/`, `/assets/`, `/libros.json`,
  `/api/users`, `/api/register`, `/api/login`, `/api/logout`, `/api/me`, `/api/progress`.
- `hash_password(salt, password)` = SHA-256 rápido. Registro: `salt = secrets.token_hex(8)`,
  password mínimo **4** caracteres (`if len(password) < 4: return None, "contraseña muy corta (mín 4)"`).
- `users.json` tiene registros viejos SIN campo `algo` (ej. `owner`).
- Servicio systemd `b2first` corriendo en 8088. Tests en `tests/` con Playwright.

## Tarea A — crear `store.py` (seam de almacenamiento)

Archivo nuevo `store.py` con **exactamente** estas funciones públicas y ninguna otra:

```python
get_user(uid) -> dict | None
create_user(uid, record) -> None
list_users() -> dict                 # {uid: record}
get_progress(uid) -> dict | None
put_progress(uid, data) -> None      # persiste + rota backups (BK_KEEP=20)
backup(uid, label=None) -> str       # devuelve el path del backup creado
```

Reglas duras:

1. Mismo formato en disco que hoy. **Cero migración de datos, cero cambio de schema.**
2. `store.py` NO importa `http.server`, NO conoce tokens, NO hace HTTP. Sólo filesystem.
3. `DATA_DIR` se recibe como parámetro del módulo (`set_data_dir(path)`) **o** se lee de
   una única función `_data_dir()` que respeta el atributo `server.DATA_DIR` si el server
   lo redefine en tests. Los tests existentes (`test_sync.py`, `test_graf.py`) importan
   `server.py` y le cambian `DATA_DIR`/`PORT` ANTES de levantar — **eso tiene que seguir
   funcionando**. Solución recomendada: `store.py` expone `DATA_DIR` como variable de
   módulo y `server.py` la setea al arrancar (`store.DATA_DIR = DATA_DIR`), más un
   `set_data_dir()` por si el test lo cambia después.
4. La rotación de backups (nombre `progress-YYYYMMDD-HHMMSS.json`, copiar el archivo
   anterior, conservar los últimos 20, y **el primer PUT no crea backup**) se mueve a
   `put_progress` sin cambiar el comportamiento observable.

Después refactorizá `server.py` para que **todos** los accesos a esos archivos pasen por
`store.*`. Los endpoints, sus respuestas HTTP y sus status codes **no cambian ni un byte**.

## Tarea B — pbkdf2 + migración transparente

1. `hash_password(salt, password)` → `hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()`.
2. El registro nuevo guarda `"algo": "pbkdf2"` en el record del usuario.
3. `login_user`: si el record **no** tiene `algo` → verificar contra el hash SHA-256
   legacy; si coincide, recalcular con pbkdf2 y **guardar el record migrado** (agregando
   `algo: "pbkdf2"`). Si tiene `algo == "pbkdf2"` → comparar directo.
4. Password mínimo: 4 → **8** en `register_user` (mensaje: `"contraseña muy corta (mín 8)"`).
   No tocar la validación de login (los usuarios viejos con password corta deben poder entrar).

## Prohibido

- Agregar cualquier dependencia (nada de pip, ni imports de terceros).
- Tocar `data/` a mano, borrar backups, o commitear `data/`.
- Cambiar nombres de endpoints, paths, ni formatos de respuesta.
- Reescribir `index.html`.
- `pkill`, `rm -rf`, ni reiniciar servicios del sistema.

## Verificación obligatoria antes de terminar (corré los 4 y pegá el resultado)

```bash
cd /home/juan/b2first-tracker
python3 -c "import ast,sys;[ast.parse(open(f).read()) for f in ('server.py','store.py')];print('AST OK')"
python3 -c "import server,store;print('IMPORT OK', store.hash_password if hasattr(store,'hash_password') else 'hash en server')" || true
curl -s -o /dev/null -w 'GET / -> %{http_code}\n' http://127.0.0.1:8088/
cd tests && uv run --with playwright python test_sync.py 2>&1 | tail -5
```

`test_sync.py` y `test_personalization.py` tienen que pasar. Si algo falla, arreglalo en
este mismo turno.

## Commit

Un solo commit convencional, sin tocar archivos ajenos:

```
refactor(store): seam de almacenamiento JSON + hash pbkdf2 con migración
```

Al final respondé **sólo** con: qué archivos tocaste, el resultado literal de los 4
comandos de verificación, y el hash del commit. Nada más.
