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
import os, re, html, mimetypes, json, shutil, time, hashlib, hmac, math, secrets, threading
import urllib.request, urllib.error
import ipaddress
import traceback
from collections import deque
from datetime import date, timedelta
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
TOKEN_TTL  = 30 * 24 * 3600                             # session valid for 30 days (sliding)
OWNER_PASSWORD = os.environ.get("B2_OWNER_PASSWORD", "b2first")  # owner password used when migrating
B2_DEMO   = os.environ.get("B2_DEMO", "0").strip() == "1"
B2_REGISTER = (os.environ.get("B2_REGISTER", "open").strip().lower() or "open")
PROGRESS_MAX_BYTES = 2 * 1024 * 1024                    # max size of a progress payload (2 MB)
AI_MAX_BYTES = 32 * 1024                                # max size of an AI request body (32 KB)
B2_PUBLIC_HEALTH = os.environ.get("B2_PUBLIC_HEALTH", "0").strip() == "1"
_START_TS = time.time()                                 # for /api/health uptime_s


def _is_demo():
    """Return True if the server is in public demo mode (B2_DEMO=1)."""
    if isinstance(B2_DEMO, str):
        return B2_DEMO.strip() in ("1", "true", "True")
    return bool(B2_DEMO)


def _public_health():
    """True when /api/health may expose absolute paths (B2_PUBLIC_HEALTH=1)."""
    if isinstance(B2_PUBLIC_HEALTH, str):
        return B2_PUBLIC_HEALTH.strip() in ("1", "true", "True")
    return bool(B2_PUBLIC_HEALTH)


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

# --- In-memory rate limiting (stdlib only; the server is a ThreadingHTTPServer) ---
_RATE_LOCK = threading.Lock()
_RATE = {}  # {key: (deque of timestamps, window_s)}
_AI_RATE = _RATE  # tests reset rate state through S._AI_RATE.clear()


def _rate(key, limit, window_s):
    """Sliding-window rate limit: True = allowed, False = over the limit.

    Old entries are pruned on every check, so the store only holds live hits.
    """
    now = time.time()
    with _RATE_LOCK:
        for k, (dq, win) in list(_RATE.items()):
            while dq and now - dq[0] >= win:
                dq.popleft()
            if not dq:
                del _RATE[k]
        dq, _win = _RATE.setdefault(key, (deque(), window_s))
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


def _retry_after(key, window_s):
    """Seconds until the oldest hit of `key` leaves the window (min 1)."""
    with _RATE_LOCK:
        entry = _RATE.get(key)
        if not entry or not entry[0]:
            return 1
        return max(1, int(window_s - (time.time() - entry[0][0])) + 1)


def _check_ai_rate(ip):
    """AI per-IP rate limit: max 10/min and 60/hour (daily quota is separate)."""
    ok_min = _rate(f"ai:min:{ip}", 10, 60)
    ok_hour = _rate(f"ai:hour:{ip}", 60, 3600)
    return ok_min and ok_hour


def _is_trusted_proxy(peer):
    """True for loopback/private peers (the Coolify proxy in front of the app)."""
    try:
        ip = ipaddress.ip_address(peer)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


def _real_ip(handler):
    """Client IP: X-Forwarded-For only when the request comes from loopback/internal."""
    peer = handler.client_address[0] if handler.client_address else ""
    if _is_trusted_proxy(peer):
        xff = handler.headers.get("X-Forwarded-For")
        if xff:
            cand = xff.split(",")[0].strip()
            if cand:
                return cand
    return peer or "local"


# --- Login brute-force guard: per username, survives IP changes (fase 12) ---
_LOGIN_FAIL_LOCK = threading.Lock()
_LOGIN_FAIL = {}  # {username-lower: {"count": int, "until": ts}}
LOGIN_FAIL_MAX = 5                      # failed attempts before the username is locked
LOGIN_LOCK_S = 15 * 60                  # lockout window (15 minutes)
LOGIN_DELAY = (0.0, 0.0, 0.2, 0.5, 1.0)  # progressive delay from the 3rd failure (max 1s)
DUMMY_SALT = "0" * 16                   # timing equalizer for unknown usernames
_DUMMY_DIGEST = None


def _dummy_digest():
    """Fixed PBKDF2 digest: the unknown-user path burns the same work as a real check."""
    global _DUMMY_DIGEST
    if _DUMMY_DIGEST is None:
        _DUMMY_DIGEST = hash_password(DUMMY_SALT, "b2first-timing-dummy")
    return _DUMMY_DIGEST


