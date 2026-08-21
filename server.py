#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 First study portal — sirve el tracker + material (PDF/audio) desde la Pi.

Acceso: http://100.112.213.66:8088 (Tailscale) o http://127.0.0.1:8088 (local).
Escanea ~/Descargas/b2-first dinámicamente: cualquier PDF/MP3/ZIP que
agregues a esa carpeta aparece solo en /libros (catálogo con buscador)
y en /libros.json (que consume la pestaña LIBROS del tracker).

Endpoints:
  GET /            → index.html (el tracker single-file)
  GET /libros      → página HTML con todo el material (visor + audios)
  GET /libros.json → JSON con el catálogo (para el tracker)
  GET /files/<rel> → sirve un archivo del material con soporte Range
                     (necesario para que el audio se pueda re-buscar)
  GET /api/progress?download=1 → descarga el progreso guardado (JSON)
  GET /api/progress → lista de backups (JSON) {file, size, date}
  PUT /api/progress → guarda el progreso (body JSON) y respalda el anterior
  GET /favicon.ico → 204 (no existe, no loguear 404)

Persistencia: el progreso vive en <repo>/data/progress.json. Cada PUT
respalda automáticamente la versión anterior en <repo>/data/backups/
(último gana + backups). Datos SOLO en esta Pi, sin auth (red privada).

Dependencias: SOLO stdlib (http.server, os, re, html, mimetypes).
Deploy: systemd unit b2first.service (Restart=always) en este dir.
"""
import os, re, html, mimetypes, json, shutil, time, hashlib, secrets
from urllib.parse import quote, unquote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ROOT      = os.path.expanduser("~/Descargas/b2-first")  # material (PDF/MP3/ZIP)
TRACKER   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
PORT      = int(os.environ.get("PORT", 8088))           # 8080 lo ocupa docker-proxy
EXTS      = {".pdf": "PDF", ".mp3": "AUDIO", ".zip": "ZIP"}
DATA_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROG_FILE = os.path.join(DATA_DIR, "progress.json")
BK_DIR    = os.path.join(DATA_DIR, "backups")
BK_KEEP   = 20                                          # backups a conservar
# Usuarios (sistema multi-cuenta)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
USERS_DIR  = os.path.join(DATA_DIR, "users")            # data/users/<id>/progress.json
TOKEN_TTL  = 7 * 24 * 3600                              # sesión válida 7 días
OWNER_PASSWORD = os.environ.get("B2_OWNER_PASSWORD", "b2first")  # pass del owner al migrar


# ---------------------------------------------------------------------------
# Catálogo de archivos
# ---------------------------------------------------------------------------
def scan():
    """Recorre ROOT y devuelve la lista de archivos {rel, name, ext, size, folder}.

    rel = ruta relativa (para /files/), folder = carpeta padre (para agrupar).
    """
    items = []
    for dirpath, _dirs, filenames in os.walk(ROOT):
        for fn in sorted(filenames):
            ext = os.path.splitext(fn)[1].lower()
            if ext in EXTS:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT)
                items.append({
                    "rel": rel,
                    "name": fn,
                    "ext": EXTS[ext],
                    "size": os.path.getsize(full),
                    "folder": os.path.dirname(rel) or "Material",
                })
    return items


def fmt_size(n):
    """Formatea bytes → '1.2 MB' legible."""
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.0f} TB"


def esc(s):
    """Escape HTML (evita inyección por nombres de archivo raros)."""
    return html.escape(str(s))


# ---------------------------------------------------------------------------
# Persistencia del progreso (data/progress.json + backups/ultimo-gato-gana)
# ---------------------------------------------------------------------------
def read_progress():
    """Devuelve el progreso guardado o {} si no existe / está corrupto."""
    try:
        with open(PROG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_progress(data):
    """Persiste el progreso (dict) de forma atómica + backup del anterior."""
    os.makedirs(BK_DIR, exist_ok=True)
    if os.path.exists(PROG_FILE):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        try:
            shutil.copy2(PROG_FILE, os.path.join(BK_DIR, f"progress-{stamp}.json"))
        except OSError:
            pass  # si el backup falla, seguimos con el guardado principal
    tmp = PROG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, PROG_FILE)  # atómico: nunca queda un archivo a medias
    # Podar backups viejos (conservar los BK_KEEP más recientes).
    try:
        bks = sorted(os.listdir(BK_DIR))
        for old in bks[:-BK_KEEP]:
            os.remove(os.path.join(BK_DIR, old))
    except OSError:
        pass


def list_backups():
    """Devuelve [{file, size, date}] con los backups, más reciente primero."""
    try:
        files = sorted(os.listdir(BK_DIR), reverse=True)
    except OSError:
        return []
    out = []
    for fn in files:
        full = os.path.join(BK_DIR, fn)
        try:
            st = os.stat(full)
        except OSError:
            continue
        out.append({
            "file": fn,
            "size": st.st_size,
            "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
        })
    return out


# ---------------------------------------------------------------------------
# Usuarios + sesiones (sistema multi-cuenta)
# ---------------------------------------------------------------------------
def _read_json(path, default):
    """Lee un JSON o devuelve el default si no existe / está corrupto."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    """Escribe un JSON de forma atómica (tmp + rename)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def load_users():
    """Devuelve {user_id: {id, name, salt, hash, color, created}}."""
    return _read_json(USERS_FILE, {})


