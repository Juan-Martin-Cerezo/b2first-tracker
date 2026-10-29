#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 First study portal — serves the tracker + material (PDF/audio) from the Pi.

Access: http://100.112.213.66:8088 (Tailscale) or http://127.0.0.1:8088 (local).
Dynamically scans ~/Descargas/b2-first: any PDF/MP3/ZIP you add to that folder
shows up on /libros (catalog with a search box) and on /libros.json (consumed
by the LIBROS tab of the tracker).

Endpoints:
  GET /            → index.html (the single-file tracker)
  GET /libros      → HTML page with all the material (viewer + audio)
  GET /libros.json → JSON with the catalog (for the tracker)
  GET /files/<rel> → serves a material file with Range support
                     (needed so audio can be seeked)
  GET /api/progress?download=1 → downloads the saved progress (JSON)
  GET /api/progress → list of backups (JSON) {file, size, date}
  PUT /api/progress → saves the progress (JSON body) and backs up the previous one
  GET /favicon.ico → 204 (does not exist, don't log a 404)

Persistence: progress lives in <repo>/data/progress.json. Each PUT
automatically backs up the previous version in <repo>/data/backups/
(latest wins + backups). Data stays ONLY on this Pi, no auth (private network).

Dependencies: stdlib ONLY (http.server, os, re, html, mimetypes).
Deploy: systemd unit b2first.service (Restart=always) in this dir.
"""
import os, re, html, mimetypes, json, shutil, time, hashlib, secrets, threading
import urllib.request, urllib.error
from urllib.parse import quote, unquote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import store
import prompts

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ROOT      = os.path.expanduser("~/Descargas/b2-first")  # material (PDF/MP3/ZIP)
TRACKER   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
DIAG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "material", "diagnostico.json")
_DIAG_CACHE = {"path": None, "mtime": None, "body": None}
PORT      = int(os.environ.get("PORT", 8088))           # 8080 is taken by docker-proxy
EXTS      = {".pdf": "PDF", ".mp3": "AUDIO", ".zip": "ZIP"}
DATA_DIR  = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
store.DATA_DIR = DATA_DIR
PROG_FILE = os.path.join(DATA_DIR, "progress.json")
BK_DIR    = os.path.join(DATA_DIR, "backups")
BK_KEEP   = 20                                          # backups to keep per user
# Users (multi-account system)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
USERS_DIR  = os.path.join(DATA_DIR, "users")            # data/users/<id>/progress.json
TOKEN_TTL  = 7 * 24 * 3600                              # session valid for 7 days
OWNER_PASSWORD = os.environ.get("B2_OWNER_PASSWORD", "b2first")  # owner password used when migrating
B2_DEMO   = os.environ.get("B2_DEMO", "0").strip() == "1"
B2_REGISTER = (os.environ.get("B2_REGISTER", "open").strip().lower() or "open")


def _is_demo():
    """Return True if the server is in public demo mode (B2_DEMO=1)."""
    if isinstance(B2_DEMO, str):
        return B2_DEMO.strip() in ("1", "true", "True")
    return bool(B2_DEMO)


def _register_mode():
    """Return "open" or "closed" (B2_REGISTER). Demo always reports "closed"."""
    if _is_demo():
        return "closed"
    val = B2_REGISTER if isinstance(B2_REGISTER, str) else ("open" if B2_REGISTER else "closed")
    return "closed" if val.strip().lower() == "closed" else "open"

# AI configuration (DeepSeek / Gemini) — injectable via env for tests without network
DEFAULT_AI_PROVIDER = "deepseek"
DEFAULT_DEEPSEEK_BASE = "https://api.deepseek.com"
DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_AI_BASE = DEFAULT_DEEPSEEK_BASE
DEFAULT_AI_MODEL = DEFAULT_DEEPSEEK_MODEL
B2_AI_PROVIDER = os.environ.get("B2_AI_PROVIDER", DEFAULT_AI_PROVIDER)
B2_AI_BASE = os.environ.get("B2_AI_BASE", "")
B2_AI_MODEL = os.environ.get("B2_AI_MODEL", "")
AI_ALLOWED_KINDS = ("Essay", "Article", "Report", "Review", "Email")
AI_TIMEOUT = 25
_AI_LOCK = threading.Lock()
_AI_RATE = {}  # {ip: [timestamps]}


def _check_ai_rate(ip):
    """In-memory rate limit: max 10/min and 60/hour per IP."""
    now = time.time()
    with _AI_LOCK:
        hist = [t for t in _AI_RATE.get(ip, []) if now - t < 3600.0]
        last_min = sum(1 for t in hist if now - t < 60.0)
        if last_min >= 10 or len(hist) >= 60:
            _AI_RATE[ip] = hist
            return False
        hist.append(now)
        _AI_RATE[ip] = hist
        return True


def _validate_ai_payload(obj):
    """Validate the JSON returned by the model against the Cambridge schema."""
    if not isinstance(obj, dict):
        return None
    for extra_k in prompts.SCHEMA_KEYS_EXTRA:
        if extra_k not in obj:
            return None
    bands = obj.get("bands")
    feedback = obj.get("feedback")
    quotes = obj.get("quotes")
    weaknesses = obj.get("weaknesses")
    rewrite = obj.get("rewrite")
    if (
        not isinstance(bands, dict)
        or not isinstance(feedback, dict)
        or not isinstance(quotes, dict)
        or not isinstance(weaknesses, dict)
    ):
        return None
    req_keys = set(prompts.SCHEMA_KEYS)
    if (
        set(bands.keys()) != req_keys
        or set(feedback.keys()) != req_keys
        or set(quotes.keys()) != req_keys
        or set(weaknesses.keys()) != req_keys
    ):
        return None
    if not isinstance(rewrite, list) or len(rewrite) != 3:
        return None
    if not all(isinstance(s, str) and s.strip() for s in rewrite):
        return None
    clean_bands = {}
    clean_feedback = {}
    clean_quotes = {}
    clean_weaknesses = {}
    for k in prompts.SCHEMA_KEYS:
        b = bands[k]
        if type(b) is not int or b < 0 or b > 5:
            return None
        fb = feedback[k]
        qt = quotes[k]
        wk = weaknesses[k]
        if not isinstance(fb, str) or not fb.strip():
            return None
        if not isinstance(qt, str) or not qt.strip():
            return None
        if not isinstance(wk, list) or len(wk) < 2:
            return None
        if not all(isinstance(w, str) and w.strip() for w in wk):
            return None
        clean_bands[k] = b
        clean_feedback[k] = fb.strip()
        clean_quotes[k] = qt.strip()
        clean_weaknesses[k] = [w.strip() for w in wk]
    return {
        "bands": clean_bands,
        "total": sum(clean_bands.values()),
        "feedback": clean_feedback,
        "quotes": clean_quotes,
        "weaknesses": clean_weaknesses,
        "rewrite": [s.strip() for s in rewrite],
    }


# ---------------------------------------------------------------------------
# File catalog
# ---------------------------------------------------------------------------
def scan():
    """Walk ROOT and return the file list {rel, name, ext, size, folder}.

    rel = relative path (for /files/), folder = parent folder (for grouping).
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
    """Format bytes → human-readable '1.2 MB'."""
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.0f} TB"