def _login_fail_key(name):
    """Normalized username used as the lockout key."""
    return name.strip().lower() if isinstance(name, str) else ""


def _login_locked(key):
    """(locked, retry_after) when `key` is under brute-force lockout."""
    now = time.time()
    with _LOGIN_FAIL_LOCK:
        rec = _LOGIN_FAIL.get(key)
        if rec and rec.get("until", 0) > now:
            return True, max(1, int(rec["until"] - now) + 1)
    return False, 0


def _login_failed(key):
    """Count one failed attempt for `key`; returns (count, just_locked)."""
    now = time.time()
    with _LOGIN_FAIL_LOCK:
        rec = _LOGIN_FAIL.setdefault(key, {"count": 0, "until": 0})
        rec["count"] += 1
        if rec["count"] >= LOGIN_FAIL_MAX:
            rec["until"] = now + LOGIN_LOCK_S
            return rec["count"], True
        return rec["count"], False


def _login_succeeded(key):
    """A successful login resets the failure counter."""
    with _LOGIN_FAIL_LOCK:
        _LOGIN_FAIL.pop(key, None)


def _login_delay(count):
    """Progressive delay: 0/0/0.2/0.5/1s from the 3rd consecutive failure."""
    return LOGIN_DELAY[min(max(count, 1) - 1, len(LOGIN_DELAY) - 1)]


# --- Daily AI quota (protects the owner's key: in-memory, resets on date change) ---
_AI_QUOTA_LOCK = threading.Lock()
_AI_QUOTA = {}  # {date iso: {"total": int, "users": {quota_key: int}}}


def _ai_quota_limits():
    """(per_user, total) daily limits from env, default 8 / 80."""
    def _int(name, default):
        try:
            return max(0, int(os.environ.get(name, str(default))))
        except ValueError:
            return default
    return _int("B2_AI_DAILY_PER_USER", 8), _int("B2_AI_DAILY_TOTAL", 80)


def _ai_quota_today():
    """Today's counter (auto-reset: previous days are dropped on access)."""
    today = date.today().isoformat()
    for k in list(_AI_QUOTA):
        if k != today:
            del _AI_QUOTA[k]
    return _AI_QUOTA.setdefault(today, {"total": 0, "users": {}})


def _ai_quota_left(quota_key):
    """Server-key AI calls left today for this user (also capped by the total)."""
    per_user, total = _ai_quota_limits()
    with _AI_QUOTA_LOCK:
        day = _ai_quota_today()
        return min(per_user - day["users"].get(quota_key, 0), total - day["total"])


def _ai_quota_consume(quota_key):
    with _AI_QUOTA_LOCK:
        day = _ai_quota_today()
        day["users"][quota_key] = day["users"].get(quota_key, 0) + 1
        day["total"] += 1


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
    """Write a JSON file atomically (tmp + rename), readable only by the owner (0600)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def load_users():
    """Return {user_id: {id, name, salt, hash, color, created}}."""
    return store.list_users()


def save_users(users):
    for uid, rec in users.items():
        store.create_user(uid, rec)


_TOKENS_LOCK = threading.Lock()  # serializes read-modify-write of tokens.json


def load_tokens():
    """Return {sha256(token): {user_id, exp, issued, last_seen, ua_hash}}."""
    return _read_json(TOKENS_FILE, {})


def save_tokens(tokens):
    _write_json(TOKENS_FILE, tokens)


def _token_key(token):
    """sha256 of the session token: the raw token is never written to disk."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ua_hash(ua):
    """sha256 of the User-Agent (stored instead of the header itself)."""
    return hashlib.sha256((ua or "").encode("utf-8")).hexdigest()


def hash_password(salt, password):
    """PBKDF2-HMAC-SHA256 hash with 200,000 iterations."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()


def _legacy_hash_password(salt, password):
    """sha256(salt + password) used before the migration to pbkdf2."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def verify_password(user_id, password):
    """True if `password` matches the stored hash (pbkdf2 or legacy)."""
    u = store.get_user(user_id)
    if not u or not isinstance(password, str):
        # Same PBKDF2 work as a real check: missing users must not answer faster.
        pw = password if isinstance(password, str) else ""
        hmac.compare_digest(_dummy_digest(), hash_password(DUMMY_SALT, pw))
        return False
    algo = u.get("algo")
    if algo == "pbkdf2":
        return hmac.compare_digest(u["hash"], hash_password(u["salt"], password))
    if not algo:
        return hmac.compare_digest(u["hash"], _legacy_hash_password(u["salt"], password))
    return False