def save_users(users):
    _write_json(USERS_FILE, users)


def load_tokens():
    """Devuelve {token: {user_id, exp}}."""
    return _read_json(TOKENS_FILE, {})


def save_tokens(tokens):
    _write_json(TOKENS_FILE, tokens)


def hash_password(salt, password):
    """sha256(salt + password). Salt de 16 bytes hex (32 chars)."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def new_token(user_id):
    """Crea un token de sesión válido por TOKEN_TTL y lo persiste."""
    tokens = load_tokens()
    # Podar expirados
    now = time.time()
    tokens = {t: v for t, v in tokens.items() if v.get("exp", 0) > now}
    tok = secrets.token_hex(24)
    tokens[tok] = {"user_id": user_id, "exp": now + TOKEN_TTL}
    save_tokens(tokens)
    return tok


def user_from_token(token):
    """Devuelve el user_id del token si es válido, o None."""
    if not token:
        return None
    tokens = load_tokens()
    v = tokens.get(token)
    if not v or v.get("exp", 0) < time.time():
        return None
    return v.get("user_id")


def revoke_token(token):
    tokens = load_tokens()
    if token in tokens:
        del tokens[token]
        save_tokens(tokens)


def public_user(u):
    """Usuario sin campos sensibles (sin salt/hash)."""
    return {"id": u["id"], "name": u["name"], "color": u.get("color", "#1b2b48"),
            "created": u.get("created", "")}


def user_prog_file(user_id):
    """Ruta del progress.json de un usuario."""
    return os.path.join(USERS_DIR, user_id, "progress.json")


def user_bk_dir(user_id):
    """Ruta del directorio de backups de un usuario."""
    return os.path.join(USERS_DIR, user_id, "backups")


def register_user(name, password, color=None):
    """Crea un usuario. Devuelve (user_id, error)."""
    users = load_users()
    name = name.strip()
    if not name:
        return None, "name vacío"
    if len(password) < 4:
        return None, "contraseña muy corta (mín 4)"
    # Normalizar nombre para id único (slug + sufijo si repetido)
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "user"
    uid = base
    n = 2
    while uid in users:
        uid = f"{base}-{n}"
        n += 1
    salt = secrets.token_hex(8)  # 16 chars
    users[uid] = {
        "id": uid, "name": name, "salt": salt,
        "hash": hash_password(salt, password),
        "color": color or "#1b2b48",
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    save_users(users)
    os.makedirs(user_bk_dir(uid), exist_ok=True)
    return uid, None


def login_user(name, password):
    """Valida credenciales. Devuelve (user_id, error)."""
    users = load_users()
    name = name.strip()
    for u in users.values():
        if u["name"].lower() == name.lower():
            if u["hash"] == hash_password(u["salt"], password):
                return u["id"], None
            return None, "contraseña incorrecta"
    return None, "usuario no encontrado"


def migrate_legacy():
    """Migra data/progress.json → data/users/owner/progress.json (una vez).

    Si ya existe users.json no hace nada. Crea el usuario 'owner' con la
    contraseña OWNER_PASSWORD y conserva el progreso actual.
    """
    if os.path.exists(USERS_FILE):
        return
    os.makedirs(USERS_DIR, exist_ok=True)
    uid = "owner"
    salt = secrets.token_hex(8)
    users = {
        uid: {"id": uid, "name": "Owner", "salt": salt,
              "hash": hash_password(salt, OWNER_PASSWORD),
              "color": "#1b2b48", "created": time.strftime("%Y-%m-%d %H:%M")}
    }
    save_users(users)
    os.makedirs(user_bk_dir(uid), exist_ok=True)
    if os.path.exists(PROG_FILE):
        shutil.move(PROG_FILE, user_prog_file(uid))
    elif not os.path.exists(user_prog_file(uid)):
        _write_json(user_prog_file(uid), {})
    # Mover backups viejos al usuario owner
    if os.path.isdir(BK_DIR):
        try:
            for fn in os.listdir(BK_DIR):
                src = os.path.join(BK_DIR, fn)
                if os.path.isfile(src):
                    shutil.move(src, os.path.join(user_bk_dir(uid), fn))
            os.rmdir(BK_DIR)
        except OSError:
            pass


def read_user_progress(user_id):
    """Devuelve el progreso de un usuario o {} si no existe."""
    return _read_json(user_prog_file(user_id), {})


def save_user_progress(user_id, data):
    """Persiste el progreso de un usuario de forma atómica + backup."""
    os.makedirs(user_bk_dir(user_id), exist_ok=True)
    pf = user_prog_file(user_id)
    if os.path.exists(pf):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        try:
            shutil.copy2(pf, os.path.join(user_bk_dir(user_id), f"progress-{stamp}.json"))
        except OSError:
            pass
    _write_json(pf, data)
    # Podar backups viejos
    try:
        bks = sorted(os.listdir(user_bk_dir(user_id)))
        for old in bks[:-BK_KEEP]:
            os.remove(os.path.join(user_bk_dir(user_id), old))
    except OSError:
        pass


def list_user_backups(user_id):
    """Devuelve [{file, size, date}] de los backups de un usuario."""
    try:
        files = sorted(os.listdir(user_bk_dir(user_id)), reverse=True)
    except OSError:
        return []
    out = []
    for fn in files:
        full = os.path.join(user_bk_dir(user_id), fn)
        try:
            st = os.stat(full)
        except OSError:
            continue
        out.append({"file": fn, "size": st.st_size,
                    "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
    return out


# ---------------------------------------------------------------------------
# Página /libros (material con visor + audios + buscador)
# ---------------------------------------------------------------------------
def portal():
    """Genera la página HTML del material agrupada por carpeta."""
    items = scan()
    # Agrupar por carpeta conservando el orden natural de las carpetas.
    groups = {}
    for it in items:
        groups.setdefault(it["folder"], []).append(it)
    order = ["Material", "sample1", "sample2", "for-schools-1", "for-schools-2"]
    def key(f):
        return order.index(f) if f in order else 99

    blocks = []
    for folder in sorted(groups, key=key):
        cards = ""
        for it in groups[folder]:
            href = "/files/" + quote(it["rel"])  # quote → espacios/acentos OK
            if it["ext"] == "AUDIO":
                cards += f'''<div class="card audio">
                  <div class="top"><span class="ico">🎧</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <audio controls preload="none" src="{href}"></audio>
                  <a class="dl" href="{href}" download>Descargar</a></div>'''
            elif it["ext"] == "PDF":
                cards += f'''<div class="card">
                  <div class="top"><span class="ico">📄</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <div class="acts"><a class="btn" href="{href}" target="_blank">Abrir PDF</a><a class="dl" href="{href}" download>Descargar</a></div></div>'''
            else:  # ZIP
                cards += f'''<div class="card">
                  <div class="top"><span class="ico">🗜️</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <a class="btn" href="{href}" download>Descargar ZIP</a></div>'''
        blocks.append(f'<h3 class="folder">{esc(folder)}</h3><div class="grid">{cards}</div>')

    total = sum(1 for _ in items)
    # Página completa con estilos dark (mismo look que el tracker) + buscador
    # en vivo que oculta tarjetas y carpetas vacías.
    return f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Material B2 First</title><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{{--bg:#0a0c12;--panel:#141824;--panel2:#1b2133;--line:#262d42;--line2:#323b56;--txt:#e8ecf8;--dim:#8b94ad;--acc:#6c8cff;--acc2:#8b6cff;--mon:#34d399}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:radial-gradient(900px 420px at 85% -8%,rgba(108,140,255,.10),transparent 60%),radial-gradient(700px 380px at -10% 18%,rgba(139,108,255,.08),transparent 55%),var(--bg);color:var(--txt);font:15px/1.5 'Inter',system-ui,sans-serif;padding:16px 16px 44px;min-height:100vh}}
h1{{font-size:20px;font-weight:800;margin-bottom:4px;letter-spacing:-.2px}}h1 a{{color:var(--txt);text-decoration:none}}
.sub{{color:var(--dim);font-size:13px;margin-bottom:16px}}
.back{{display:inline-block;margin-bottom:14px;color:var(--acc);text-decoration:none;font-size:13px;font-weight:600;background:var(--panel);border:1px solid var(--line);padding:7px 14px;border-radius:10px;transition:border-color .15s}}
.back:hover{{border-color:var(--acc)}}
.folder{{color:var(--acc);font-size:15px;font-weight:700;margin:20px 0 9px;text-transform:capitalize;letter-spacing:.2px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}
.card{{background:linear-gradient(180deg,rgba(255,255,255,.018),transparent 40%),var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:0 10px 30px -12px rgba(0,0,0,.55)}}
.card .top{{display:flex;gap:10px;align-items:flex-start}}
.card .ico{{width:34px;height:34px;flex:none;border-radius:9px;background:var(--panel2);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;font-size:16px}}
.card b{{font-size:13.5px;display:block;line-height:1.35;overflow-wrap:break-word;word-break:break-word}}
.card .meta{{font-size:11.5px;color:var(--dim);margin-top:2px}}
.acts{{display:flex;gap:8px;margin-top:11px;align-items:center}}
audio{{width:100%;margin-top:10px;height:34px;border-radius:8px}}
.btn{{background:linear-gradient(135deg,var(--acc),var(--acc2));color:#fff;border-radius:9px;padding:8px 13px;font-size:12.5px;font-weight:700;text-decoration:none;display:inline-block}}
.dl{{color:var(--acc);font-size:12px;font-weight:600;text-decoration:none;margin-left:auto}}
.dl:hover{{text-decoration:underline}}
#filtro{{width:100%;max-width:440px;background:var(--bg);border:1px solid var(--line2);border-radius:10px;color:var(--txt);padding:11px 13px;font-size:14px;font-family:'Inter',system-ui,sans-serif;margin-bottom:16px;transition:border-color .15s,box-shadow .15s}}
#filtro:focus{{outline:none;border-color:var(--acc);box-shadow:0 0 0 3px rgba(108,140,255,.14)}}
</style></head><body>
<a class="back" href="/">← Volver al Tracker</a>
<h1>📚 Material B2 First</h1>
<div class="sub">{total} archivos · los PDFs abren en el visor del navegador (PC y celular) · los audios se reproducen acá</div>
<input id="filtro" placeholder="🔍 Buscar material... (ej: listening, speaking, handbook)">
<div id="contenido">
{''.join(blocks)}
</div>
<script>
document.getElementById('filtro').addEventListener('input',function(){{
  var q=this.value.toLowerCase().trim();
  // Ocultar/mostrar tarjetas según el texto del filtro.
  document.querySelectorAll('#contenido .card').forEach(function(c){{
    c.style.display=(!q||c.textContent.toLowerCase().includes(q))?'':'none';
  }});
  // Ocultar las carpetas que quedaron sin tarjetas visibles.
  document.querySelectorAll('#contenido .folder').forEach(function(h){{
    var sib=[];
    var n=h.nextElementSibling;
    while(n&&n.classList&&!n.classList.contains('folder')){{sib.push(n);n=n.nextElementSibling;}}
    h.style.display=sib.some(function(c){{return c.style.display!=='none'}})||!q?'':'none';
  }});
}});
</script>
</body></html>'''


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    server_version = "B2FirstPortal/1.0"

    def log_message(self, fmt, *a):
        """Silencia el log por request (ruido en journald)."""
        pass

    def _send(self, code, body, ctype, extra=None):
        """Helper: respuesta con headers mínimos + Content-Length."""
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        """Router único (usado por GET y HEAD)."""
        path = unquote(self.path.split("?")[0])

        # Tracker (index.html)
        if path in ("/", "/index.html"):
            try:
                body = open(TRACKER, "rb").read()
                self._send(200, body, "text/html; charset=utf-8")
            except OSError:
                self._send(404, b"tracker no encontrado", "text/plain")
            return

        # Página de material
        if path == "/libros":
            self._send(200, portal().encode("utf-8"), "text/html; charset=utf-8")
            return

        # Archivos del material con anti-traversal + soporte Range (audio)
        if path.startswith("/files/"):
            rel = path[len("/files/"):]
            full = os.path.realpath(os.path.join(ROOT, rel))
            # Bloquea .. y links fuera de ROOT.
            if not full.startswith(os.path.realpath(ROOT)) or not os.path.isfile(full):
                self._send(404, b"no existe", "text/plain")
                return
            size = os.path.getsize(full)
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            # Range: el navegador pide chunks para el <audio> (seek/rebobinar).
            rng = self.headers.get("Range")
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng)
                if m:
                    start = int(m.group(1) or 0)
                    end = int(m.group(2) or size - 1)
                    end = min(end, size - 1)
                    with open(full, "rb") as f:
                        f.seek(start)
                        data = f.read(end - start + 1)
                    self._send(206, data, ctype, {
                        "Content-Range": f"bytes {start}-{end}/{size}",
                        "Accept-Ranges": "bytes",
                    })
                    return
            with open(full, "rb") as f:
                data = f.read()
            self._send(200, data, ctype, {"Accept-Ranges": "bytes"})
            return

        # Assets estáticos del tracker (favicon, manifest, apple-touch-icon)
        if path.startswith("/assets/"):
            rel = path[len("/assets/"):]
            root_assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
            full = os.path.realpath(os.path.join(root_assets, rel))
            if not full.startswith(os.path.realpath(root_assets)) or not os.path.isfile(full):
                self._send(404, b"no existe", "text/plain")
                return
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as f:
                data = f.read()
            self._send(200, data, ctype)
            return

        # JSON del catálogo (lo consume la pestaña LIBROS del tracker)
        if path == "/libros.json":
            data = [{"name": it["name"], "folder": it["folder"], "ext": it["ext"],
                     "rel": it["rel"], "size": it["size"], "href": "/files/" + quote(it["rel"])}
                    for it in scan()]
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        # ---- API de usuarios / auth ----
        if path == "/api/users":
            migrate_legacy()
            users = [public_user(u) for u in load_users().values()]
            body = json.dumps(users, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/api/register":
            migrate_legacy()
            if self.command != "POST":
                self._send(405, b"metodo no permitido", "text/plain"); return
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send(400, b"JSON invalido", "text/plain"); return
            uid, err = register_user(req.get("name", ""), req.get("password", ""), req.get("color"))
            if err:
                self._send(400, err.encode("utf-8"), "text/plain"); return
            tok = new_token(uid)
            users = load_users()
            body = json.dumps({"id": uid, "name": users[uid]["name"], "color": users[uid]["color"], "token": tok},
                              ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/api/login":
            migrate_legacy()
            if self.command != "POST":
                self._send(405, b"metodo no permitido", "text/plain"); return
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send(400, b"JSON invalido", "text/plain"); return
            uid, err = login_user(req.get("name", ""), req.get("password", ""))
            if err:
                self._send(401, err.encode("utf-8"), "text/plain"); return
            tok = new_token(uid)
            users = load_users()
            body = json.dumps({"id": uid, "name": users[uid]["name"], "color": users[uid]["color"], "token": tok},
                              ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/api/logout":
            if self.command != "POST":
                self._send(405, b"metodo no permitido", "text/plain"); return
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send(400, b"JSON invalido", "text/plain"); return
            revoke_token(req.get("token", ""))
            self._send(200, b"ok", "text/plain")
            return

        if path == "/api/me":
            tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
            uid = user_from_token(tok)
            if not uid:
                self._send(401, b"sesion invalida", "text/plain"); return
            users = load_users()
            u = users.get(uid)
            if not u:
                self._send(404, b"usuario no existe", "text/plain"); return
            body = json.dumps(public_user(u), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        # Progreso: GET (descargar o listar backups) + PUT (guardar) — por usuario
        if path == "/api/progress":
            migrate_legacy()
            qs = self.path.split("?", 1)[-1]
            user_id = re.search(r"(?:^|&)user=([^&]+)", qs)
            user_id = unquote(user_id.group(1)) if user_id else "owner"
            # Validar sesión: si hay token, debe pertenecer al user; si no hay
            # token, se permite solo al owner (compatibilidad con tests antiguos).
            tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
            uid = user_from_token(tok)
            if uid is None and user_id != "owner":
                self._send(401, b"sesion requerida", "text/plain"); return
            if uid is not None and uid != user_id:
                self._send(403, b"no autorizado para este usuario", "text/plain"); return
            if self.command == "GET":
                if "download=1" in qs.split("&"):
                    data = read_user_progress(user_id)
                    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
                else:
                    data = list_user_backups(user_id)
                    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
            elif self.command == "PUT":
                try:
                    raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                    data = json.loads(raw.decode("utf-8"))
                    if not isinstance(data, dict):
                        self._send(400, b"formato invalido: debe ser dict JSON", "text/plain")
                        return
                    if "log" not in data or not isinstance(data["log"], list):
                        data["log"] = []
                    if "errs" not in data or not isinstance(data["errs"], list):
                        data["errs"] = []
                    save_user_progress(user_id, data)
                    body = b"ok"
                    self._send(200, body, "text/plain")
                except (ValueError, OSError):
                    self._send(400, b"JSON invalido", "text/plain")
            else:
                self._send(405, b"metodo no permitido", "text/plain")
            return

        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return

        self._send(404, b"not found", "text/plain")

    def do_GET(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_HEAD(self):
        self._handle()


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    migrate_legacy()
    print(f"B2First portal en http://0.0.0.0:{PORT} (root={ROOT})")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