def esc(s):
    """Escape HTML (prevents injection via weird file names)."""
    return html.escape(str(s))


# ---------------------------------------------------------------------------
# Progress persistence (delegated to store.py)
# ---------------------------------------------------------------------------
def read_progress():
    """Return the owner's saved progress, or {} if it does not exist."""
    return read_user_progress("owner")


def save_progress(data):
    """Persist the owner's progress atomically + back up the previous one."""
    save_user_progress("owner", data)


def list_backups():
    """Return [{file, size, date}] with the owner's backups, most recent first."""
    return list_user_backups("owner")


# ---------------------------------------------------------------------------
# Users + sessions (multi-account system)
# ---------------------------------------------------------------------------
def _read_json(path, default):
    """Read a JSON file or return the default if it does not exist / is corrupt."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    """Write a JSON file atomically (tmp + rename)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def load_users():
    """Return {user_id: {id, name, salt, hash, color, created}}."""
    return store.list_users()


def save_users(users):
    for uid, rec in users.items():
        store.create_user(uid, rec)


def load_tokens():
    """Return {token: {user_id, exp}}."""
    return _read_json(TOKENS_FILE, {})


def save_tokens(tokens):
    _write_json(TOKENS_FILE, tokens)


def hash_password(salt, password):
    """PBKDF2-HMAC-SHA256 hash with 200,000 iterations."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()


def _legacy_hash_password(salt, password):
    """sha256(salt + password) used before the migration to pbkdf2."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def new_token(user_id):
    """Create a session token valid for TOKEN_TTL and persist it."""
    tokens = load_tokens()
    # Prune expired tokens
    now = time.time()
    tokens = {t: v for t, v in tokens.items() if v.get("exp", 0) > now}
    tok = secrets.token_hex(24)
    tokens[tok] = {"user_id": user_id, "exp": now + TOKEN_TTL}
    save_tokens(tokens)
    return tok