def new_token(user_id, ua=""):
    """Create a session token valid for TOKEN_TTL and persist only its hash."""
    with _TOKENS_LOCK:
        tokens = load_tokens()
        # Prune expired tokens
        now = time.time()
        tokens = {t: v for t, v in tokens.items() if v.get("exp", 0) > now}
        tok = secrets.token_hex(24)
        tokens[_token_key(tok)] = {
            "user_id": user_id, "exp": now + TOKEN_TTL, "issued": now,
            "last_seen": now, "ua_hash": _ua_hash(ua),
        }
        save_tokens(tokens)
    return tok


def auth_from_token(token, ua="", ip="", rid=""):
    """Return (user_id, error) for a session token and extend its expiry (sliding).

    Tokens are stored hashed; a legacy plaintext record is migrated to its hash
    on first use. A User-Agent change is logged as `ua_changed` (never blocked).

    error is None, "session expired" or "invalid session".
    """
    if not token:
        return None, "invalid session"
    key = _token_key(token)
    with _TOKENS_LOCK:
        tokens = load_tokens()
        v = tokens.get(key)
        if v is None and token in tokens:  # legacy plaintext record → hash it
            v = tokens.pop(token)
            tokens[key] = v
        if not v:
            return None, "invalid session"
        if v.get("exp", 0) < time.time():
            return None, "session expired"
        now = time.time()
        v["exp"] = now + TOKEN_TTL  # sliding expiration
        v["last_seen"] = now
        ua_h = _ua_hash(ua)
        if v.get("ua_hash") and v["ua_hash"] != ua_h:
            _audit("ua_changed", v.get("user_id", ""), ip, rid)
        if ua_h:
            v["ua_hash"] = ua_h
        save_tokens(tokens)
        return v.get("user_id"), None


def revoke_token(token):
    with _TOKENS_LOCK:
        tokens = load_tokens()
        key = _token_key(token)
        if key in tokens or token in tokens:
            tokens.pop(key, None)
            tokens.pop(token, None)
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


# --- Password policy (fase 12): embedded list, no dependencies, no downloads ---
COMMON_PASSWORDS = frozenset("""
1234 12345 123456 1234567 12345678 123456789 1234567890 12345678910 111111 11111111
000000 00000000 121212 123123 123321 112233 12121212 12344321 159753 654321 87654321
666666 66666666 7777777 888888 88888888 999999 987654321 102030 101010 12341234
password password1 password12 password123 password1234 password12345 password123456
passwordpassword passw0rd p@ssw0rd p@ssword p@ssw0rd123 passw0rd123 passwd password1!
password! password2 password123! motdepasse senha senha123 contrasena qwerty qwerty123
qwerty1234 qwerty12345 qwertyui qwertyuiop qwerty12 qwe123 qweasd qweasdzxc asd123
asdfgh asdfghjkl asdfghjkl; zxcvbnm zxcvbn 1q2w3e 1q2w3e4r 1q2w3e4r5t qazwsx qazwsxedc
zaq12wsx 1qaz2wsx 1qazxsw2 abc123 abcd1234 abcdefg abcdefgh abc12345 a1b2c3 a123456
iloveyou iloveyou1 ilovemyself love love123 lovely lovely123 amor tequiero angel
angel123 baby baby123 babygirl babyboy boy boy123 girl girl123 princess princess1
princess123 prince sunshine sunshine1 sunflower flower flower123 butterfly rainbow
letmein letmein1 letmein123 welcome welcome1 welcome123 welcome1234 welkom benvenuto
monkey monkey123 dragon dragon123 tiger tiger123 lion lion123 shadow shadow123
master master1 master123 admin admin123 admin1234 administrator root root123 toor
guest guest123 user user123 usuario test test123 testtest test1 demo demo123 demo1
changeme changeme123 change default default123 login login123 access123 secret secret123
trustno1 trustno123 freedom freedom123 whatever hello hello123 hello1 hola hola123
football football1 football123 baseball basketball soccer soccer123 hockey hockey123
jordan michael michael1 jennifer joshua ashley nicole daniel thomas matrix matrix123
starwars starwars1 pokemon pokemon1 batman batman123 superman superman123 spiderman
harley harley123 ranger hunter hunter123 buster killer george sexy sex sex123
computer computer123 internet internet123 server server123 system system123 oracle
mysql database windows linux apple android samsung google facebook twitter instagram
whatsapp snapchat linkedin youtube amazon netflix spotify minecraft fortnite roblox
cambridge cambridge1 english english123 ingles b2first b2first123 firstcertificate
january february march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday summer winter spring autumn
cookie cookies chocolate peanut banana orange apple123 cherry mango strawberry
red123 blue123 green123 black123 white123 yellow silver golden diamond gold123
money money123 rich rich123 forever forever123 nothing nothing123 nopassword
asdf1234 123abc abc1234 abcd123 aaa111 q1w2e3r4 z1x2c3v4 555555 55555555 444444
""".split())


_PASSWORD_ERRORS = {
    "password too short (min 8)": "Password must be at least 8 characters.",
    "password too common": "Password is too common. Choose something harder to guess.",
    "password equals username": "Password must not be your username.",
}


def password_problem(name, password):
    """Return the error key when the password is too weak, else None."""
    if not isinstance(password, str) or len(password) < 8:
        return "password too short (min 8)"
    if isinstance(name, str) and password.strip().lower() == name.strip().lower():
        return "password equals username"
    if password.strip().lower() in COMMON_PASSWORDS:
        return "password too common"
    return None


def register_user(name, password, color=None):
    """Create a user. Return (user_id, error)."""
    users = store.list_users()
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        return None, "name is empty"
    if not isinstance(password, str) or len(password) < 8:
        return None, "password too short (min 8)"
    for u in users.values():
        if u.get("name", "").lower() == name.lower():
            return None, "username taken"
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
    name = name.strip() if isinstance(name, str) else ""
    match = None
    for u in users.values():
        if u.get("name", "").lower() == name.lower():
            match = u
            break
    if not match:
        # Burn the same PBKDF2 work as a real check (no user enumeration by timing).
        pw = password if isinstance(password, str) else ""
        hmac.compare_digest(_dummy_digest(), hash_password(DUMMY_SALT, pw))
        return None, "user not found"
    if verify_password(match["id"], password):
        if not match.get("algo"):
            migrated = dict(match)
            migrated["hash"] = hash_password(match["salt"], password)
            migrated["algo"] = "pbkdf2"
            store.create_user(match["id"], migrated)
        return match["id"], None
    return None, "wrong password"


def change_password(user_id, current, new_password):
    """Verify `current` and set `new_password` (pbkdf2). Return (error, http_code)."""
    u = store.get_user(user_id)
    if not u:
        return "invalid session", 401
    problem = password_problem(u.get("name", ""), new_password)
    if problem:
        return _PASSWORD_ERRORS.get(problem, problem), 400
    if not verify_password(user_id, current):
        return "Wrong password.", 401
    salt = secrets.token_hex(8)  # 16 chars
    rec = dict(u)
    rec["salt"] = salt
    rec["hash"] = hash_password(salt, new_password)
    rec["algo"] = "pbkdf2"
    store.create_user(user_id, rec)
    return None, 200


def delete_user(user_id):
    """Remove the account: data dir, users.json record and every session token."""
    store.remove_user(user_id)
    with _TOKENS_LOCK:
        tokens = load_tokens()
        tokens = {t: v for t, v in tokens.items() if v.get("user_id") != user_id}
        save_tokens(tokens)


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
# /api/health (storage check, no auth)
# ---------------------------------------------------------------------------
def _health_check():
    """Return (status, body): 200 only when the storage is sane, else 503.

    Checks: DATA_DIR is writable (8-byte probe), users.json parses and every
    uid has its folder. Absolute paths are only exposed with B2_PUBLIC_HEALTH=1.
    """
    probe = os.path.join(DATA_DIR, ".health-probe")
    try:
        with open(probe, "wb") as f:
            f.write(b"\0" * 8)
        os.remove(probe)
    except OSError:
        return 503, {"ok": False, "error": "data dir is not writable", "check": "data_dir"}
    try:
        with open(store._users_file(), "r", encoding="utf-8") as f:
            users = json.load(f)
        if not isinstance(users, dict):
            raise ValueError("users.json is not an object")
    except FileNotFoundError:
        users = {}
    except (OSError, ValueError):
        return 503, {"ok": False, "error": "users.json is corrupt", "check": "users_json"}
    missing = []
    for uid in users:
        try:
            if not os.path.isdir(store._user_dir(uid)):
                missing.append(uid)
        except ValueError:
            missing.append(uid)
    if missing:
        return 503, {"ok": False, "error": "missing user directories",
                     "check": "dirs", "missing_dirs": missing}
    return 200, {
        "ok": True,
        "users": len(users),
        "data_dir": DATA_DIR if _public_health() else os.path.basename(DATA_DIR),
        "version": "1.0.0",
        "uptime_s": int(time.time() - _START_TS),
    }


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
# Audit log (fase 12): append-only JSON lines with the auth events.
# NEVER stores tokens, passwords or hashes. Rotates at 5 MB → audit.log.1.
# ---------------------------------------------------------------------------
_AUDIT_LOCK = threading.Lock()
AUDIT_MAX_BYTES = 5 * 1024 * 1024