def user_from_token(token):
    """Return the token's user_id if it is valid, or None."""
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
    """User without sensitive fields (no salt/hash)."""
    return {"id": u["id"], "name": u["name"], "color": u.get("color", "#1b2b48"),
            "created": u.get("created", "")}


def user_prog_file(user_id):
    """Path to a user's progress.json."""
    return store._prog_file(user_id)


def user_bk_dir(user_id):
    """Path to a user's backup directory."""
    return store._bk_dir(user_id)


def register_user(name, password, color=None):
    """Create a user. Return (user_id, error)."""
    users = store.list_users()
    name = name.strip()
    if not name:
        return None, "name is empty"
    if len(password) < 8:
        return None, "password too short (min 8)"
    # Normalize the name for a unique id (slug + suffix if repeated)
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "user"
    uid = base
    n = 2
    while uid in users:
        uid = f"{base}-{n}"
        n += 1
    salt = secrets.token_hex(8)  # 16 chars
    store.create_user(uid, {
        "id": uid, "name": name, "salt": salt,
        "hash": hash_password(salt, password),
        "algo": "pbkdf2",
        "color": color or "#1b2b48",
        "created": time.strftime("%Y-%m-%d %H:%M"),
    })
    return uid, None


def login_user(name, password):
    """Validate credentials and migrate legacy hashes to pbkdf2. Return (user_id, error)."""
    users = store.list_users()
    name = name.strip()
    for u in users.values():
        if u["name"].lower() == name.lower():
            algo = u.get("algo")
            if algo == "pbkdf2":
                if u["hash"] == hash_password(u["salt"], password):
                    return u["id"], None
            elif not algo:
                if u["hash"] == _legacy_hash_password(u["salt"], password):
                    migrated = dict(u)
                    migrated["hash"] = hash_password(u["salt"], password)
                    migrated["algo"] = "pbkdf2"
                    store.create_user(u["id"], migrated)
                    return u["id"], None
            return None, "wrong password"
    return None, "user not found"


def change_password(user_id, current, new_password):
    """Verify `current` and set `new_password` (pbkdf2). Return (error, http_code)."""
    u = store.get_user(user_id)
    if not u:
        return "user not found", 401
    algo = u.get("algo")
    if algo == "pbkdf2":
        ok = u["hash"] == hash_password(u["salt"], current)
    elif not algo:
        ok = u["hash"] == _legacy_hash_password(u["salt"], current)
    else:
        ok = False
    if not isinstance(new_password, str) or len(new_password) < 8:
        return "password too short (min 8)", 400
    if not ok:
        return "wrong password", 401
    salt = secrets.token_hex(8)  # 16 chars
    rec = dict(u)
    rec["salt"] = salt
    rec["hash"] = hash_password(salt, new_password)
    rec["algo"] = "pbkdf2"
    store.create_user(user_id, rec)
    return None, 200


def migrate_legacy():
    """Migrate data/progress.json → data/users/owner/progress.json (once).

    If users.json already exists it does nothing. Creates the 'owner' user with
    the OWNER_PASSWORD and keeps the current progress.
    """
    if store.list_users():
        return
    uid = "owner"
    salt = secrets.token_hex(8)
    store.create_user(uid, {
        "id": uid, "name": "Owner", "salt": salt,
        "hash": hash_password(salt, OWNER_PASSWORD),
        "algo": "pbkdf2",
        "color": "#1b2b48", "created": time.strftime("%Y-%m-%d %H:%M"),
    })
    if os.path.exists(PROG_FILE):
        legacy_data = _read_json(PROG_FILE, {})
        store.put_progress(uid, legacy_data)
        try:
            os.remove(PROG_FILE)
        except OSError:
            pass
    # Move old backups to the owner user
    if os.path.isdir(BK_DIR):
        try:
            for fn in os.listdir(BK_DIR):
                src = os.path.join(BK_DIR, fn)
                if os.path.isfile(src):
                    shutil.move(src, os.path.join(store._bk_dir(uid), fn))
            os.rmdir(BK_DIR)
        except OSError:
            pass


def read_user_progress(user_id):
    """Return a user's progress, or {} if it does not exist."""
    data = store.get_progress(user_id)
    return data if data is not None else {}


def save_user_progress(user_id, data):
    """Persist a user's progress atomically + backup."""
    store.put_progress(user_id, data)