def _audit_file():
    return os.path.join(DATA_DIR, "audit.log")


def _audit(event, user="", ip="", rid=""):
    """Append one event line to data/audit.log (0600). Best-effort: never raises."""
    line = json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rid": rid or "",
        "event": event,
        "user": user or "",
        "ip": ip or "",
    }, ensure_ascii=False)
    try:
        with _AUDIT_LOCK:
            path = _audit_file()
            try:
                if os.path.exists(path) and os.path.getsize(path) > AUDIT_MAX_BYTES:
                    os.replace(path, path + ".1")
            except OSError:
                pass
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, (line + "\n").encode("utf-8"))
            finally:
                os.close(fd)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
    except OSError:
        pass


def read_audit_events():
    """All audit events in chronological order (the rotated file is included)."""
    events = []
    for path in (_audit_file() + ".1", _audit_file()):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        ev = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(ev, dict):
                        events.append(ev)
        except OSError:
            continue
    return events


# ---------------------------------------------------------------------------
# Progress payload schema (fase 12): PUT /api/progress validation
# ---------------------------------------------------------------------------
PROGRESS_LIST_MAX = 5000         # max items in log / errs
PROGRESS_STR_MAX = 500           # max chars for ordinary strings
PROGRESS_STR_MAX_LONG = 4000     # max chars for note / text fields
PROGRESS_DEPTH_MAX = 6           # max nesting depth of any top-level value


def _depth(v):
    """Nesting depth of a JSON value (scalars = 1, empty containers = 1)."""
    if isinstance(v, dict):
        return 1 + max([_depth(x) for x in v.values()] or [0])
    if isinstance(v, list):
        return 1 + max([_depth(x) for x in v] or [0])
    return 1


def _scan_progress(v, path, key):
    """Return the offending field path for bad strings/numbers, else None."""
    if isinstance(v, str):
        limit = PROGRESS_STR_MAX_LONG if key in ("note", "text") else PROGRESS_STR_MAX
        return path if len(v) > limit else None
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if math.isfinite(v) else path
    if isinstance(v, dict):
        for k, val in v.items():
            err = _scan_progress(val, f"{path}.{k}" if path else str(k), str(k))
            if err:
                return err
        return None
    if isinstance(v, list):
        for i, val in enumerate(v):
            err = _scan_progress(val, f"{path}[{i}]", key)
            if err:
                return err
        return None
    return path


def _validate_progress(data):
    """Validate a progress payload. Return None when valid, else the offending field.

    Unknown keys are kept (forward compatible) but their values still obey the
    string/number rules. The error never echoes the payload back.
    """
    if not isinstance(data, dict):
        return "<root>"
    for name in ("log", "errs"):
        v = data.get(name)
        if v is None and name not in data:
            continue                      # absent → coerced to [] by the caller
        if not isinstance(v, list) or len(v) > PROGRESS_LIST_MAX:
            return name
        for i, item in enumerate(v):
            if not isinstance(item, dict):
                return f"{name}[{i}]"
    for name in ("settings", "profile"):
        v = data.get(name)
        if v is not None and not isinstance(v, dict):
            return name
    for k, v in data.items():
        if _depth(v) > PROGRESS_DEPTH_MAX:
            return str(k)
    for k, v in data.items():
        err = _scan_progress(v, str(k), str(k))
        if err:
            return err
    return None


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ),
}
_LOG_LOCK = threading.Lock()  # keeps one access-log line atomic under concurrency