def list_user_backups(user_id):
    """Return [{file, size, date}] with a user's backups."""
    bk_dir = store._bk_dir(user_id)
    try:
        files = sorted(os.listdir(bk_dir), reverse=True)
    except OSError:
        return []
    out = []
    for fn in files:
        full = os.path.join(bk_dir, fn)
        try:
            st = os.stat(full)
        except OSError:
            continue
        out.append({"file": fn, "size": st.st_size,
                    "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
    return out


# ---------------------------------------------------------------------------
# /libros page (material with viewer + audio + search)
# ---------------------------------------------------------------------------
def portal():
    """Generate the material's HTML page grouped by folder."""
    items = scan()
    # Group by folder, preserving the folders' natural order.
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
            href = "/files/" + quote(it["rel"])  # quote → spaces/accents OK
            if it["ext"] == "AUDIO":
                cards += f'''<div class="card audio">
                  <div class="top"><span class="ico">🎧</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <audio controls preload="none" src="{href}"></audio>
                  <a class="dl" href="{href}" download>Download</a></div>'''
            elif it["ext"] == "PDF":
                cards += f'''<div class="card">
                  <div class="top"><span class="ico">📄</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <div class="acts"><a class="btn" href="{href}" target="_blank">Open PDF</a><a class="dl" href="{href}" download>Download</a></div></div>'''
            else:  # ZIP
                cards += f'''<div class="card">
                  <div class="top"><span class="ico">🗜️</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <a class="btn" href="{href}" download>Download ZIP</a></div>'''
        blocks.append(f'<h3 class="folder">{esc(folder)}</h3><div class="grid">{cards}</div>')

    total = sum(1 for _ in items)
    # Full page with dark styles (same look as the tracker) + a live search
    # that hides cards and empty folders.
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
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
<a class="back" href="/">← Back to Tracker</a>
<h1>📚 Material B2 First</h1>
<div class="sub">{total} files · PDFs open in the browser viewer (desktop and mobile) · audio plays here</div>
<input id="filtro" placeholder="🔍 Search material... (e.g.: listening, speaking, handbook)">
<div id="contenido">
{''.join(blocks)}
</div>
<script>
document.getElementById('filtro').addEventListener('input',function(){{
  var q=this.value.toLowerCase().trim();
  // Hide/show cards based on the filter text.
  document.querySelectorAll('#contenido .card').forEach(function(c){{
    c.style.display=(!q||c.textContent.toLowerCase().includes(q))?'':'none';
  }});
  // Hide folders left with no visible cards.
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
        """Silence per-request logging (noise in journald)."""
        pass

    def _send(self, code, body, ctype, extra=None):
        """Helper: response with minimal headers + Content-Length."""
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        """Single router (used by GET and HEAD)."""
        path = unquote(self.path.split("?")[0])

        # Tracker (index.html)
        if path in ("/", "/index.html"):
            try:
                body = open(TRACKER, "rb").read()
                self._send(200, body, "text/html; charset=utf-8")
            except OSError:
                self._send(404, b"tracker not found", "text/plain")
            return

        # Material page
        if path == "/libros":
            self._send(200, portal().encode("utf-8"), "text/html; charset=utf-8")
            return

        # Material files with anti-traversal + Range support (audio)
        if path.startswith("/files/"):
            rel = path[len("/files/"):]
            full = os.path.realpath(os.path.join(ROOT, rel))
            # Block .. and links outside ROOT.
            if not full.startswith(os.path.realpath(ROOT)) or not os.path.isfile(full):
                self._send(404, b"not found", "text/plain")
                return
            size = os.path.getsize(full)
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            # Range: the browser requests chunks for the <audio> (seek/rewind).
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

        # Static tracker assets (favicon, manifest, apple-touch-icon)
        if path.startswith("/assets/"):
            rel = path[len("/assets/"):]
            root_assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
            full = os.path.realpath(os.path.join(root_assets, rel))
            if not full.startswith(os.path.realpath(root_assets)) or not os.path.isfile(full):
                self._send(404, b"not found", "text/plain")
                return
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as f:
                data = f.read()
            self._send(200, data, ctype)
            return

        # Catalog JSON (consumed by the LIBROS tab of the tracker)
        if path == "/libros.json":
            data = [{"name": it["name"], "folder": it["folder"], "ext": it["ext"],
                     "rel": it["rel"], "size": it["size"], "href": "/files/" + quote(it["rel"])}
                    for it in scan()]
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        # Cold-start diagnostic (public material without auth, cached in memory)
        if path == "/diagnostico.json":
            if not os.path.isfile(DIAG_FILE):
                self._send(404, json.dumps({"error": "diagnostic not found"}).encode("utf-8"), "application/json")
                return
            try:
                st = os.stat(DIAG_FILE)
                if _DIAG_CACHE["body"] is not None and _DIAG_CACHE["path"] == DIAG_FILE and _DIAG_CACHE["mtime"] == st.st_mtime:
                    self._send(200, _DIAG_CACHE["body"], "application/json")
                    return
                with open(DIAG_FILE, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                items = obj.get("items") if isinstance(obj, dict) else None
                if not isinstance(items, list) or len(items) != 12:
                    raise ValueError("items != 12")
                for it in items:
                    if not isinstance(it, dict):
                        raise ValueError("item is not a dict")
                    ans = it.get("answer")
                    opts = it.get("options")
                    if type(ans) is not int or ans < 0 or ans > 3:
                        raise ValueError("answer out of 0-3")
                    if not isinstance(opts, list) or len(opts) != 4:
                        raise ValueError("options != 4")
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                _DIAG_CACHE["path"] = DIAG_FILE
                _DIAG_CACHE["mtime"] = st.st_mtime
                _DIAG_CACHE["body"] = body
                self._send(200, body, "application/json")
            except (OSError, ValueError, TypeError):
                self._send(500, json.dumps({"error": "invalid diagnostic"}).encode("utf-8"), "application/json")
            return

        # Public server configuration (demo mode, version, AI support, registration)
        if path == "/api/config":
            body = json.dumps({"demo": _is_demo(), "version": "1.0.0", "ai": True,
                               "register": _register_mode()}, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        # In demo mode accounts and sync are blocked (nobody reads or writes data/)
        if _is_demo() and path in ("/api/register", "/api/login", "/api/logout", "/api/me", "/api/users", "/api/progress", "/api/password"):
            clen = int(self.headers.get("Content-Length", 0) or 0)
            if clen > 0:
                self.rfile.read(clen)
            body = json.dumps({"error": "demo mode: no accounts or sync"}, ensure_ascii=False).encode("utf-8")
            self._send(403, body, "application/json; charset=utf-8")
            return

        # ---- User / auth API ----
        if path == "/api/users":
            migrate_legacy()
            users = [public_user(u) for u in store.list_users().values()]
            body = json.dumps(users, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/api/register":
            migrate_legacy()
            if self.command != "POST":
                self._send(405, b"method not allowed", "text/plain"); return
            if _register_mode() == "closed":
                clen = int(self.headers.get("Content-Length", 0) or 0)
                if clen > 0:
                    self.rfile.read(clen)
                body = json.dumps({"error": "registration is closed"}, ensure_ascii=False).encode("utf-8")
                self._send(403, body, "application/json; charset=utf-8")
                return
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send(400, b"invalid JSON", "text/plain"); return
            uid, err = register_user(req.get("name", ""), req.get("password", ""), req.get("color"))
            if err:
                self._send(400, err.encode("utf-8"), "text/plain"); return
            tok = new_token(uid)
            u = store.get_user(uid)
            body = json.dumps({"id": uid, "name": u["name"], "color": u["color"], "token": tok},
                              ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/api/login":
            migrate_legacy()
            if self.command != "POST":
                self._send(405, b"method not allowed", "text/plain"); return
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send(400, b"invalid JSON", "text/plain"); return
            uid, err = login_user(req.get("name", ""), req.get("password", ""))
            if err:
                self._send(401, err.encode("utf-8"), "text/plain"); return
            tok = new_token(uid)
            u = store.get_user(uid)
            body = json.dumps({"id": uid, "name": u["name"], "color": u["color"], "token": tok},
                              ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/api/logout":
            if self.command != "POST":
                self._send(405, b"method not allowed", "text/plain"); return
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send(400, b"invalid JSON", "text/plain"); return
            revoke_token(req.get("token", ""))
            self._send(200, b"ok", "text/plain")
            return

        if path == "/api/me":
            tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
            uid = user_from_token(tok)
            if not uid:
                self._send(401, b"invalid session", "text/plain"); return
            u = store.get_user(uid)
            if not u:
                self._send(404, b"user does not exist", "text/plain"); return
            body = json.dumps(public_user(u), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        # Password change (Bearer auth). Invalidates every other session of the user.
        if path == "/api/password":
            if self.command != "POST":
                self._send(405, b"method not allowed", "text/plain"); return
            tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
            uid = user_from_token(tok)
            if not uid:
                self._send(401, json.dumps({"error": "invalid session"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send(400, json.dumps({"error": "invalid JSON"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            err, code = change_password(uid, req.get("current", ""), req.get("next", ""))
            if err:
                self._send(code, json.dumps({"error": err}).encode("utf-8"), "application/json; charset=utf-8")
                return
            # Keep only the current session: a leaked password must not keep old sessions alive.
            tokens = load_tokens()
            tokens = {t: v for t, v in tokens.items() if t == tok or v.get("user_id") != uid}
            save_tokens(tokens)
            self._send(200, json.dumps({"ok": True}).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Progress: GET (download or list backups) + PUT (save) — per user
        if path == "/api/progress":
            migrate_legacy()
            qs = self.path.split("?", 1)[-1]
            user_id = re.search(r"(?:^|&)user=([^&]+)", qs)
            user_id = unquote(user_id.group(1)) if user_id else "owner"
            # Validate the session: if there is a token it must belong to the user; if
            # there is no token, only the owner is allowed (backwards compat with old tests).
            tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
            uid = user_from_token(tok)
            if uid is None and user_id != "owner":
                self._send(401, b"session required", "text/plain"); return
            if uid is not None and uid != user_id:
                self._send(403, b"not authorized for this user", "text/plain"); return
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
                        self._send(400, b"invalid format: must be a JSON object", "text/plain")
                        return
                    if "log" not in data or not isinstance(data["log"], list):
                        data["log"] = []
                    if "errs" not in data or not isinstance(data["errs"], list):
                        data["errs"] = []
                    if isinstance(data.get("settings"), dict):
                        data["settings"].pop("aiKey", None)
                    save_user_progress(user_id, data)
                    body = b"ok"
                    self._send(200, body, "text/plain")
                except (ValueError, OSError):
                    self._send(400, b"invalid JSON", "text/plain")
            else:
                self._send(405, b"method not allowed", "text/plain")
            return

        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return

        if path == "/api/ai/writing":
            if self.command != "POST":
                self._send(405, json.dumps({"error": "method not allowed"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            xff = self.headers.get("X-Forwarded-For")
            client_ip = xff.split(",")[0].strip() if xff else (self.client_address[0] if self.client_address else "local")
            if not _check_ai_rate(client_ip):
                self._send(429, json.dumps({"error": "rate limit"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                req = json.loads(raw.decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("not dict")
            except (ValueError, UnicodeDecodeError):
                self._send(400, json.dumps({"error": "invalid json"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            text = req.get("text")
            kind = req.get("kind")
            if not isinstance(text, str) or not (50 <= len(text.strip()) <= 3000) or not (50 <= len(text) <= 3000):
                self._send(400, json.dumps({"error": "text must be between 50 and 3000 chars"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            if kind not in AI_ALLOWED_KINDS:
                self._send(400, json.dumps({"error": "invalid kind"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            api_key = (req.get("provider_key") or req.get("key") or os.environ.get("B2_AI_KEY") or "").strip()
            if not api_key:
                self._send(502, json.dumps({"error": "missing provider key"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            env_prov = B2_AI_PROVIDER if B2_AI_PROVIDER != DEFAULT_AI_PROVIDER else os.environ.get("B2_AI_PROVIDER", DEFAULT_AI_PROVIDER)
            provider = (req.get("provider") or env_prov or DEFAULT_AI_PROVIDER).strip().lower()
            if provider not in ("deepseek", "gemini"):
                self._send(400, json.dumps({"error": "invalid provider"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            default_base = DEFAULT_DEEPSEEK_BASE if provider == "deepseek" else DEFAULT_GEMINI_BASE
            default_model = DEFAULT_DEEPSEEK_MODEL if provider == "deepseek" else DEFAULT_GEMINI_MODEL
            base = (B2_AI_BASE or os.environ.get("B2_AI_BASE") or default_base).strip()
            env_model = B2_AI_MODEL or os.environ.get("B2_AI_MODEL") or ""
            model = (req.get("model") or env_model or default_model).strip()
            prompt_text = prompts.writing_prompt(text.strip(), kind)
            if provider == "deepseek":
                url = f"{base.rstrip('/')}/chat/completions"
                payload = json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompts.WRITING_SYSTEM},
                        {"role": "user", "content": f"=== TASK TYPE (GENRE) ===\n{kind}\n\n=== STUDENT TEXT ===\n{text.strip()}"},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                }).encode("utf-8")
                req_headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                }
            else:
                url = f"{base.rstrip('/')}/models/{model}:generateContent"
                payload = json.dumps({
                    "contents": [{"parts": [{"text": prompt_text}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
                }).encode("utf-8")
                req_headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                }
            up_req = urllib.request.Request(
                url,
                data=payload,
                headers=req_headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(up_req, timeout=AI_TIMEOUT) as resp:
                    up_raw = resp.read().decode("utf-8")
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
                self._send(502, json.dumps({"error": "upstream provider failed"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            try:
                up_json = json.loads(up_raw)
                if provider == "deepseek":
                    cand_text = up_json["choices"][0]["message"]["content"]
                else:
                    cand_text = up_json["candidates"][0]["content"]["parts"][0]["text"]
                cand_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", cand_text.strip())
                model_obj = json.loads(cand_text)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                self._send(422, json.dumps({"error": "invalid model json"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            validated = _validate_ai_payload(model_obj)
            if not validated:
                self._send(422, json.dumps({"error": "schema validation failed"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            validated["model"] = model
            self._send(200, json.dumps(validated, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
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
# Startup
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not _is_demo():
        migrate_legacy()
    print(f"B2First portal at http://0.0.0.0:{PORT} (root={ROOT})")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