class H(BaseHTTPRequestHandler):
    # No version banner: the default handler appends the Python version, which tells an
    # attacker which interpreter CVEs to try. Send a bare, unversioned product name.
    server_version = "B2First"
    sys_version = ""

    def log_message(self, fmt, *a):
        """Silence per-request logging (replaced by _log_line: one line, no secrets)."""
        pass

    def _log_line(self):
        """One stdout access line per request. Never logs tokens, query or body."""
        path = self.path.split("?")[0]
        ms = int((time.time() - self._t0) * 1000)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with _LOG_LOCK:
            print(f"{ts} rid={self._rid} {self.command} {path} {self._status} {ms}ms ip={_real_ip(self)}",
                  flush=True)

    def _run(self):
        """Route one request: request id, access log and error containment."""
        self._rid = secrets.token_hex(4)
        self._status = 0
        self._t0 = time.time()
        try:
            self._handle()
        except store.StoreBusy:
            self._safe_json(429, {"error": "busy", "retry_after": 2}, {"Retry-After": "2"})
        except (ConnectionResetError, BrokenPipeError):
            pass  # client went away: just close, never write
        except TimeoutError:
            self._safe_json(504, {"error": "timeout", "rid": self._rid})
        except Exception:
            traceback.print_exc()
            self._safe_json(500, {"error": "internal", "rid": self._rid})
        finally:
            self._log_line()

    def _safe_json(self, code, obj, extra=None):
        """Best-effort JSON response (the client may already be gone)."""
        try:
            self._send_json(code, obj, extra)
        except OSError:
            pass

    def _send(self, code, body, ctype, extra=None):
        """Helper: response with security headers + Content-Length."""
        self._status = code
        self.send_response(code)
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.send_header("X-Request-Id", self._rid)
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, obj, extra=None):
        """Helper: JSON response."""
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8", extra)

    def _rate_limited(self, key, limit, window_s):
        """Apply _rate() and answer 429 + Retry-After when the limit is exceeded."""
        if _rate(key, limit, window_s):
            return False
        self._drain()
        retry = _retry_after(key, window_s)
        self._send_json(429, {"error": "too many requests", "retry_after": retry},
                        {"Retry-After": str(retry)})
        return True

    def _clen(self):
        """Content-Length of the request body (0 if absent or malformed)."""
        try:
            return max(0, int(self.headers.get("Content-Length", 0) or 0))
        except ValueError:
            return 0

    def _drain(self):
        """Read and discard the request body (bounded) so the client can finish."""
        remaining = min(self._clen(), 16 * 1024 * 1024)
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            remaining -= len(chunk)

    def _bearer(self):
        return (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()

    def _auth(self):
        """Return (user_id, error) from the Authorization header."""
        return auth_from_token(self._bearer(), self.headers.get("User-Agent", ""),
                               _real_ip(self), self._rid)

    def _handle(self):
        """Single router (used by GET and HEAD)."""
        path = unquote(self.path.split("?")[0])

        # Global per-IP limit for the whole API (health is excluded on purpose).
        if path.startswith("/api/") and path != "/api/health":
            if self._rate_limited("api:" + _real_ip(self), 300, 60):
                return

        # CORS is closed: answer preflights without any permissive header.
        if self.command == "OPTIONS":
            self._send(204, b"", "text/plain")
            return

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

        # Storage health check (no auth): 200 sane / 503 broken
        if path == "/api/health":
            code, obj = _health_check()
            self._send_json(code, obj)
            return

        # In demo mode accounts and sync are blocked (nobody reads or writes data/)
        if _is_demo() and path in ("/api/register", "/api/login", "/api/logout", "/api/me",
                                   "/api/users", "/api/progress", "/api/password",
                                   "/api/account", "/api/export", "/api/audit"):
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
            if self._rate_limited("register:" + _real_ip(self), 5, 3600):
                return
            if _register_mode() == "closed":
                clen = int(self.headers.get("Content-Length", 0) or 0)
                if clen > 0:
                    self.rfile.read(clen)
                body = json.dumps({"error": "registration is closed"}, ensure_ascii=False).encode("utf-8")
                self._send(403, body, "application/json; charset=utf-8")
                return
            raw = self.rfile.read(self._clen())
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send_json(400, {"error": "invalid JSON"}); return
            problem = password_problem(req.get("name", ""), req.get("password", ""))
            if problem:
                self._send_json(400, {"error": _PASSWORD_ERRORS.get(problem, problem)})
                return
            uid, err = register_user(req.get("name", ""), req.get("password", ""), req.get("color"))
            if err:
                code, msg = {
                    "username taken": (409, "That username is taken."),
                    "password too short (min 8)": (400, "Password must be at least 8 characters."),
                    "name is empty": (400, "Username is required."),
                }.get(err, (400, err))
                self._send_json(code, {"error": msg})
                return
            _audit("register", req.get("name", ""), _real_ip(self), self._rid)
            tok = new_token(uid, self.headers.get("User-Agent", ""))
            u = store.get_user(uid)
            body = json.dumps({"id": uid, "name": u["name"], "color": u["color"], "token": tok},
                              ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/api/login":
            migrate_legacy()
            if self.command != "POST":
                self._send(405, b"method not allowed", "text/plain"); return
            ip = _real_ip(self)
            if self._rate_limited("login-ip:" + ip, 10, 600):
                return
            raw = self.rfile.read(self._clen())
            try:
                req = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send_json(400, {"error": "invalid JSON"}); return
            name = req.get("name", "")
            fkey = _login_fail_key(name)
            if self._rate_limited("login-user:" + fkey, 20, 3600):
                return
            locked, retry = _login_locked(fkey)
            if locked:
                # Locked usernames are rejected before any password work (cross-IP).
                self._send_json(429, {"error": "too many failed attempts", "retry_after": retry},
                                {"Retry-After": str(retry)})
                return
            uid, err = login_user(name, req.get("password", ""))
            if err:
                count, _just_locked = _login_failed(fkey)
                _audit("login_fail", name if isinstance(name, str) else "", ip, self._rid)
                time.sleep(_login_delay(count))
                self._send_json(401, {"error": "Wrong username or password."}); return
            _login_succeeded(fkey)
            u = store.get_user(uid)
            _audit("login_ok", u.get("name", uid), ip, self._rid)
            tok = new_token(uid, self.headers.get("User-Agent", ""))
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
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"}); return
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
            if self._rate_limited("password:" + _real_ip(self), 5, 3600):
                return
            tok = self._bearer()
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"})
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
            keep_key = _token_key(tok)
            with _TOKENS_LOCK:
                tokens = load_tokens()
                tokens = {t: v for t, v in tokens.items()
                          if t in (keep_key, tok) or v.get("user_id") != uid}
                save_tokens(tokens)
            u = store.get_user(uid)
            _audit("password_change", u.get("name", uid) if u else uid, _real_ip(self), self._rid)
            self._send(200, json.dumps({"ok": True}).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Account overview: uid, creation date, data usage and today's AI quota (auth)
        # DELETE /api/account {password} closes the account and erases all its data.
        if path == "/api/account":
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"}); return
            if self.command == "GET":
                u = store.get_user(uid)
                if not u:
                    self._send_json(404, {"error": "user does not exist"}); return
                try:
                    progress_bytes = os.path.getsize(user_prog_file(uid))
                except OSError:
                    progress_bytes = 0
                self._send_json(200, {
                    "uid": uid,
                    "created": u.get("created", ""),
                    "progress_bytes": progress_bytes,
                    "ai_left_today": max(0, _ai_quota_left("user:" + uid)),
                })
                return
            if self.command == "DELETE":
                raw = self.rfile.read(self._clen())
                try:
                    req = json.loads(raw.decode("utf-8"))
                except ValueError:
                    self._send_json(400, {"error": "invalid JSON"}); return
                if not verify_password(uid, req.get("password", "")):
                    self._send_json(401, {"error": "Wrong password."}); return
                u = store.get_user(uid)
                _audit("account_delete", u.get("name", uid) if u else uid, _real_ip(self), self._rid)
                delete_user(uid)
                self._send_json(200, {"ok": True})
                return
            self._send(405, b"method not allowed", "text/plain"); return

        # Audit trail (auth): each user sees their own events, never anyone else's.
        if path == "/api/audit":
            if self.command != "GET":
                self._send(405, b"method not allowed", "text/plain"); return
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"}); return
            u = store.get_user(uid)
            name = u.get("name", "") if u else ""
            m = re.search(r"(?:^|&)limit=(\d+)", self.path.split("?", 1)[-1])
            limit = min(200, max(1, int(m.group(1)))) if m else 50
            mine = {str(uid).lower(), str(name).lower()}
            all_events = read_audit_events()
            events = [e for e in all_events
                      if str(e.get("user", "")).lower() in mine]
            out = {"events": events[-limit:][::-1]}
            if uid == "owner":
                agg = {}
                for e in all_events:
                    key = str(e.get("event", ""))
                    agg[key] = agg.get(key, 0) + 1
                out["aggregate"] = agg
            self._send_json(200, out)
            return

        # Full data export: the complete progress as a JSON download (auth)
        if path == "/api/export":
            if self.command != "GET":
                self._send(405, b"method not allowed", "text/plain"); return
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"}); return
            data = read_user_progress(uid)
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            fname = f"b2first-export-{uid}-{time.strftime('%Y%m%d')}.json"
            self._send(200, body, "application/json; charset=utf-8",
                       {"Content-Disposition": f'attachment; filename="{fname}"'})
            return

        # Progress: GET (download or list backups) + PUT (save) — per user
        if path == "/api/progress":
            migrate_legacy()
            qs = self.path.split("?", 1)[-1]
            m = re.search(r"(?:^|&)user=([^&]*)", qs)
            try:
                user_id = store._safe_uid(unquote(m.group(1)) if m else "owner")
            except ValueError:
                self._drain()
                self._send_json(400, {"error": "invalid user id"})
                return
            # Validate the session: a present token must be valid and belong to the
            # user; with no token only a DIRECT local request may touch the owner's data
            # (backwards compat for the owner's own machine). Any proxied request — the
            # public Funnel always sets X-Forwarded-For — must authenticate, otherwise a
            # stranger could read or overwrite the owner's progress with no credentials.
            tok = self._bearer()
            uid, auth_err = self._auth() if tok else (None, None)
            if tok and not uid:
                self._send_json(401, {"error": auth_err or "invalid session"}); return
            if not tok:
                proxied = bool(self.headers.get("X-Forwarded-For") or self.headers.get("X-Real-IP"))
                if user_id != "owner" or proxied:
                    self._send_json(401, {"error": "session required"}); return
            if uid is not None and uid != user_id:
                self._send_json(403, {"error": "not authorized for this user"}); return
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
                if self._clen() > PROGRESS_MAX_BYTES:
                    self._drain()
                    self._send_json(413, {"error": "progress too large"}); return
                if self._rate_limited("progress:" + user_id, 60, 60):
                    return
                try:
                    raw = self.rfile.read(self._clen())
                    data = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._send(400, b"invalid JSON", "text/plain")
                    return
                field = _validate_progress(data)
                if field is not None:
                    self._send_json(422, {"error": "invalid progress", "field": field})
                    return
                if "log" not in data:
                    data["log"] = []
                if "errs" not in data:
                    data["errs"] = []
                if isinstance(data.get("settings"), dict):
                    data["settings"].pop("aiKey", None)
                if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > PROGRESS_MAX_BYTES:
                    self._send_json(413, {"error": "progress too large"}); return
                save_user_progress(user_id, data)
                body = b"ok"
                self._send(200, body, "text/plain")
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
            if self._clen() > AI_MAX_BYTES:
                self._drain()
                self._send(413, json.dumps({"error": "ai payload too large"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            client_ip = _real_ip(self)
            if not _check_ai_rate(client_ip):
                self._drain()
                self._send(429, json.dumps({"error": "rate limit"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            try:
                length = self._clen()
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
            # A key sent in the request is the user's own: it never touches the
            # owner's key nor the server quota. Otherwise the shared server key
            # is used and the daily quota (per user + total) applies.
            api_key = (req.get("provider_key") or req.get("key") or "").strip()
            if not api_key:
                quota_uid, _auth_err = self._auth() if self._bearer() else (None, None)
                quota_key = "user:" + quota_uid if quota_uid else "ip:" + client_ip
                if _ai_quota_left(quota_key) <= 0:
                    _audit("quota_hit", quota_uid or "", client_ip, self._rid)
                    reset = (date.today() + timedelta(days=1)).isoformat()
                    self._send(429, json.dumps({"error": "daily AI quota reached", "reset": reset}).encode("utf-8"), "application/json; charset=utf-8")
                    return
                api_key = (os.environ.get("B2_AI_KEY") or "").strip()
                if not api_key:
                    self._send(502, json.dumps({"error": "missing provider key"}).encode("utf-8"), "application/json; charset=utf-8")
                    return
                _ai_quota_consume(quota_key)
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
        self._run()

    def do_PUT(self):
        self._run()

    def do_POST(self):
        self._run()

    def do_DELETE(self):
        self._run()

    def do_HEAD(self):
        self._run()

    def do_OPTIONS(self):
        self._run()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not _is_demo():
        migrate_legacy()
    print(f"B2First portal at http://0.0.0.0:{PORT} (root={ROOT})")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
