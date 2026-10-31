#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 First study portal — serves the tracker + material (PDF/audio) from the Pi.

Access: http://127.0.0.1:8088 by default (B2_HOST); the public entrypoint is a TLS
proxy in front of it (Tailscale Funnel). LAN access requires B2_HOST=0.0.0.0 and the
nftables firewall remains the real barrier.
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
  POST /api/speaking/report → four-scale speaking report (pronunciation from Azure PA,
                     interactive communication as proxies only)
  GET /api/speaking/capabilities → {live, turn}: which transport this key can run
  POST /api/speaking/turn → one spoken turn: transcript + examiner reply + its audio
  GET /favicon.ico → 204 (does not exist, don't log a 404)

Persistence: progress lives in <repo>/data/progress.json. Each PUT
automatically backs up the previous version in <repo>/data/backups/
(latest wins + backups). Data stays ONLY on this Pi, no auth (private network).

Dependencies: stdlib ONLY (http.server, os, re, html, mimetypes).
Deploy: systemd unit b2first.service (Restart=always) in this dir.
"""
import os, re, html, mimetypes, json, shutil, time, hashlib, hmac, math, secrets, threading, gzip
import base64, binascii
import struct
import calendar
import socket
import urllib.request, urllib.error
import ipaddress
import traceback
from collections import deque
from datetime import date, timedelta
from email.utils import formatdate, parsedate_to_datetime
from urllib.parse import quote, unquote, urlsplit
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import store
import prompts
import plans
import billing
import speech
import speaking_prompts
import speaking_report
import legal

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
TOKEN_ABSOLUTE_TTL = 90 * 24 * 3600                     # hard ceiling: never extended
OWNER_PASSWORD = os.environ.get("B2_OWNER_PASSWORD", "b2first")  # owner password used when migrating
B2_DEMO   = os.environ.get("B2_DEMO", "0").strip() == "1"
B2_REGISTER = (os.environ.get("B2_REGISTER", "open").strip().lower() or "open")
PROGRESS_MAX_BYTES = 2 * 1024 * 1024                    # max size of a progress payload (2 MB)
AI_MAX_BYTES = 32 * 1024                                # max size of an AI request body (32 KB)
B2_PUBLIC_HEALTH = os.environ.get("B2_PUBLIC_HEALTH", "0").strip() == "1"
_START_TS = time.time()                                 # for /api/health uptime_s

# --- Network surface (fase 16) ---------------------------------------------
# Bind address. Defaults to loopback: the public entrypoint is a TLS proxy
# (Tailscale Funnel) talking to 127.0.0.1. LAN access requires B2_HOST=0.0.0.0,
# and even then the nftables firewall is the real barrier, not this bind.
B2_HOST = os.environ.get("B2_HOST", "127.0.0.1")
# Optional comma-separated allowlist of Host headers. Empty = no check.
B2_ALLOWED_HOSTS = os.environ.get("B2_ALLOWED_HOSTS", "")

def _env_int(name, default):
    """Read an integer env var, falling back to `default` when absent or invalid."""
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except (TypeError, ValueError):
        return default


CONNECTION_LIMIT = _env_int("B2_CONNECTION_LIMIT", 512)  # simultaneous sockets (hard cap)
_CONN_SEM = threading.BoundedSemaphore(CONNECTION_LIMIT)
REQUEST_QUEUE_SIZE = _env_int("B2_REQUEST_QUEUE_SIZE", 256)  # listen() backlog
# Disables the static payload cache (compressed bodies + ETag/304). Only for
# measuring the uncached baseline; production always runs with the cache on.
B2_NO_CACHE = (os.environ.get("B2_NO_CACHE") or "").strip() in ("1", "true", "True")
SOCKET_TIMEOUT = 15                                     # seconds (slowloris cut-off)
MAX_URI_LEN = 2048                                      # request-target characters
MAX_HEADERS = 60                                        # request header count
MAX_BODY_BYTES = 3 * 1024 * 1024                        # global request body ceiling
ALLOWED_METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS")
ALLOW_HEADER = ", ".join(ALLOWED_METHODS)


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
AI_TASKS = ("essay", "article", "report", "review", "email")
AI_TEXT_MIN_CHARS = 60
AI_TEXT_MAX_CHARS = 4000
AI_TEXT_HARD_MAX_CHARS = 6000
AI_TEXT_MIN_WORDS = 40
AI_TEXT_MAX_WORDS = 700
AI_OUTPUT_MAX_BYTES = 8 * 1024
AI_TIMEOUT = 25

# --- Phase 30: bring-your-own provider key (writing + speaking report) ------
# The key arrives in X-Provider-Key and lives only in memory for the duration
# of one request: it is never written under data/, never logged, never put in
# the audit chain and never echoed back. Only OpenAI-compatible wire formats
# are supported for BYO keys, so one adapter covers every listed provider.
PROVIDER_TIMEOUT = 20                    # seconds per outbound completion call
PROVIDER_MAX_RESPONSE = 256 * 1024       # max bytes read from the provider
BYO_RATE_PER_HOUR = 120                  # BYO calls per hour per account
BYO_TEST_RATE_PER_MIN = 10               # provider test calls per minute
BYO_KEY_MAX = 512                        # max key characters
BYO_MODEL_MAX = 200                      # max model-id characters
_BYO_MODEL_RE = re.compile(r"^[A-Za-z0-9._:/@+-]{1,%d}$" % BYO_MODEL_MAX)
# Exact operator-controlled origins allowed without the public-https checks
# (self-hosted gateways and the local stubs used by the test suites). Empty by
# default: a client-supplied base can never be trusted on its own.
BYO_TRUSTED_BASES = tuple(
    item.strip().rstrip("/")
    for item in os.environ.get("B2_BYO_TRUSTED_BASES", "").split(",")
    if item.strip()
)

# --- Azure Pronunciation Assessment (S2) -----------------------------------
# The key lives only in the systemd environment, is never sent to the browser,
# never logged and never written to data/. Without it the endpoint degrades to
# 503 speech_not_configured and the Pronunciation band stays "not measured".
SPK_AZURE_KEY = os.environ.get("B2_SPK_AZURE_KEY", "")
SPK_AZURE_REGION = os.environ.get("B2_SPK_AZURE_REGION", "")
SPK_AZURE_ENDPOINT = os.environ.get("B2_SPK_AZURE_ENDPOINT", "")
SPK_PA_PATH = ("/speech/recognition/conversation/cognitiveservices/v1"
               "?language=en-US&format=detailed")
SPK_PA_TIMEOUT = speech.PA_TIMEOUT
SPK_PA_MAX_B64 = 2 * 1024 * 1024     # base64 characters of audio (2 MB)
SPK_PA_MAX_BODY = 2 * 1024 * 1024    # hard body cap for /api/speaking/pa (2 MB)
SPK_PA_RATE_PER_MIN = 30             # calls per minute per user
SPK_PA_DAILY_DEFAULT = 60            # calls per day per user

# --- Gemini Live examiner (S3) ---------------------------------------------
# The Google key only mints short-lived ephemeral tokens: the browser connects
# straight to Google and the Pi never sees a byte of audio. The key itself is
# never sent to the browser, never logged and never written under data/.
# Verified against ai.google.dev/gemini-api/docs/ephemeral-tokens and
# .../docs/live-api/get-started-websocket on 2026-10-30.
SPK_TOKEN_TTL_S = 30 * 60            # expireTime: the session may send for 30 min
SPK_TOKEN_NEW_SESSION_S = 60         # newSessionExpireTime: open it within 1 min
SPK_TOKEN_RATE_PER_MIN = 10          # token mints per minute per user
SPK_MIN_DAILY_DEFAULT = 20           # minutes per user per day
SPK_MIN_DAILY_TOTAL_DEFAULT = 120    # minutes per instance per day
SPK_MINUTE_MAX_BODY = 4096           # POST /api/speaking/minute body cap
SPK_MINUTE_MAX_CALL_S = 300          # max seconds accepted in one report
DEFAULT_SPK_MODEL = "gemini-3.8-live"
DEFAULT_SPK_TOKEN_URL = "https://generativelanguage.googleapis.com/v1beta/auth_tokens"
DEFAULT_SPK_WS_URL = ("wss://generativelanguage.googleapis.com/ws/"
                      "google.ai.generativelanguage.v1beta.GenerativeService"
                      ".BidiGenerateContentConstrained")

# --- S5: four-scale speaking report ----------------------------------------
# One text-model call per report. Pronunciation never comes from here: it is
# mapped from the Azure PA scores (speaking_report.band_from_pa), so the model
# cannot invent it. Interactive Communication stays null with proxies beside it.
SPK_REPORT_RATE_PER_MIN = 6          # reports per minute per user
SPK_REPORT_MAX_BODY = 512 * 1024     # request body cap (transcript + PA words)
SPK_REPORT_CACHE_MAX = 200           # idempotent replays kept in memory
SPK_REPORT_CACHE_TTL = 3600          # seconds a replay stays valid

# --- Phase 36: turn-based voice examiner -----------------------------------
# One round trip per spoken turn: the candidate's audio goes up, the examiner's
# transcript, reply and voice come back. Chosen because the owner's key exposes
# zero models with bidiGenerateContent, so the Live socket stays silent.
# Nothing is stored and no audio or transcript text is ever logged: only
# timings and outcomes reach the audit chain.
SPK_TURN_MAX_S = 25                  # longest accepted candidate turn (seconds)
SPK_TURN_MAX_BYTES = 800 * 1024      # decoded audio cap for one turn
SPK_TURN_MAX_B64 = (SPK_TURN_MAX_BYTES * 4) // 3 + 16
SPK_TURN_MAX_BODY = 1200 * 1024      # body cap, decided before parsing
SPK_TURN_MAX_SAY = 400               # chars a controller line may ask to speak
SPK_TURN_HISTORY_TURNS = 6           # rolling window; never persisted
SPK_TURN_HISTORY_CHARS = 500
SPK_TURN_RATE_PER_MIN = 20           # turns per minute per account
SPK_TURN_TIMEOUT = 20                # seconds per upstream call
SPK_TURN_SESSION_TTL_S = 3 * 3600    # a mock is paid once per session
SPK_TURN_SESSIONS_MAX = 500          # accounts remembered for that window
SPK_TURN_PCM_RATE = 16000            # client wire format: 16 kHz mono 16-bit
SPK_PCM_BYTES_PER_S = SPK_TURN_PCM_RATE * 2
SPK_TTS_RATE = 24000                 # Gemini TTS output: 24 kHz mono 16-bit
DEFAULT_SPK_TURN_MODEL = "gemini-2.5-flash"
DEFAULT_SPK_TTS_MODEL = "gemini-2.5-flash-preview-tts"
SPK_TTS_VOICES = {"examiner": "Puck", "partner": "Kore"}
SPK_TURN_MIMES = ("audio/pcm", "audio/wav", "audio/x-wav", "audio/wave", "audio/l16")
SPK_TTS_CACHE_MAX = 40               # cached scripted lines, LRU by mtime
SPK_WARM_MAX_LINES = 24              # lines one warm request may pre-generate

# --- In-memory rate limiting (stdlib only; the server is a ThreadingHTTPServer) ---
_RATE_LOCK = threading.Lock()
_RATE = {}  # {key: (deque of timestamps, window_s)}
_AI_RATE = _RATE  # tests reset rate state through S._AI_RATE.clear()
_RATE_STATS = {"user": 0, "ip": 0}  # cumulative 429s, exposed by /api/metrics

# Per-user buckets for authenticated API traffic (a shared school/CGNAT IP must
# never rate-limit 50 students as if they were one abuser). Anonymous traffic
# and the credential endpoints stay IP-bucketed.
RATE_USER_API = _env_int("B2_RATE_USER_API", 600)   # requests/min per user
RATE_IP_AUTH = _env_int("B2_RATE_IP_AUTH", 30)      # login+register+password per IP/min
RATE_IP_ANON = _env_int("B2_RATE_IP_ANON", _env_int("B2_RATE_IP_API", 300))
AUTH_RATE_PATHS = ("/api/login", "/api/register", "/api/password")

# Phase 33: Stripe callbacks are capped before a single byte is read. Stripe
# events are small; 64 KB is generous and keeps a hostile upload cheap to refuse.
BILLING_WEBHOOK_MAX_BYTES = 64 * 1024
_BILLING_EVENT_LOCK = threading.Lock()   # idempotency check + apply + record


def _rate_stat(kind):
    """Count one rejected request in the given bucket ("user" or "ip")."""
    with _RATE_LOCK:
        _RATE_STATS[kind] = _RATE_STATS.get(kind, 0) + 1


def rate_stats():
    """Cumulative 429 counts by bucket since process start."""
    with _RATE_LOCK:
        return dict(_RATE_STATS)


def _rate(key, limit, window_s):
    """Sliding-window rate limit: True = allowed, False = over the limit.

    A limit <= 0 disables the bucket (used to measure raw capacity).
    Old entries are pruned on every check, so the store only holds live hits.
    """
    if limit <= 0:
        return True
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
    headers = getattr(handler, "headers", None)
    if headers is not None and _is_trusted_proxy(peer):
        xff = headers.get("X-Forwarded-For")
        if xff:
            cand = xff.split(",")[0].strip()
            if cand:
                return cand
    return peer or "local"


def _client_id(ip):
    """Truncated sha256 of a client address — the only form that may be logged."""
    return hashlib.sha256(str(ip or "").encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Product telemetry (fase 15): privacy-first usage events, NEVER content.
# RULE: whitelisted event names + whitelisted scalar props only. No free
# text, no emails, no names, no tokens, no answers/writings ever land here.
# Events are append-only JSONL in data/events/YYYY-MM-DD.jsonl (0600) with a
# 7-day retention; the client IP is only stored as sha256(ip+salt)[:16].
# ---------------------------------------------------------------------------
EVENT_NAMES = frozenset("""
app_open view_change onboarding_step onboarding_done onboarding_skip
quicklog_open quicklog_save session_save diag_start diag_finish
plan_generate ai_request ai_success ai_error ai_blocked theme_toggle
export_data delete_account login register js_error fetch_error slow_view
""".split())
EVENT_PROPS = frozenset("""
view part kind ms count ok code step theme ver
message_trunc stack_hash status endpoint
""".split())
EVENT_PROP_STR_MAX = 64          # max chars for ordinary string props
EVENT_MSG_MAX = 120              # max chars for js_error message_trunc
EVENTS_MAX_BATCH = 50            # max events per batch (more -> 413)
EVENTS_MAX_BYTES = 32 * 1024     # max request body (more -> 413)
EVENTS_RETENTION_DAYS = 7        # event files older than this are deleted
EVENTS_BATCH_LIMIT = 60          # batches per hour per IP (more -> 429)
_EVENTS_LOCK = threading.Lock()
_EVENTS_SALT_CACHE = None


def _events_dir():
    return os.path.join(DATA_DIR, "events")


def _events_salt():
    """Random salt for IP hashing, persisted in data/.events_salt (0600)."""
    global _EVENTS_SALT_CACHE
    if _EVENTS_SALT_CACHE:
        return _EVENTS_SALT_CACHE
    path = os.path.join(DATA_DIR, ".events_salt")
    salt = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            salt = f.read().strip()
    except OSError:
        pass
    if not salt:
        salt = secrets.token_hex(16)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, salt.encode("utf-8"))
            finally:
                os.close(fd)
            os.chmod(path, 0o600)
        except OSError:
            pass
    _EVENTS_SALT_CACHE = salt
    return salt


def _ip_hash(ip):
    """sha256(ip + salt) truncated to 16 hex chars: the IP is never stored."""
    return hashlib.sha256((str(ip) + _events_salt()).encode("utf-8")).hexdigest()[:16]


def _sanitize_event(ev):
    """Return (n, p) for a valid whitelisted event, else None.

    Unknown names and unknown props are dropped; values must be scalars and
    strings are truncated (64 chars, 120 for message_trunc). Never raises.
    """
    if not isinstance(ev, dict):
        return None
    n = ev.get("n")
    if not isinstance(n, str) or n not in EVENT_NAMES:
        return None
    p = {}
    p_in = ev.get("p")
    if isinstance(p_in, dict):
        for k, v in p_in.items():
            if not isinstance(k, str) or k not in EVENT_PROPS:
                continue
            if isinstance(v, bool):
                p[k] = v
            elif isinstance(v, int):
                p[k] = v
            elif isinstance(v, float):
                if math.isfinite(v):
                    p[k] = v
            elif isinstance(v, str):
                limit = EVENT_MSG_MAX if k == "message_trunc" else EVENT_PROP_STR_MAX
                p[k] = v[:limit]
    return n, p


def _prune_events(events_dir):
    """Delete event files older than the retention window (best-effort)."""
    cutoff = (date.today() - timedelta(days=EVENTS_RETENTION_DAYS)).isoformat()
    try:
        names = os.listdir(events_dir)
    except OSError:
        return
    for fn in names:
        if not fn.endswith(".jsonl"):
            continue
        try:
            if fn[:-6] < cutoff:
                os.remove(os.path.join(events_dir, fn))
        except (OSError, ValueError):
            continue


def _append_events(clean, sid, uid, ip_hash):
    """Append sanitized events to data/events/YYYY-MM-DD.jsonl (0600)."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    day = time.strftime("%Y-%m-%d")
    lines = "".join(
        json.dumps({"ts": ts, "sid": sid, "uid": uid, "n": n, "p": p,
                    "ip_hash": ip_hash}, ensure_ascii=False) + "\n"
        for n, p in clean
    )
    try:
        with _EVENTS_LOCK:
            d = _events_dir()
            os.makedirs(d, mode=0o700, exist_ok=True)
            _prune_events(d)
            path = os.path.join(d, day + ".jsonl")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, lines.encode("utf-8"))
            finally:
                os.close(fd)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
    except OSError:
        pass


def _metrics_window(since_epoch):
    """Aggregate the stored events newer than since_epoch (no personal data)."""
    agg = {"events": {}, "views": {}, "errors": {}, "ai": {
        "requests": 0, "success": 0, "errors": 0, "blocked": 0},
        "sids": set(), "view_ms": []}
    try:
        names = sorted(os.listdir(_events_dir()))
    except OSError:
        names = []
    for fn in names:
        if not fn.endswith(".jsonl"):
            continue
        try:
            f = open(os.path.join(_events_dir(), fn), "r", encoding="utf-8")
        except OSError:
            continue
        with f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    ev = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(ev, dict):
                    continue
                try:
                    t = calendar.timegm(time.strptime(str(ev.get("ts", "")), "%Y-%m-%dT%H:%M:%SZ"))
                except (ValueError, TypeError):
                    continue
                if t < since_epoch:
                    continue
                n = ev.get("n")
                if not isinstance(n, str):
                    continue
                p = ev.get("p") if isinstance(ev.get("p"), dict) else {}
                sid = str(ev.get("sid") or "")
                if sid:
                    agg["sids"].add(sid)
                agg["events"][n] = agg["events"].get(n, 0) + 1
                if n == "view_change":
                    v = p.get("view")
                    if isinstance(v, str) and v:
                        agg["views"][v] = agg["views"].get(v, 0) + 1
                if n in ("js_error", "fetch_error"):
                    rec = agg["errors"].setdefault(
                        n, {"n": n, "count": 0, "last_message_trunc": ""})
                    rec["count"] += 1
                    msg = p.get("message_trunc")
                    if not isinstance(msg, str):
                        msg = "HTTP %s %s" % (p.get("status", "?"), p.get("endpoint", ""))
                    rec["last_message_trunc"] = str(msg)[:EVENT_MSG_MAX]
                if n == "ai_request":
                    agg["ai"]["requests"] += 1
                elif n == "ai_success":
                    agg["ai"]["success"] += 1
                elif n == "ai_error":
                    agg["ai"]["errors"] += 1
                elif n == "ai_blocked":
                    agg["ai"]["blocked"] += 1
                if n in ("view_change", "slow_view"):
                    ms = p.get("ms")
                    if isinstance(ms, (int, float)) and not isinstance(ms, bool) and math.isfinite(ms):
                        agg["view_ms"].append(float(ms))
    return agg


def _p50(values):
    """Median of a list of numbers (0 when empty)."""
    if not values:
        return 0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return int(round(s[mid]))
    return int(round((s[mid - 1] + s[mid]) / 2))


def build_metrics():
    """Aggregate product metrics for the last 24 h and the last 7 days."""
    def pack(agg):
        return {
            "events": agg["events"],
            "errors": sorted(agg["errors"].values(), key=lambda r: -r["count"]),
            "views": agg["views"],
            "ai": agg["ai"],
            "users_active": len(agg["sids"]),
            "p50_view_ms": _p50(agg["view_ms"]),
        }
    now = time.time()
    out = pack(_metrics_window(now - 24 * 3600))
    out["last_7d"] = pack(_metrics_window(now - 7 * 24 * 3600))
    # S3: spoken minutes are the one budget that is not count-based, and minted
    # tokens are the abuse signal. Both read from the persisted per-user ledger.
    minutes, tokens = _spk_metrics_today()
    out["speaking_minutes_today"] = minutes
    out["speaking_tokens_minted"] = tokens
    stats = rate_stats()
    out["rate_limited_by_user"] = stats.get("user", 0)
    out["rate_limited_by_ip"] = stats.get("ip", 0)
    return out


# --- Login brute-force guard: per username, survives IP changes (fase 12) ---
_LOGIN_FAIL_LOCK = threading.Lock()
_LOGIN_FAIL = {}  # {username-lower: {"count": int, "until": ts}}
LOGIN_FAIL_MAX = 5                      # failed attempts before the username is locked
LOGIN_LOCK_S = 15 * 60                  # lockout window (15 minutes)
# Exponential backoff by consecutive failures: #3 → 5 s, #4 → 15 s, #5 → 60 s
# (the 5th also arms the 15-minute lockout). Index = failures - 1.
LOGIN_BACKOFF = (0.0, 0.0, 5.0, 15.0, 60.0)
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
    """Exponential backoff: 0/0/5/15/60 s from the 3rd consecutive failure."""
    return LOGIN_BACKOFF[min(max(count, 1) - 1, len(LOGIN_BACKOFF) - 1)]


# --- Daily AI quota + plans (phase 31) -------------------------------------
# Two meters guard the owner's key:
#   * the per-account allowance comes from the plan (plans.py: free 3/day,
#     pro 60/month, byo unlimited to us); it is persisted in data/usage.json so
#     a restart cannot hand out a fresh quota;
#   * B2_AI_DAILY_TOTAL is the instance-wide daily ceiling, still in memory, so
#     50 pro accounts cannot burn the Pi.
# B2_AI_DAILY_PER_USER survives only as an explicit operator override.
LICENSE_SECRET_MIN = 32
LICENSE_ATTEMPTS_PER_HOUR = 5
_AI_QUOTA_LOCK = threading.Lock()
_AI_QUOTA = {}  # {date iso: {"total": int, "users": {ip key: int}}}


def _license_secret():
    """B2_LICENSE_SECRET when usable, else "". Read per call (tests inject it)."""
    value = (os.environ.get("B2_LICENSE_SECRET") or "").strip()
    return value if len(value) >= LICENSE_SECRET_MIN else ""


def _plan_for(uid, byo=False):
    """The one place that answers 'what may this account do right now'."""
    return plans.effective_plan(uid, byo=byo)


# --- Billing events (phase 33) ---------------------------------------------
# A verified Stripe event is reduced to the handful of ids and statuses this
# server understands. Nothing from the payload beyond those fields is copied
# to disk, so a body that carried card data could not persist it.
def _billing_object(event):
    """The `data.object` of an event, or {} when the shape is unexpected."""
    data = event.get("data") if isinstance(event, dict) else None
    obj = data.get("object") if isinstance(data, dict) else None
    return obj if isinstance(obj, dict) else {}


def _billing_user_for(obj):
    """Resolve the account an event belongs to (client ref, sub id, customer)."""
    ref = obj.get("client_reference_id")
    if isinstance(ref, str) and ref:
        return ref
    metadata = obj.get("metadata")
    if isinstance(metadata, dict):
        stamped = metadata.get("user_id")
        if isinstance(stamped, str) and stamped:
            return stamped
    for value in (obj.get("subscription"), obj.get("id")):
        if isinstance(value, str) and value.startswith("sub_"):
            uid, _row = billing.find_by_subscription(value)
            if uid:
                return uid
    customer = obj.get("customer")
    if isinstance(customer, str) and customer:
        uid, _row = billing.find_by_customer(customer)
        if uid:
            return uid
    return ""


def _billing_iso(value):
    """ISO timestamp for a Stripe epoch value, or None."""
    stamp = billing.epoch(value)
    return billing.iso(stamp) if stamp is not None else None


def _apply_billing_event(event, now=None):
    """Apply one verified event; returns (type, uid, applied).

    Only the documented types are handled. The row written is built from
    allow-listed fields (ids, status, period end, grace) — never the payload.
    """
    kind = event.get("type") if isinstance(event, dict) else ""
    if not isinstance(kind, str) or not kind:
        return "", "", False
    obj = _billing_object(event)
    ts = time.time() if now is None else float(now)
    uid = _billing_user_for(obj)
    if not uid:
        return kind, "", False
    row = billing.get_sub(uid)

    if kind == "checkout.session.completed":
        new = dict(row)
        customer = obj.get("customer")
        sub = obj.get("subscription")
        if isinstance(customer, str) and customer:
            new["customer_id"] = customer
        if isinstance(sub, str) and sub:
            new["subscription_id"] = sub
        # Only the ids are trusted here: the period end arrives with
        # `customer.subscription.*`, and granting pro before it is known could
        # leave an account paid forever if that event never lands.
        new.setdefault("status", "pending")
        new.setdefault("since", billing.iso(ts))
        billing.put_sub(uid, new)
        return kind, uid, True

    if kind in ("customer.subscription.updated",
                "customer.subscription.deleted"):
        status = obj.get("status")
        if kind.endswith("deleted"):
            status = "canceled"
        if not isinstance(status, str) or not status:
            status = "active"
        end = _billing_iso(obj.get("current_period_end"))
        new = dict(row)
        customer = obj.get("customer")
        sub = obj.get("id")
        if isinstance(customer, str) and customer:
            new["customer_id"] = customer
        if isinstance(sub, str) and sub:
            new["subscription_id"] = sub
        new["status"] = status
        if end:
            new["current_period_end"] = end
        new["plan"] = billing.plan_from_subscription(status, end, ts)
        if new["plan"] == "pro" and status in ("active", "trialing"):
            new.pop("grace_until", None)
        new.setdefault("since", billing.iso(ts))
        billing.put_sub(uid, new)
        return kind, uid, True

    if kind == "invoice.payment_failed":
        new = dict(row)
        customer = obj.get("customer")
        sub = obj.get("subscription")
        if isinstance(customer, str) and customer:
            new["customer_id"] = customer
        if isinstance(sub, str) and sub:
            new["subscription_id"] = sub
        new["status"] = "past_due"
        new["plan"] = "pro"
        new["grace_until"] = billing.iso(ts + billing.GRACE_DAYS * 86400)
        new.setdefault("since", billing.iso(ts))
        billing.put_sub(uid, new)
        return kind, uid, True

    return kind, uid, False


def _apply_billing_event_once(event):
    """Idempotent wrapper: (type, uid, applied, duplicate), serialized.

    The check, the apply and the ledger write happen under one lock, so two
    concurrent deliveries of the same event id cannot both grant time.
    """
    event_id = event.get("id") if isinstance(event, dict) else ""
    with _BILLING_EVENT_LOCK:
        if isinstance(event_id, str) and event_id and billing.event_seen(event_id):
            return "", "", False, True
        kind, uid, applied = _apply_billing_event(event)
        if isinstance(event_id, str) and event_id:
            billing.record_event(event_id)
        return kind, uid, applied, False


def _legacy_per_user_cap():
    """B2_AI_DAILY_PER_USER when the operator set it explicitly, else None.

    New deployments leave it unset and rely on the plans. It is kept because
    older units (and a few test suites) use it as an emergency hard cap.
    """
    raw = os.environ.get("B2_AI_DAILY_PER_USER")
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _ai_quota_limits():
    """(legacy per-account cap or None, instance-wide daily total)."""
    def _int(name, default):
        try:
            return max(0, int(os.environ.get(name, str(default))))
        except ValueError:
            return default
    return _legacy_per_user_cap(), _int("B2_AI_DAILY_TOTAL", 80)


def _ai_quota_today():
    """Today's counter (auto-reset: previous days are dropped on access)."""
    today = date.today().isoformat()
    for k in list(_AI_QUOTA):
        if k != today:
            del _AI_QUOTA[k]
    return _AI_QUOTA.setdefault(today, {"total": 0, "users": {}})


def _ai_total_left():
    """Calls left today for the whole instance."""
    _legacy, total = _ai_quota_limits()
    with _AI_QUOTA_LOCK:
        return total - _ai_quota_today()["total"]


def _ai_total_consume():
    with _AI_QUOTA_LOCK:
        _ai_quota_today()["total"] += 1


def _ai_quota_left(quota_key):
    """Anonymous (per-IP) calls left today; the free allowance unless overridden."""
    legacy, _total = _ai_quota_limits()
    cap = legacy if legacy is not None else plans.LIMITS["free"]["writing"]["limit"]
    with _AI_QUOTA_LOCK:
        day = _ai_quota_today()
        return max(0, cap - day["users"].get(quota_key, 0))


def _ai_quota_consume(quota_key):
    with _AI_QUOTA_LOCK:
        day = _ai_quota_today()
        day["users"][quota_key] = day["users"].get(quota_key, 0) + 1
        day["total"] += 1


def _ai_left_for(uid):
    """LLM calls left for an account in its current window (GET /api/account)."""
    legacy = _legacy_per_user_cap()
    if legacy is not None:
        return max(0, legacy - plans.writing_used(uid, "day"))
    limits = _plan_for(uid)["limits"]["writing"]
    if limits is None:
        return 1000000  # byo: the user's key pays, we do not meter it
    return max(0, limits["limit"] - plans.writing_used(uid, limits["window"]))


# --- Daily PA quota (same shape as the AI quota; protects the Azure key) ---
_SPK_QUOTA_LOCK = threading.Lock()
_SPK_QUOTA = {}  # {date iso: {quota_key: int}}


def _spk_pa_daily_limit():
    """Daily PA calls per user (B2_SPK_PA_DAILY_PER_USER, default 60)."""
    try:
        return max(0, int(os.environ.get("B2_SPK_PA_DAILY_PER_USER",
                                         str(SPK_PA_DAILY_DEFAULT))))
    except ValueError:
        return SPK_PA_DAILY_DEFAULT


def _spk_pa_quota_today():
    """Today's counter (auto-reset: previous days are dropped on access)."""
    today = date.today().isoformat()
    for k in list(_SPK_QUOTA):
        if k != today:
            del _SPK_QUOTA[k]
    return _SPK_QUOTA.setdefault(today, {})


def _spk_pa_quota_left(quota_key):
    with _SPK_QUOTA_LOCK:
        return _spk_pa_daily_limit() - _spk_pa_quota_today().get(quota_key, 0)


def _spk_pa_quota_consume(quota_key):
    with _SPK_QUOTA_LOCK:
        day = _spk_pa_quota_today()
        day[quota_key] = day.get(quota_key, 0) + 1


def _spk_azure_key():
    """Azure subscription key from env (module constant first, then os.environ)."""
    value = SPK_AZURE_KEY or os.environ.get("B2_SPK_AZURE_KEY", "")
    return value.strip() if isinstance(value, str) else ""


def _spk_pa_url():
    """Recognition URL: B2_SPK_AZURE_ENDPOINT override, else the regional host."""
    endpoint = SPK_AZURE_ENDPOINT or os.environ.get("B2_SPK_AZURE_ENDPOINT", "")
    endpoint = endpoint.strip().rstrip("/") if isinstance(endpoint, str) else ""
    if endpoint:
        return endpoint if "speech/recognition" in endpoint else endpoint + SPK_PA_PATH
    region = SPK_AZURE_REGION or os.environ.get("B2_SPK_AZURE_REGION", "")
    region = region.strip() if isinstance(region, str) else ""
    if not region:
        return ""
    return f"https://{region}.stt.speech.microsoft.com{SPK_PA_PATH}"


# --- Gemini Live: token minting + speaking-minute budget (S3) --------------
def _spk_google_key():
    """Google API key from env only (never from the module constant cache)."""
    value = os.environ.get("B2_SPK_GOOGLE_KEY", "")
    return value.strip() if isinstance(value, str) else ""


def _spk_model():
    value = os.environ.get("B2_SPK_GOOGLE_MODEL", DEFAULT_SPK_MODEL)
    value = value.strip() if isinstance(value, str) else ""
    return value or DEFAULT_SPK_MODEL


def _spk_token_url():
    """Token provisioning URL (B2_SPK_GOOGLE_TOKEN_URL overrides it for tests)."""
    value = os.environ.get("B2_SPK_GOOGLE_TOKEN_URL", DEFAULT_SPK_TOKEN_URL)
    value = value.strip() if isinstance(value, str) else ""
    return value or DEFAULT_SPK_TOKEN_URL


def _spk_ws_url():
    """WSS endpoint the browser connects to (no token in it)."""
    value = os.environ.get("B2_SPK_WS_URL", DEFAULT_SPK_WS_URL)
    value = value.strip() if isinstance(value, str) else ""
    return value or DEFAULT_SPK_WS_URL


def _spk_iso_after(seconds):
    """UTC ISO-8601 timestamp `seconds` in the future, e.g. ...Z."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds))


def _spk_mint_token(api_key):
    """Mint a single-use ephemeral token. Return (token, error).

    Contract verified against ai.google.dev/gemini-api/docs/ephemeral-tokens:
    POST /v1beta/auth_tokens with `uses`, `expireTime` and
    `newSessionExpireTime`; the token is the `name` field of the response.
    """
    body = json.dumps({
        "uses": 1,
        "expireTime": _spk_iso_after(SPK_TOKEN_TTL_S),
        "newSessionExpireTime": _spk_iso_after(SPK_TOKEN_NEW_SESSION_S),
    }).encode("utf-8")
    req = urllib.request.Request(
        _spk_token_url(),
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(64 * 1024)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None, "upstream_failed"
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "invalid_upstream"
    token = obj.get("name") if isinstance(obj, dict) else None
    if not isinstance(token, str) or not token.strip():
        return None, "invalid_upstream"
    return token.strip(), None


def _spk_min_limits():
    """(minutes per user, minutes for the instance) for today."""
    def _int(name, default):
        try:
            return max(0, int(os.environ.get(name, str(default))))
        except ValueError:
            return default
    return (_int("B2_SPK_MIN_DAILY_PER_USER", SPK_MIN_DAILY_DEFAULT),
            _int("B2_SPK_MIN_DAILY_TOTAL", SPK_MIN_DAILY_TOTAL_DEFAULT))


def _spk_today():
    return date.today().isoformat()


def _spk_remaining_s(uid):
    """Seconds left today, the stricter of the per-user and instance budgets."""
    per_user_min, total_min = _spk_min_limits()
    rec = store.speaking_read(uid, _spk_today())
    total_used = sum(store.speaking_read(other, _spk_today())["seconds"]
                     for other in store.list_users())
    remaining = min(per_user_min * 60 - rec["seconds"],
                    total_min * 60 - total_used)
    return max(0, int(remaining))


def _spk_metrics_today():
    """(minutes spoken today across users, tokens minted today)."""
    today = _spk_today()
    seconds = 0.0
    tokens = 0
    for uid in store.list_users():
        rec = store.speaking_read(uid, today)
        seconds += rec["seconds"]
        tokens += rec["tokens_minted"]
    return round(seconds / 60.0, 1), tokens


# --- Phase 36: turn-based voice — helpers ----------------------------------
def _spk_turn_base():
    """Gemini API base for the turn path (B2_SPK_TURN_BASE overrides it)."""
    value = os.environ.get("B2_SPK_TURN_BASE", DEFAULT_GEMINI_BASE)
    value = value.strip().rstrip("/") if isinstance(value, str) else ""
    return value or DEFAULT_GEMINI_BASE


def _spk_turn_model():
    value = os.environ.get("B2_SPK_TURN_MODEL", DEFAULT_SPK_TURN_MODEL)
    value = value.strip() if isinstance(value, str) else ""
    return value or DEFAULT_SPK_TURN_MODEL


def _spk_tts_model():
    value = os.environ.get("B2_SPK_TTS_MODEL", DEFAULT_SPK_TTS_MODEL)
    value = value.strip() if isinstance(value, str) else ""
    return value or DEFAULT_SPK_TTS_MODEL


def _spk_live_enabled():
    """The operator says this key can run Live (B2_SPK_LIVE=1)."""
    raw = os.environ.get("B2_SPK_LIVE", "")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


_SPK_LIVE_LOCK = threading.Lock()
_SPK_LIVE_CACHE = {"at": 0.0, "model": "", "ok": False}
SPK_LIVE_PROBE_TTL = 600


def _spk_model_has_live(api_key, model):
    """True only when `model` lists bidiGenerateContent. Cached, fails closed."""
    now = time.time()
    with _SPK_LIVE_LOCK:
        if (_SPK_LIVE_CACHE["at"] and _SPK_LIVE_CACHE["model"] == model
                and now - _SPK_LIVE_CACHE["at"] < SPK_LIVE_PROBE_TTL):
            return _SPK_LIVE_CACHE["ok"]
    ok = False
    try:
        req = urllib.request.Request(
            _spk_turn_base() + "/models",
            headers={"x-goog-api-key": api_key},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read(256 * 1024)
        body = json.loads(raw.decode("utf-8"))
        for item in (body.get("models") if isinstance(body, dict) else []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").split("/")[-1]
            methods = item.get("supportedGenerationMethods") or []
            if name == model and "bidiGenerateContent" in methods:
                ok = True
                break
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, ValueError, UnicodeDecodeError):
        ok = False
    with _SPK_LIVE_LOCK:
        _SPK_LIVE_CACHE.update({"at": now, "model": model, "ok": ok})
    return ok


def _spk_live_available():
    """`live:true` needs the operator's flag AND a model that really offers it."""
    if not _spk_live_enabled():
        return False
    api_key = _spk_google_key()
    if not api_key:
        return False
    return _spk_model_has_live(api_key, _spk_model())


_SPK_TURN_LOCK = threading.Lock()
_SPK_TURN_SESSIONS = {}   # {uid: {session_id: first_seen}}


def _spk_turn_session_known(uid, session_id):
    """Has this account already opened (and paid for) this exam session?"""
    if not session_id:
        return False
    now = time.time()
    with _SPK_TURN_LOCK:
        seen = _SPK_TURN_SESSIONS.setdefault(uid, {})
        for sid, stamp in list(seen.items()):
            if now - stamp > SPK_TURN_SESSION_TTL_S:
                seen.pop(sid, None)
        return session_id in seen


def _spk_turn_session_mark(uid, session_id):
    """Remember a session after its first successful turn (mock already paid)."""
    if not session_id:
        return
    with _SPK_TURN_LOCK:
        _SPK_TURN_SESSIONS.setdefault(uid, {})[session_id] = time.time()
        while len(_SPK_TURN_SESSIONS) > SPK_TURN_SESSIONS_MAX:
            _SPK_TURN_SESSIONS.pop(next(iter(_SPK_TURN_SESSIONS)))


def _spk_turn_sessions_clear():
    """Test hook: forget every metered session."""
    with _SPK_TURN_LOCK:
        _SPK_TURN_SESSIONS.clear()


def _spk_wav_bytes(pcm, rate=SPK_TTS_RATE):
    """Wrap mono 16-bit PCM in a RIFF/WAVE container `decodeAudioData` accepts."""
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1,
        rate, rate * 2, 2, 16, b"data", len(pcm),
    ) + pcm


def _spk_gemini_text(body):
    """Join the text parts of a Gemini response, or None when there are none."""
    try:
        parts = body["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    chunks = [p.get("text") for p in parts
              if isinstance(p, dict) and isinstance(p.get("text"), str)]
    text = "".join(chunks)
    return text or None


_SPK_TURN_REPEAT = "Sorry, I did not catch that. Could you say it again, please?"

_SPK_TURN_RULE = """
VOICE LINE, TURN BY TURN
These rules override the part block above wherever they disagree.
- The candidate's audio is ONE turn. Transcribe it verbatim in `transcript`
  (English, no timestamps, no speaker labels). If there is no clear speech,
  use "" — NEVER guess, complete or invent words.
- Then write your own next turn in `reply`: exactly the words you say out loud,
  in English. Your reply is AT MOST 10 words (6-9 is ideal) — a long line costs seconds of speech. The exam rules
  above still apply, except that this turn is a conversation, not a reading of
  the question list.
- REACT FIRST. Your reply must contain at least one concrete word or phrase
  from `transcript` and show that you heard it. Example: candidate says
  "I go by bike because it is healthier" → "Bike — why is it healthier for you?"
- If the transcript is empty: do not invent an answer. Say you could not hear
  the audio and ask the candidate to repeat it, in 10 words or fewer.
- If the transcript has fewer than 4 words or is off-topic: ask a short
  follow-up ("Why?" / "Can you tell me more about X?") using a word they said.
  Do NOT advance to the next scripted question.
- Only when the answer is on-topic and at least 4 words long may you move to
  the next scripted question — and even then, refer to what they said first.
- The scripted question list is a FALLBACK for silence, not a script to read.
  Never ask a question that could have been asked without listening.
- Never describe the audio, never mention transcription, never add JSON prose.
Return only the JSON object.
"""

_SPK_TURN_SCHEMA = {
    "type": "object",
    "properties": {"transcript": {"type": "string"}, "reply": {"type": "string"}},
    "required": ["transcript", "reply"],
}


def _spk_turn_instruction(role, part, task):
    """The same role prompt the Live socket would have used, plus the JSON rule."""
    base = (speaking_prompts.partner_instruction(part or 1, task)
            if role == "partner"
            else speaking_prompts.examiner_instruction(part or 1, task))
    return base + _SPK_TURN_RULE


def _spk_turn_history(raw):
    """Sanitise the rolling history: last 6 turns, known speakers, capped text."""
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw[-SPK_TURN_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            continue
        who, text = item.get("who"), item.get("text")
        if who not in ("candidate", "examiner", "partner"):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        out.append({"who": who, "text": text.strip()[:SPK_TURN_HISTORY_CHARS]})
    return out


_SPK_TURN_WHO = {"candidate": "Candidate", "partner": "Candidate B",
                 "examiner": "Examiner"}


def _spk_turn_contents(history):
    """History as Gemini `contents`, each turn labelled with who said it.

    Labels matter: the reply must react to the candidate, not to its own
    previous line. Consecutive same-role turns are merged.
    """
    contents = []
    for turn in history:
        role = "model" if turn["who"] == "examiner" else "user"
        text = "{}: {}".format(_SPK_TURN_WHO.get(turn["who"], "Candidate"),
                               turn["text"])
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].append({"text": text})
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    return contents


def _spk_turn_understand(api_key, system, history, audio_b64, mime):
    """One Gemini call: transcribe the candidate's audio AND write the reply.

    Returns ``(transcript, reply, ms, error)``. One call instead of two is what
    keeps the stop-talking → first-audio latency inside the target; `ms` is the
    whole call, so the response reports stt as 0 and the cost under llm.
    """
    contents = _spk_turn_contents(history)
    spoken = [
        {"inlineData": {"mimeType": mime, "data": audio_b64}},
        {"text": "That was the candidate's spoken turn. Return the JSON object."},
    ]
    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"].extend(spoken)   # one user turn, not two in a row
    else:
        contents.append({"role": "user", "parts": spoken})
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
            # The reply is 8-14 words: thinking adds ~2 s and buys nothing.
            "maxOutputTokens": 60,
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseSchema": _SPK_TURN_SCHEMA,
        },
    }
    started = time.time()
    body, error = _provider_complete(_spk_turn_base(), api_key, _spk_turn_model(),
                                     payload, wire="gemini",
                                     timeout=SPK_TURN_TIMEOUT)
    ms = int((time.time() - started) * 1000)
    if error:
        return None, None, ms, error
    text = _spk_gemini_text(body)
    if text is None:
        return None, None, ms, "upstream_failed"
    try:
        obj = json.loads(text)
    except ValueError:
        return None, None, ms, "upstream_failed"
    if not isinstance(obj, dict):
        return None, None, ms, "upstream_failed"
    transcript, reply = obj.get("transcript"), obj.get("reply")
    if not isinstance(transcript, str) or not isinstance(reply, str) or not reply.strip():
        return None, None, ms, "upstream_failed"
    return transcript.strip()[:2000], reply.strip()[:900], ms, None


def _spk_tts(api_key, text, voice):
    """One TTS call. Returns ``(wav_bytes, ms, error)``; PCM is wrapped as WAV."""
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    started = time.time()
    body, error = _provider_complete(_spk_turn_base(), api_key, _spk_tts_model(),
                                     payload, wire="gemini",
                                     timeout=SPK_TURN_TIMEOUT,
                                     max_bytes=4 * 1024 * 1024)
    ms = int((time.time() - started) * 1000)
    if error:
        return None, ms, error
    data = None
    try:
        parts = body["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        parts = []
    for part in parts if isinstance(parts, list) else []:
        if not isinstance(part, dict):
            continue
        blob = part.get("inlineData")
        if isinstance(blob, dict) and isinstance(blob.get("data"), str):
            data = blob["data"]
            break
    if not data:
        return None, ms, "upstream_failed"
    try:
        pcm = base64.b64decode(data, validate=False)
    except (ValueError, binascii.Error):
        return None, ms, "upstream_failed"
    if not pcm:
        return None, ms, "upstream_failed"
    return _spk_wav_bytes(pcm), ms, None


# --- Phase 37: TTS cache for the scripted lines -----------------------------
# The scripted lines never change between sessions, so paying 0.3 s + audio
# duration for each one on every turn is waste. They are cached by the sha256
# of (text, voice): the filename carries no text, the bytes are WAV only. The
# cache is the ONLY thing this feature writes under data/, and it is LRU-capped.
_SPK_TTS_LOCK = threading.Lock()
_SPK_WARM_LOCK = threading.Lock()
_SPK_WARM_INFLIGHT = set()


def _spk_tts_dir():
    return os.path.join(DATA_DIR, "tts")


def _spk_tts_cache_path(text, voice):
    digest = hashlib.sha256((text + "\x00" + voice).encode("utf-8")).hexdigest()
    return os.path.join(_spk_tts_dir(), digest + ".wav")


def _spk_tts_cache_get(text, voice):
    """Cached WAV for (text, voice) or None. A hit refreshes the LRU stamp."""
    path = _spk_tts_cache_path(text, voice)
    try:
        with open(path, "rb") as fh:
            data = fh.read(4 * 1024 * 1024 + 1)
        if not data or len(data) > 4 * 1024 * 1024:
            return None
        os.utime(path, None)
        return data
    except OSError:
        return None


def _spk_tts_cache_prune():
    """Keep the newest SPK_TTS_CACHE_MAX .wav files, drop the rest."""
    try:
        entries = [(entry.stat().st_mtime, entry.path)
                   for entry in os.scandir(_spk_tts_dir())
                   if entry.is_file() and entry.name.endswith(".wav")]
    except OSError:
        return
    entries.sort()
    for _mtime, path in entries[:-SPK_TTS_CACHE_MAX]:
        try:
            os.remove(path)
        except OSError:
            pass


def _spk_tts_cache_put(text, voice, wav):
    """Write a WAV as 0600, atomically, and prune the cache to its cap."""
    directory = _spk_tts_dir()
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass
        tmp = os.path.join(directory, ".tmp-" + secrets.token_hex(8))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(wav)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        os.replace(tmp, _spk_tts_cache_path(text, voice))
        try:
            os.chmod(_spk_tts_cache_path(text, voice), 0o600)
        except OSError:
            pass
        _spk_tts_cache_prune()
    except OSError:
        return


def _spk_tts_cached(api_key, text, voice):
    """``(wav, ms, cached, error)``: cache first, upstream TTS on a miss."""
    started = time.time()
    with _SPK_TTS_LOCK:
        cached = _spk_tts_cache_get(text, voice)
    if cached is not None:
        return cached, int((time.time() - started) * 1000), True, None
    wav, ms, error = _spk_tts(api_key, text, voice)
    if error:
        return None, ms, False, error
    # One paid upstream call, one tick of the instance meter. A cache hit above
    # returns before this line, so it costs nothing.
    _ai_total_consume()
    with _SPK_TTS_LOCK:
        _spk_tts_cache_put(text, voice, wav)
    return wav, ms, False, None


def _spk_warm_lines(raw):
    """Sanitise the scripted lines a client asks to pre-generate."""
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for item in raw[:SPK_WARM_MAX_LINES]:
        if not isinstance(item, str):
            continue
        text = item.strip()[:SPK_TURN_MAX_SAY]
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _spk_warm_async(api_key, lines, voice):
    """Generate the missing scripted lines in the background; return queued N."""
    lines = [line for line in lines if isinstance(line, str) and line.strip()]
    if not lines:
        return 0
    key = (voice, tuple(lines))
    with _SPK_WARM_LOCK:
        if key in _SPK_WARM_INFLIGHT:
            return 0
        _SPK_WARM_INFLIGHT.add(key)

    def run():
        try:
            for line in lines:
                try:
                    _spk_tts_cached(api_key, line.strip(), voice)
                except Exception:
                    pass
        finally:
            with _SPK_WARM_LOCK:
                _SPK_WARM_INFLIGHT.discard(key)

    threading.Thread(target=run, name="spk-tts-warm", daemon=True).start()
    return len(lines)


# --- S5 report idempotency: a retry must not buy a second LLM call ----------
_SPK_REPORT_LOCK = threading.Lock()
_SPK_REPORT_CACHE = {}   # {(uid, request_id): (timestamp, result)}


def _spk_report_cache_get(uid, request_id):
    """A previous successful report for this (user, request_id), or None."""
    if not request_id:
        return None
    now = time.time()
    with _SPK_REPORT_LOCK:
        for key, (stamp, _result) in list(_SPK_REPORT_CACHE.items()):
            if now - stamp > SPK_REPORT_CACHE_TTL:
                _SPK_REPORT_CACHE.pop(key, None)
        hit = _SPK_REPORT_CACHE.get((uid, request_id))
        return hit[1] if hit else None


def _spk_report_cache_put(uid, request_id, result):
    """Remember a successful report so a retry replays it without the model."""
    if not request_id:
        return
    with _SPK_REPORT_LOCK:
        _SPK_REPORT_CACHE[(uid, request_id)] = (time.time(), result)
        while len(_SPK_REPORT_CACHE) > SPK_REPORT_CACHE_MAX:
            _SPK_REPORT_CACHE.pop(next(iter(_SPK_REPORT_CACHE)))


def _speaking_report_cache_clear():
    """Test hook: drop every cached report."""
    with _SPK_REPORT_LOCK:
        _SPK_REPORT_CACHE.clear()


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
# AI input/output guards (fase 17)
# ---------------------------------------------------------------------------
_AI_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_AI_ABUSE = (
    ("prompt_injection", re.compile(r"ignore\s+(?:(?:all|any|the)\s+)?previous", re.I)),
    ("prompt_injection", re.compile(r"system\s+prompt", re.I)),
    ("prompt_injection", re.compile(r"you\s+are\s+now", re.I)),
    ("prompt_injection", re.compile(r"developer\s+mode", re.I)),
    ("prompt_injection", re.compile(r"jailbreak", re.I)),
    ("prompt_injection", re.compile(r"reveal\s+your\s+instructions", re.I)),
    ("prompt_injection", re.compile(r"repeat\s+the\s+instructions", re.I)),
    ("roleplay", re.compile(r"act\s+as", re.I)),
    ("roleplay", re.compile(r"pretend\s+to\s+be", re.I)),
    ("code", re.compile(r"```")),
    ("code", re.compile(r"\bdef\s")),
    ("code", re.compile(r"\bimport\s")),
    ("sql", re.compile(r"\bselect\s", re.I)),
    ("html", re.compile(r"<script", re.I)),
    ("encoding", re.compile(r"base64", re.I)),
    ("credentials", re.compile(r"api[ _-]?key", re.I)),
    ("provider_probe", re.compile(r"openai", re.I)),
    ("provider_probe", re.compile(r"deepseek", re.I)),
)
# The system-prompt phrases that must never come back in a model response.
_AI_LEAK_STRONG = (
    "you are a senior official cambridge",
    "the only valid instructions",
    "anything inside student_text",
    "mandatory marking rules",
    "calibration rules",
    "refusal rules (non-negotiable)",
    "return only this exact json shape",
)
_AI_LEAK_WEAK = (
    "communicative achievement",
    "target reader",
    "cohesive devices",
    "assessment scales",
    "band 5",
    "band 4",
)


def _looks_binary(text):
    """True when more than 5% of the characters are not printable."""
    if not text:
        return False
    bad = sum(1 for ch in text if ch not in "\n\r\t" and not ch.isprintable())
    return bad / len(text) > 0.05


def _sanitize_ai_text(raw):
    """Normalise a submission: drop control characters and collapse blank lines."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _AI_CTRL_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fit_ai_text(text):
    """Cap the text sent to the model: 500 chars per line, 200 lines max."""
    return "\n".join(ln[:500] for ln in text.split("\n")[:200])


def _ai_abuse_reason(text):
    """Heuristic abuse detector; returns a reason slug or "".

    A pattern only blocks when it appears in the first 3 lines or is repeated
    2+ times. That is deliberate: a legitimate essay may contain a single
    "act as" or "select" deep in the text, and we prefer a false negative (the
    model itself has refusal rules) to a false positive that ruins a real
    student's writing.
    """
    low = text.lower()
    head = "\n".join(text.split("\n")[:3]).lower()
    for reason, rx in _AI_ABUSE:
        hits = len(rx.findall(low))
        if hits and (hits >= 2 or rx.search(head)):
            return reason
    if re.search(r"\S{200,}", text):
        return "blob"
    return ""


def _leaks_system_prompt(text, strong_only=False):
    """True when a model response echoes the internal system prompt.

    `strong_only` is used by the speaking report: its fixes legitimately talk
    about "band 4", "band 5" or "cohesive devices", so the weak (Writing
    rubric) markers would reject honest output. The strong markers cover the
    speaking prompt as well, so the leak guard is not weakened.
    """
    low = text.lower()
    if any(marker in low for marker in _AI_LEAK_STRONG):
        return True
    if strong_only:
        return False
    return sum(1 for marker in _AI_LEAK_WEAK if marker in low) >= 3


def _word_count(text):
    """Words as a human counts them: whitespace tokens carrying a letter or digit.

    A lone em dash or "&" is punctuation, not a word. The client mirror is
    countWords() in index.html; the two must agree or a text can be rejected
    after the UI said it was inside the range.
    """
    return sum(1 for tok in text.split() if any(ch.isalnum() for ch in tok))


# ---------------------------------------------------------------------------
# Phase 30: BYO provider plumbing
# ---------------------------------------------------------------------------
def _validate_provider_base(raw):
    """Return a normalised https base or None.

    Refusing everything that is not a public https origin is what keeps this
    header from becoming an SSRF gadget: no plain http, no IP literal, no
    localhost, no private/link-local/reserved address and no port other than
    443. Hostnames are resolved once and every answer must be public.
    """
    text = (raw or "").strip().rstrip("/")
    if not text or len(text) > 300:
        return None
    if text in BYO_TRUSTED_BASES:
        return text
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password:
        return None
    if port not in (None, 443) or parts.query or parts.fragment:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or "." not in host or host == "localhost" or host.endswith(".localhost"):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return None
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return None
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return None
    path = parts.path.rstrip("/")
    return "https://" + host + path


def _byo_from_headers(headers):
    """Parse the optional X-Provider-* headers.

    Returns ``(byo, error)`` where ``byo`` is ``{key, base, model}`` or None.
    No key means "use the owner's key and quota". Error slugs never contain
    the submitted value: the caller answers 400 with the slug only.
    """
    key = (headers.get("X-Provider-Key") or "").strip()
    if not key:
        return None, None
    if len(key) > BYO_KEY_MAX or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in key):
        return None, "invalid_provider_key"
    model = (headers.get("X-Provider-Model") or "").strip()
    if model and not _BYO_MODEL_RE.match(model):
        return None, "invalid_provider_model"
    if not model:
        model = DEFAULT_DEEPSEEK_MODEL
    raw_base = (headers.get("X-Provider-Base") or "").strip()
    if raw_base:
        base = _validate_provider_base(raw_base)
        if not base:
            return None, "invalid_provider_base"
    else:
        base = DEFAULT_DEEPSEEK_BASE
    return {"key": key, "base": base, "model": model}, None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turn every 3xx into an HTTPError instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _provider_complete(base, key, model, payload, wire="openai",
                       timeout=PROVIDER_TIMEOUT,
                       max_bytes=PROVIDER_MAX_RESPONSE):
    """One outbound completion request shared by the owner and BYO paths.

    Returns ``(parsed_body, error)``. The key is used only in the request
    headers: it is never logged, stored or returned. Redirects are refused,
    the read is capped and the timeout is fixed, so a hostile endpoint cannot
    turn this into an unbounded request.
    """
    if wire == "gemini":
        url = base.rstrip("/") + "/models/" + model + ":generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    else:
        url = base.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json",
                   "Authorization": "Bearer " + key}
    try:
        data = json.dumps(payload).encode("utf-8")
    except (TypeError, ValueError):
        return None, "bad_payload"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, ValueError):
        return None, "upstream_failed"
    if len(raw) > max_bytes:
        return None, "upstream_failed"
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "upstream_failed"
    if not isinstance(body, dict):
        return None, "upstream_failed"
    return body, None


def _ai_text_complete(system, user_block, byo=None):
    """One text-model call for the speaking report.

    With ``byo`` the call runs on the user's own key and base (OpenAI wire);
    without it, on the owner's key (DeepSeek or Gemini) and quota. Returns
    ``(content, error)``; the raw provider body is never returned, echoed or
    logged.
    """
    if byo:
        api_key, base, model, wire = byo["key"], byo["base"], byo["model"], "openai"
    else:
        api_key = (os.environ.get("B2_AI_KEY") or "").strip()
        if not api_key:
            return None, "ai_not_configured"
        env_provider = (B2_AI_PROVIDER if B2_AI_PROVIDER != DEFAULT_AI_PROVIDER
                        else os.environ.get("B2_AI_PROVIDER", DEFAULT_AI_PROVIDER))
        wire = (env_provider or DEFAULT_AI_PROVIDER).strip().lower()
        if wire not in ("deepseek", "gemini"):
            return None, "ai_not_configured"
        default_base = DEFAULT_DEEPSEEK_BASE if wire == "deepseek" else DEFAULT_GEMINI_BASE
        default_model = DEFAULT_DEEPSEEK_MODEL if wire == "deepseek" else DEFAULT_GEMINI_MODEL
        base = (B2_AI_BASE or os.environ.get("B2_AI_BASE") or default_base).strip()
        model = (B2_AI_MODEL or os.environ.get("B2_AI_MODEL") or default_model).strip()
    if wire == "gemini":
        payload = {
            "contents": [{"parts": [{"text": f"{system}\n\n{user_block}"}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "temperature": 0.2},
        }
    else:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
    body, error = _provider_complete(base, api_key, model, payload, wire=wire)
    if error:
        return None, error
    try:
        if wire == "gemini":
            content = body["candidates"][0]["content"]["parts"][0]["text"]
        else:
            content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("not text")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None, "upstream_failed"
    return content, None



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


_LIBROS_CACHE = {"ts": 0.0, "body": b""}
_LIBROS_TTL = 60.0


def _libros_json():
    """The /libros.json payload, memoised for 60 s.

    scan() walks the whole material tree; calling it on every page load was pure
    waste (and the response was sent without cache headers, so every visitor paid
    for it). 60 s is short enough that adding a book shows up without a restart.
    """
    now = time.time()
    if _LIBROS_CACHE["body"] and now - _LIBROS_CACHE["ts"] < _LIBROS_TTL:
        return _LIBROS_CACHE["body"]
    data = [{"name": it["name"], "folder": it["folder"], "ext": it["ext"],
             "rel": it["rel"], "size": it["size"], "href": "/files/" + quote(it["rel"])}
            for it in scan()]
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    _LIBROS_CACHE["ts"] = now
    _LIBROS_CACHE["body"] = body
    return body


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


PBKDF2_ITERATIONS = store.PBKDF2_ITERATIONS


def hash_password(salt, password, iterations=None):
    """PBKDF2-HMAC-SHA256 hash (600,000 iterations by default, OWASP 2023)."""
    iters = iterations or PBKDF2_ITERATIONS
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iters).hex()


def _legacy_hash_password(salt, password):
    """sha256(salt + password) used before the migration to pbkdf2."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _record_iterations(u):
    """PBKDF2 iterations of a stored record (200k for hashes written before 600k)."""
    try:
        iters = int(u.get("iters") or 200_000)
    except (TypeError, ValueError):
        iters = 200_000
    return max(1, iters)


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
        return hmac.compare_digest(
            u["hash"], hash_password(u["salt"], password, _record_iterations(u)))
    if not algo:
        return hmac.compare_digest(u["hash"], _legacy_hash_password(u["salt"], password))
    return False


def new_token(user_id, ua=""):
    """Create a session token and persist only its hash.

    Two expiry clocks: `exp` slides on activity (TOKEN_TTL, 30 days) and
    `absolute_exp` is a hard ceiling (TOKEN_ABSOLUTE_TTL, 90 days) that is
    never extended, so a stolen token cannot be kept alive forever.
    """
    with _TOKENS_LOCK:
        tokens = load_tokens()
        # Prune expired tokens
        now = time.time()
        tokens = {t: v for t, v in tokens.items()
                  if v.get("exp", 0) > now
                  and v.get("absolute_exp", now + 1) > now}
        tok = secrets.token_hex(24)
        tokens[_token_key(tok)] = {
            "user_id": user_id, "exp": now + TOKEN_TTL, "issued": now,
            "absolute_exp": now + TOKEN_ABSOLUTE_TTL,
            "last_seen": now, "ua_hash": _ua_hash(ua),
        }
        save_tokens(tokens)
    return tok


def auth_from_token(token, ua="", ip="", rid=""):
    """Return (user_id, error) for a session token and extend its expiry (sliding).

    Tokens are stored hashed; a legacy plaintext record is migrated to its hash
    on first use. The sliding expiry is capped by `absolute_exp`, which is set
    once and never moved. A User-Agent change is logged as `ua_changed`
    (never blocked).

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
        now = time.time()
        abs_exp = v.get("absolute_exp")
        if not isinstance(abs_exp, (int, float)):
            # Records written before the absolute ceiling existed: anchor it to
            # `issued` so the token cannot gain a fresh 90 days on every use.
            abs_exp = v.get("issued", now) + TOKEN_ABSOLUTE_TTL
            v["absolute_exp"] = abs_exp
        if now >= abs_exp or v.get("exp", 0) < now:
            tokens.pop(key, None)
            save_tokens(tokens)
            return None, "session expired"
        v["exp"] = min(now + TOKEN_TTL, abs_exp)  # sliding, never past the ceiling
        v["last_seen"] = now
        ua_h = _ua_hash(ua)
        if v.get("ua_hash") and v["ua_hash"] != ua_h:
            _audit("ua_changed", v.get("user_id", ""), ip, rid)
        if ua_h:
            v["ua_hash"] = ua_h
        save_tokens(tokens)
        return v.get("user_id"), None


def revoke_token(token):
    """Delete one session; return the user id it belonged to ("" when unknown)."""
    with _TOKENS_LOCK:
        tokens = load_tokens()
        key = _token_key(token)
        rec = tokens.pop(key, None)
        if rec is None:
            rec = tokens.pop(token, None)
        if rec is not None:
            save_tokens(tokens)
        return rec.get("user_id", "") if isinstance(rec, dict) else ""


def revoke_user_sessions(user_id):
    """Delete every session of one user; return how many were revoked."""
    with _TOKENS_LOCK:
        tokens = load_tokens()
        kept = {t: v for t, v in tokens.items() if v.get("user_id") != user_id}
        revoked = len(tokens) - len(kept)
        if revoked:
            save_tokens(kept)
        return revoked


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


# --- Password policy (fase 12/24): embedded list, no dependencies, no downloads ---
COMMON_PASSWORDS = store.COMMON_PASSWORDS
PASSWORD_MIN_LEN = 10


_PASSWORD_ERRORS = {
    "password too short (min 10)": "Password must be at least 10 characters.",
    "password too common": "Password is too common. Choose something harder to guess.",
    "password equals username": "Password must not be your username.",
}


def password_problem(name, password):
    """Return the error key when the password is too weak, else None."""
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LEN:
        return "password too short (min 10)"
    if isinstance(name, str) and password.strip().lower() == name.strip().lower():
        return "password equals username"
    if password.strip().lower() in COMMON_PASSWORDS:
        return "password too common"
    return None


def password_strength(password):
    """Coarse strength signal for the registration notice: 0=weak, 1=fair, 2=strong."""
    if not isinstance(password, str):
        return 0
    classes = sum((
        any(ch.islower() for ch in password),
        any(ch.isupper() for ch in password),
        any(ch.isdigit() for ch in password),
        any(not ch.isalnum() for ch in password),
    ))
    if len(password) >= 14 and classes >= 3:
        return 2
    if len(password) >= PASSWORD_MIN_LEN and classes >= 2:
        return 1
    return 0


def register_user(name, password, color=None):
    """Create a user. Return (user_id, error)."""
    users = store.list_users()
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        return None, "name is empty"
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LEN:
        return None, "password too short (min 10)"
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
        "algo": "pbkdf2", "iters": PBKDF2_ITERATIONS,
        "color": color or "#1b2b48",
        "created": time.strftime("%Y-%m-%d %H:%M"),
    })
    return uid, None


def _needs_rehash(u):
    """True when a stored hash is legacy (sha256) or below the 600k iteration target."""
    if not u.get("algo"):
        return True
    if u.get("algo") != "pbkdf2":
        return False
    return _record_iterations(u) < PBKDF2_ITERATIONS


def login_user(name, password):
    """Validate credentials and migrate legacy hashes. Return (user_id, error).

    Transparent upgrade: on a successful login, a sha256 hash or a PBKDF2 hash
    below 600,000 iterations is re-hashed with the current parameters and saved,
    so nobody is locked out and old hashes do not stay weak at rest.
    """
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
        if _needs_rehash(match):
            migrated = dict(match)
            migrated["salt"] = secrets.token_hex(8)
            migrated["hash"] = hash_password(migrated["salt"], password)
            migrated["algo"] = "pbkdf2"
            migrated["iters"] = PBKDF2_ITERATIONS
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
    rec["iters"] = PBKDF2_ITERATIONS
    store.create_user(user_id, rec)
    return None, 200


def delete_user(user_id):
    """Remove the account: data dir, users.json record and every session token."""
    store.remove_user(user_id)
    # Phase 31: a closed account leaves no plan, no usage and no license link
    # behind (the code stays burnt: only the hash row survives, detached).
    plans.forget_user(user_id)
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
        "algo": "pbkdf2", "iters": PBKDF2_ITERATIONS,
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
    """Return a user's progress, or {} if it does not exist.

    The `plan` mirror is derived here on every read: data/plans.json is the
    source of truth, the document only carries a copy for the UI to render.
    """
    data = store.get_progress(user_id)
    data = data if data is not None else {}
    if isinstance(data, dict):
        plan = _plan_for(user_id)
        data["plan"] = {"plan": plan["plan"], "since": plan["since"],
                        "until": plan["until"], "source": plan["source"]}
    return data


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
# /privacy — the privacy policy (plain server-rendered HTML, same look as the
# app: design tokens + light/dark themes). The same text lives in
# docs/PRIVACY.md. The contact address is the explicit TODO_OWNER_EMAIL
# placeholder: replace it with the real owner email before going public.
# ---------------------------------------------------------------------------
# /privacy, /terms, /security — rendered from docs/*.md by legal.py. The
# documents are trusted, but the renderer escapes every source character.
def privacy_page():
    """Return the privacy policy page (English, dark-mode aware)."""
    return legal.legal_page("PRIVACY", "Privacy Policy")


def terms_page():
    """Return the terms of use page."""
    return legal.legal_page("TERMS", "Terms of Use")


def security_page():
    """Return the security policy / disclosure page."""
    return legal.legal_page("SECURITY", "Security Policy")


# ---------------------------------------------------------------------------
# Audit log (fase 12/24): append-only, hash-chained JSON lines.
# NEVER stores tokens, passwords, hashes or student content. Every line carries
# `prev` = sha256 of the previous raw line (first line: 64 zeros), so editing or
# deleting a line breaks the chain. tools/verify_audit.py checks it.
# Rotates at 5 MB → audit.log.1; the chain continues across the rotation.
# ---------------------------------------------------------------------------
_AUDIT_LOCK = threading.Lock()
AUDIT_MAX_BYTES = 5 * 1024 * 1024
AUDIT_GENESIS = "0" * 64


def _audit_file():
    return os.path.join(DATA_DIR, "audit.log")


def _audit_tail_hash(path):
    """sha256 hex of the last complete line of `path`, or None when empty/missing.

    Reads only the tail (64 KB), so the cost does not grow with the log size.
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 65536))
            tail = f.read()
    except OSError:
        return None
    lines = [ln for ln in tail.split(b"\n") if ln.strip()]
    if not lines:
        return None
    return hashlib.sha256(lines[-1]).hexdigest()


def _audit_prev(path):
    """`prev` for the next line: tail of the current file, else of the rotated one."""
    return (_audit_tail_hash(path)
            or _audit_tail_hash(path + ".1")
            or AUDIT_GENESIS)


def _audit(event, user="", ip="", rid="", detail=None):
    """Append one hash-chained event line to data/audit.log (0600).

    Best-effort: never raises. `detail` may carry scalar metadata only
    (lengths, reason slugs, statuses). Callers must never pass content or
    secrets: the student's text is not logged.
    """
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rid": rid or "",
        "event": event,
        "user": user or "",
        "ip": _client_id(ip) if ip else "",
    }
    if isinstance(detail, dict):
        for k, v in detail.items():
            if k in record or not isinstance(v, (str, int, float, bool)):
                continue
            record[k] = v[:120] if isinstance(v, str) else v
    try:
        with _AUDIT_LOCK:
            path = _audit_file()
            try:
                if os.path.exists(path) and os.path.getsize(path) > AUDIT_MAX_BYTES:
                    os.replace(path, path + ".1")
            except OSError:
                pass
            record["prev"] = _audit_prev(path)
            line = json.dumps(record, ensure_ascii=False)
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


def _scrub_audit_user(keys):
    """Erase the username from retained audit lines for a deleted account.

    The chain is rebuilt (prev recomputed) because editing a line invalidates
    it. Deletion is the one legitimate rewrite: the events stay (counted,
    timestamped, request-id'd), but the identity is gone. Returns the number of
    lines scrubbed.
    """
    wanted = {str(k).lower() for k in keys if k}
    if not wanted:
        return 0
    with _AUDIT_LOCK:
        objects = []
        for path in (_audit_file() + ".1", _audit_file()):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for ln in f:
                        ln = ln.strip()
                        if not ln:
                            continue
                        try:
                            obj = json.loads(ln)
                        except ValueError:
                            continue
                        if isinstance(obj, dict):
                            objects.append(obj)
            except OSError:
                continue
        scrubbed = 0
        prev = AUDIT_GENESIS
        out = []
        for obj in objects:
            if str(obj.get("user", "")).lower() in wanted:
                obj["user"] = ""
                obj["scrubbed"] = True
                scrubbed += 1
            obj["prev"] = prev
            line = json.dumps(obj, ensure_ascii=False)
            out.append(line)
            prev = hashlib.sha256(line.encode("utf-8")).hexdigest()
        if scrubbed:
            path = _audit_file()
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(out) + ("\n" if out else ""))
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
            os.chmod(path, 0o600)
            try:
                os.remove(path + ".1")
            except OSError:
                pass
        return scrubbed


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
# /.well-known/security.txt (RFC 9116)
# ---------------------------------------------------------------------------
PUBLIC_BASE = os.environ.get("B2_PUBLIC_URL", "https://vps-server.tail40095b.ts.net").rstrip("/")


def security_txt():
    """RFC 9116 security.txt body.

    There is no published owner mailbox, so the only Contact is the GitHub
    advisory form (a real, working private channel). Expires is always in the
    future (180 days).
    """
    expires = time.strftime("%Y-%m-%dT%H:%M:%S.000Z",
                            time.gmtime(time.time() + 180 * 24 * 3600))
    return (
        "Contact: https://github.com/Juan-Martin-Cerezo/b2first-tracker/security/advisories/new\n"
        f"Expires: {expires}\n"
        "Preferred-Languages: en, es\n"
        f"Canonical: {PUBLIC_BASE}/.well-known/security.txt\n"
        f"Policy: {PUBLIC_BASE}/security\n"
        f"Acknowledgments: {PUBLIC_BASE}/security\n"
    )


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
PERMISSIONS_NONE = "geolocation=(), camera=(), microphone=()"
PERMISSIONS_MIC = "geolocation=(), camera=(), microphone=(self)"

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # microphone=(self) is only advertised on the tracker page, which is the one
    # place the speaking studio captures audio. Everything else gets the minimum.
    "Permissions-Policy": PERMISSIONS_NONE,
    # 'unsafe-inline' is still required by the single-file UI (197 inline event
    # handlers); 'unsafe-eval' is not present. object-src/base-uri close the
    # plugin and <base> injection paths. See SECURITY.md §"Residual risks".
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline' blob:; worker-src 'self' blob:; "
        "connect-src 'self' wss://generativelanguage.googleapis.com; "
        "object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ),
}


def _security_headers(path):
    """Return the security headers for one request path.

    `microphone=(self)` is only granted to the tracker itself; every other
    response advertises no device capability at all.
    """
    headers = dict(SECURITY_HEADERS)
    if (path or "").split("?", 1)[0] in ("/", "/index.html"):
        headers["Permissions-Policy"] = PERMISSIONS_MIC
    return headers


def _server_timing(t0):
    """`Server-Timing` value with the internal processing time in milliseconds."""
    return "app;dur=%.1f" % max(0.0, (time.time() - t0) * 1000.0)


def _allowed_hosts():
    """Host allowlist from B2_ALLOWED_HOSTS (comma-separated, case-insensitive)."""
    raw = B2_ALLOWED_HOSTS if isinstance(B2_ALLOWED_HOSTS, str) else ""
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _host_allowed(host):
    """True when no allowlist is configured or `host` (port-stripped) is listed."""
    allowed = _allowed_hosts()
    if not allowed:
        return True
    raw = (host or "").strip().lower()
    name = raw
    if name.startswith("["):                 # IPv6 literal: [::1]:8088
        end = name.find("]")
        if end != -1:
            name = name[:end + 1]
    elif ":" in name:                        # host:port
        name = name.split(":", 1)[0]
    return name in allowed or raw in allowed


def _bad_path_code(raw_target):
    """Return 400/403 for a hostile request-target, else None.

    Checks only the path (never the query): literal NUL, backslash, `..` in any
    encoding (single or double percent-encoded), empty `//` segments and hidden
    dot-files. The target is decoded for inspection only; routing still decodes
    exactly once.
    """
    path = raw_target.split("?", 1)[0]
    candidate = path
    for _ in range(3):                       # path, one decode, two decodes
        low = candidate.lower()
        if "\x00" in candidate or "\\" in candidate or ".." in low:
            return 400
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded
    if "//" in path or "//" in candidate:
        return 400
    for i, seg in enumerate(candidate.split("/")):
        if i == 1 and seg == ".well-known":
            continue                         # RFC 9116 lives under a dot folder
        if seg not in ("", ".") and seg.startswith("."):
            return 403                       # hidden files: no existence oracle
    return None


_LOG_LOCK = threading.Lock()  # keeps one access-log line atomic under concurrency

# ---------------------------------------------------------------------------
# Static payload cache (fase 23): compress once, validate by (path, mtime, size)
# ---------------------------------------------------------------------------
# Serving 434 KB of index.html re-gzipped on every request burned ~15-20 ms of
# CPU per visit on the Pi. The cache stores the raw and gzipped bodies plus the
# ETag/Last-Modified validators. A touch of the file changes mtime_ns, so the
# next request rebuilds the entry: no restart, no TTL.
_STATIC_LOCK = threading.Lock()
_STATIC_CACHE = {}  # {full_path: {key, raw, gz, etag, last_modified, mtime}}


def _compressible(ctype):
    """True for text-shaped payloads worth gzipping (skip already-compressed ones)."""
    return not ctype.startswith(("image/", "audio/", "video/",
                                 "application/zip", "application/pdf"))


def _http_date(ts):
    return formatdate(ts, usegmt=True)


def _etag_matches(header, etag):
    """True when If-None-Match lists `etag` (weak tags and * included)."""
    if not header:
        return False
    for tag in header.split(","):
        tag = tag.strip()
        if tag == "*":
            return True
        if tag.startswith("W/"):
            tag = tag[2:].strip()
        if tag == etag:
            return True
    return False


def _if_modified_since_hit(header, mtime):
    """True when If-Modified-Since is not older than the file mtime."""
    if not header:
        return False
    try:
        dt = parsedate_to_datetime(header)
        return dt is not None and dt.timestamp() >= int(mtime)
    except (TypeError, ValueError, OverflowError, OSError):
        return False


def _static_entry(full, ctype):
    """Return the cached (raw, gzip, validators) entry, rebuilding it on change."""
    st = os.stat(full)
    key = (st.st_mtime_ns, st.st_size, st.st_ino)
    with _STATIC_LOCK:
        entry = _STATIC_CACHE.get(full)
        if entry and entry["key"] == key:
            return entry
    with open(full, "rb") as f:
        raw = f.read()
    gz = gzip.compress(raw, 6) if len(raw) >= 1024 and _compressible(ctype) else None
    # The hash covers the served bytes *and* the file identity: a same-mtime
    # redeploy gets a new ETag, and a bare `touch` invalidates client caches.
    h = hashlib.sha256()
    h.update(gz if gz is not None else raw)
    h.update(b"\0")
    h.update(f"{st.st_mtime_ns}:{st.st_size}".encode("ascii"))
    entry = {
        "key": key,
        "raw": raw,
        "gz": gz,
        "etag": '"' + h.hexdigest()[:16] + '"',
        "last_modified": _http_date(st.st_mtime),
        "mtime": st.st_mtime,
    }
    with _STATIC_LOCK:
        _STATIC_CACHE[full] = entry
    return entry


class H(BaseHTTPRequestHandler):
    # No version banner: the default handler appends the Python version, which tells an
    # attacker which interpreter CVEs to try. Send a bare, unversioned product name.
    server_version = "B2First"
    sys_version = ""
    # Slow clients (slowloris) are cut off after this many seconds of socket stall.
    timeout = SOCKET_TIMEOUT

    def version_string(self):
        """Bare product name: never expose the interpreter version."""
        return self.server_version

    def __getattr__(self, name):
        """Send 405 + Allow for any method the router does not implement.

        BaseHTTPRequestHandler would answer 501 for unknown `do_*` names; this
        keeps every unsupported method (TRACE, FROB, PATCH...) on the same
        documented 405 path without enumerating them.
        """
        if name.startswith("do_"):
            return self._method_not_allowed
        raise AttributeError(name)

    def handle(self):
        """Cap simultaneous connections; answer 503 when the semaphore is exhausted.

        Non-blocking acquire: an overloaded server fails fast with Retry-After
        instead of parking the request thread until a slot frees up.
        """
        if not _CONN_SEM.acquire(blocking=False):
            self._begin()
            self.close_connection = True
            try:
                self._send_json(503, {"error": "busy", "retry_after": 1},
                                {"Retry-After": "1"})
            except OSError:
                pass
            finally:
                self._log_line()
            return
        try:
            super().handle()
        finally:
            _CONN_SEM.release()

    def _begin(self):
        """Initialize the per-request logging state.

        Used before parse_request in the connection-cap path, so path/command
        may not exist yet: give them neutral defaults rather than letting a
        logging or header helper raise while answering 503.
        """
        self._rid = secrets.token_hex(4)
        self._status = 0
        self._t0 = time.time()
        self._auth_result = None   # refreshed per request, never reused
        if getattr(self, "path", None) is None:
            self.path = ""
        if not getattr(self, "command", None):
            self.command = "-"
        if getattr(self, "requestline", None) is None:
            self.requestline = ""
        if getattr(self, "request_version", None) is None:
            self.request_version = ""

    def _method_not_allowed(self):
        """405 + Allow for any method outside ALLOWED_METHODS (e.g. TRACE)."""
        self._begin()
        try:
            self._send_json(405, {"error": "method not allowed"})
        except OSError:
            pass
        finally:
            self.close_connection = True
            self._log_line()

    def _reject(self, code, obj):
        """Answer a hostile request and close, without reading its body."""
        self.close_connection = True
        self._safe_json(code, obj)

    def log_message(self, fmt, *a):
        """Silence per-request logging (replaced by _log_line: one line, no secrets)."""
        pass

    def _log_line(self):
        """One stdout access line per request. Never logs tokens, query or body."""
        path = self.path.split("?")[0]
        ms = int((time.time() - self._t0) * 1000)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = f"{ts} rid={self._rid} {self.command} {path} {self._status} {ms}ms ip={_client_id(_real_ip(self))}\n"
        with _LOG_LOCK:
            print(line, end="", flush=True)   # one write: no interleaved log lines

    def _run(self):
        """Route one request: request id, access log and error containment."""
        self._begin()
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

    def _send_raw(self, code, body, ctype, extra=None):
        """Write a response as-is (callers that pre-encode pass Content-Encoding)."""
        self._status = code
        extra = dict(extra or {})
        if code == 405:
            # Every 405 advertises the supported methods, wherever it comes from.
            extra.setdefault("Allow", ALLOW_HEADER)
        self.send_response(code)
        for k, v in _security_headers(self.path).items():
            self.send_header(k, v)
        self.send_header("X-Request-Id", self._rid)
        self.send_header("Server-Timing", _server_timing(self._t0))
        if self.path.startswith("/api/") and "Cache-Control" not in extra:
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_ndjson_start(self):
        """Begin a close-delimited NDJSON stream (HTTP/1.0, no Content-Length).

        Used by the speaking turn so the reply text reaches the browser before
        the TTS call finishes: the UI can show what the examiner said while the
        audio is still being generated.
        """
        self._status = 200
        self.close_connection = True
        self.send_response(200)
        for key, value in _security_headers(self.path).items():
            self.send_header(key, value)
        self.send_header("X-Request-Id", self._rid)
        self.send_header("Server-Timing", _server_timing(self._t0))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _send_ndjson(self, obj):
        """Write one JSON line and flush it immediately."""
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
        self.wfile.flush()

    def _send(self, code, body, ctype, extra=None):
        """Helper: response with security headers + Content-Length.

        Compresses compressible payloads when the client advertises gzip. Dynamic
        bodies stay on this path; static files go through _serve_cached_static so
        the compressed bytes and validators are computed once.
        """
        extra = dict(extra or {})
        if (len(body) >= 1024 and code not in (204, 304)
                and _compressible(ctype)
                and "gzip" in (self.headers.get("Accept-Encoding") or "").lower()):
            body = gzip.compress(body, 6)
            extra.setdefault("Content-Encoding", "gzip")
            extra.setdefault("Vary", "Accept-Encoding")
        self._send_raw(code, body, ctype, extra)

    def _send_not_modified(self, etag, last_modified):
        """304 with validators and no body (no Content-Length, so nothing is sent)."""
        self._status = 304
        self.send_response(304)
        for k, v in _security_headers(self.path).items():
            self.send_header(k, v)
        self.send_header("X-Request-Id", self._rid)
        self.send_header("Server-Timing", _server_timing(self._t0))
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", last_modified)
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def _serve_cached_static(self, full, ctype, extra=None):
        """Serve a static file from the in-memory cache with ETag/Last-Modified.

        Revalidated by (mtime_ns, size, inode), so `touch` invalidates on the next
        request. If-None-Match / If-Modified-Since answer 304 without a body and
        without recompressing. B2_NO_CACHE=1 bypasses the cache for baseline runs.
        """
        extra = dict(extra or {})
        extra.setdefault("Cache-Control", "no-cache")
        if B2_NO_CACHE:
            try:
                with open(full, "rb") as f:
                    body = f.read()
            except OSError:
                self._send(404, b"not found", "text/plain")
                return
            self._send(200, body, ctype, extra)
            return
        try:
            entry = _static_entry(full, ctype)
        except OSError:
            self._send(404, b"not found", "text/plain")
            return
        inm = self.headers.get("If-None-Match")
        if _etag_matches(inm, entry["etag"]) or (
                not inm and _if_modified_since_hit(
                    self.headers.get("If-Modified-Since"), entry["mtime"])):
            self._send_not_modified(entry["etag"], entry["last_modified"])
            return
        extra["ETag"] = entry["etag"]
        extra["Last-Modified"] = entry["last_modified"]
        extra["Vary"] = "Accept-Encoding"
        if (entry["gz"] is not None
                and "gzip" in (self.headers.get("Accept-Encoding") or "").lower()):
            extra["Content-Encoding"] = "gzip"
            self._send_raw(200, entry["gz"], ctype, extra)
        else:
            self._send_raw(200, entry["raw"], ctype, extra)

    def _send_json(self, code, obj, extra=None):
        """Helper: JSON response."""
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8", extra)

    def _rate_limited(self, key, limit, window_s, kind="ip"):
        """Apply _rate() and answer 429 + Retry-After when the limit is exceeded.

        `kind` feeds the cumulative counters exposed by /api/metrics, so the
        operator can tell a shared-IP burst from a single abusive account.
        """
        if _rate(key, limit, window_s):
            return False
        _rate_stat(kind)
        if kind == "user":
            # No personal data, no content: just who hit the bucket and where.
            uid = key.split(":", 1)[1] if ":" in key else ""
            _audit("rate_limited_by_user", uid, _real_ip(self), self._rid,
                   {"path": self.path.split("?", 1)[0][:120]})
        self._drain()
        retry = _retry_after(key, window_s)
        self._send_json(429, {"error": "too many requests", "retry_after": retry},
                        {"Retry-After": str(retry)})
        return True

    def _plan_limit_429(self, limit, plan, value, window, reset, uid):
        """429 that names the plan, the limit and what unlocks more.

        Never a dead end: `unlock` tells the client that `pro` (or a BYO key)
        lifts the limit, which is what the limit modal offers.
        """
        _audit("plan_limit_hit", uid or "", _real_ip(self), self._rid,
               {"limit": limit, "plan": plan})
        self._send_json(429, {
            "error": "plan_limit",
            "limit": limit,
            "plan": plan,
            "limit_value": value,
            "window": window,
            "reset": reset,
            "unlock": "pro",
        })

    def _legacy_quota_429(self):
        """The pre-phase-31 body, kept when B2_AI_DAILY_PER_USER is the blocker."""
        reset = (date.today() + timedelta(days=1)).isoformat()
        self._send_json(429, {"error": "daily AI quota reached", "reset": reset})

    def _writing_gate(self, uid, ip):
        """May this request spend one LLM call? Replies and returns False if not.

        Checks only; the caller consumes right before the upstream call so a
        failed validation never burns quota.
        """
        legacy = _legacy_per_user_cap()
        if uid:
            plan = _plan_for(uid)
            limits = plan["limits"]["writing"]
            if limits is None:
                return True  # byo: their key pays, the hourly cap still applies
            if legacy is not None:
                if plans.writing_used(uid, "day") >= legacy:
                    self._legacy_quota_429()
                    return False
            elif plans.writing_used(uid, limits["window"]) >= limits["limit"]:
                self._plan_limit_429("writing", plan["plan"], limits["limit"],
                                     limits["window"],
                                     plans.reset_at(limits["window"]), uid)
                return False
        elif _ai_quota_left("ip:" + ip) <= 0:
            if legacy is None:
                free = plans.LIMITS["free"]["writing"]
                self._plan_limit_429("writing", "free", free["limit"],
                                     free["window"], plans.reset_at(free["window"]), "")
            else:
                self._legacy_quota_429()
            return False
        if _ai_total_left() <= 0:
            self._legacy_quota_429()
            return False
        return True

    def _writing_consume(self, uid, ip):
        """Count one LLM call for an account (persisted) or an IP (in memory)."""
        if uid:
            plans.writing_consume(uid)
            _ai_total_consume()
        else:
            _ai_quota_consume("ip:" + ip)

    def _speaking_gate(self, uid):
        """May this account mint one more mock? Replies and returns False if not."""
        plan = _plan_for(uid)
        limits = plan["limits"]["speaking"]
        if limits is None:
            return True
        used = plans.speaking_used(uid, limits["window"])
        if used["mocks"] >= limits["mocks"] or used["seconds"] >= limits["minutes"] * 60:
            self._plan_limit_429("speaking", plan["plan"], limits["mocks"],
                                 limits["window"],
                                 plans.reset_at(limits["window"]), uid)
            return False
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
        """Return (user_id, error) from the Authorization header (once per request).

        The router authenticates early to pick the rate-limit bucket, so handlers
        later in the same request reuse the result instead of re-reading tokens.
        """
        cached = getattr(self, "_auth_result", None)
        if cached is not None:
            return cached
        result = auth_from_token(self._bearer(), self.headers.get("User-Agent", ""),
                                 _real_ip(self), self._rid)
        self._auth_result = result
        return result

    def _handle(self):
        """Single router (used by GET and HEAD)."""
        # --- Request-target and header limits (before touching any state) ---
        if len(self.path) > MAX_URI_LEN:
            self._reject(414, {"error": "uri too long"})
            return
        if len(self.headers) > MAX_HEADERS:
            self._reject(431, {"error": "too many headers"})
            return
        if not _host_allowed(self.headers.get("Host", "")):
            self._reject(421, {"error": "misdirected request"})
            return
        bad = _bad_path_code(self.path)
        if bad:
            self._reject(bad, {"error": "invalid path" if bad == 400 else "forbidden"})
            return

        path = unquote(self.path.split("?")[0])
        clen = self._clen()

        # Body ceilings are decided from Content-Length before a single byte of
        # the body is read (no drain, no allocation): closing the connection is
        # what stops the upload.
        if clen > MAX_BODY_BYTES:
            self._reject(413, {"error": "payload too large"})
            return
        if path == "/api/speaking/pa" and clen > SPK_PA_MAX_BODY:
            _audit("pa_rejected", "", _real_ip(self), self._rid, {"reason": "too_large"})
            self._reject(413, {"error": "audio too large"})
            return
        if path == "/api/progress" and self.command == "PUT" and clen > PROGRESS_MAX_BYTES:
            self._reject(413, {"error": "progress too large"})
            return
        if path == "/api/billing/webhook" and clen > BILLING_WEBHOOK_MAX_BYTES:
            _audit("billing_webhook_rejected", "", _real_ip(self), self._rid,
                   {"reason": "too_large"})
            self._reject(413, {"error": "payload too large"})
            return

        # Rate limits: authenticated traffic is bucketed by user_id, everything
        # else by IP. A shared CGNAT/school IP therefore cannot 429 a logged-in
        # student because a classmate is hammering the API. Credential endpoints
        # stay IP-bucketed (anti-abuse) with a tighter ceiling.
        if path.startswith("/api/") and path != "/api/health":
            ip = _real_ip(self)
            if path in AUTH_RATE_PATHS:
                if self._rate_limited("ip-auth:" + ip, RATE_IP_AUTH, 60, "ip"):
                    return
            else:
                uid, _auth_err = self._auth()
                if uid:
                    if self._rate_limited("user-api:" + uid, RATE_USER_API, 60, "user"):
                        return
                elif self._rate_limited("ip-anon:" + ip, RATE_IP_ANON, 60, "ip"):
                    return

        # CORS is closed: answer preflights without any permissive header.
        if self.command == "OPTIONS":
            self._send(204, b"", "text/plain")
            return

        # RFC 9116 vulnerability-disclosure metadata (public, no auth).
        if path == "/.well-known/security.txt":
            if self.command not in ("GET", "HEAD"):
                self._send(405, b"method not allowed", "text/plain")
                return
            self._send(200, security_txt().encode("utf-8"),
                       "text/plain; charset=utf-8", {"Cache-Control": "public, max-age=3600"})
            return

        # Tracker (index.html) — cached, revalidated by ETag so a redeploy is
        # picked up on the next request and an unchanged file costs a 304.
        if path in ("/", "/index.html"):
            self._serve_cached_static(TRACKER, "text/html; charset=utf-8")
            return

        # Legal pages (public HTML, rendered from docs/*.md, cacheable for 5 min)
        if path in ("/privacy", "/terms", "/security"):
            page = {"/privacy": privacy_page, "/terms": terms_page,
                    "/security": security_page}[path]()
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8",
                       {"Cache-Control": "public, max-age=300"})
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
                        "Cache-Control": "public, max-age=3600",
                    })
                    return
            with open(full, "rb") as f:
                data = f.read()
            self._send(200, data, ctype, {"Accept-Ranges": "bytes",
                                          "Cache-Control": "public, max-age=3600"})
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
            self._serve_cached_static(full, ctype)
            return

        # Speaking Part 2 photographs (Wikimedia Commons, credits in the folder).
        # Same traversal guard as /assets: realpath must stay inside img/.
        if path.startswith("/img/"):
            rel = path[len("/img/"):]
            root_img = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
            full = os.path.realpath(os.path.join(root_img, rel))
            if not full.startswith(os.path.realpath(root_img)) or not os.path.isfile(full):
                self._send(404, b"not found", "text/plain")
                return
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            self._serve_cached_static(full, ctype)
            return

        # Phase 35: the speaking task bank. Pure data, so the exam can grow
        # without touching index.html; served like /diagnostico.json but
        # without the item-count validation (the client validates its shape).
        if path == "/material/speaking.json":
            full = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "material", "speaking.json")
            if not os.path.isfile(full):
                self._send(404, json.dumps({"error": "speaking bank not found"}).encode("utf-8"),
                           "application/json")
                return
            ctype = "application/json; charset=utf-8"
            self._serve_cached_static(full, ctype)
            return

        # Catalog JSON (consumed by the LIBROS tab of the tracker).
        # `scan()` walks the whole material tree on every call: memoise it for 60 s
        # and answer 304 when the client already has the same ETag. Without this,
        # every page load re-walks the filesystem and re-sends the JSON.
        if path == "/libros.json":
            body = _libros_json()
            etag = '"' + hashlib.sha256(body).hexdigest()[:16] + '"'
            inm = self.headers.get("If-None-Match") or ""
            if etag in [t.strip() for t in inm.split(",")] or inm.strip() == "*":
                self._status = 304
                self.send_response(304)
                for k, v in _security_headers(self.path).items():
                    self.send_header(k, v)
                self.send_header("X-Request-Id", self._rid)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "public, max-age=300, stale-while-revalidate=86400")
                self.end_headers()
                return
            self._send(200, body, "application/json; charset=utf-8",
                       {"Cache-Control": "public, max-age=300, stale-while-revalidate=86400",
                        "ETag": etag})
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

        # Phase 31: the plan behind the current account (auth, read-only).
        if path == "/api/plan":
            if self.command != "GET":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            plan = _plan_for(uid)
            usage = plans.usage_snapshot(uid, plan["limits"])
            self._send_json(200, {
                "plan": plan["plan"],
                "since": plan["since"],
                "until": plan["until"],
                "source": plan["source"],
                "limits": plan["limits"],
                "usage": usage,
                "reset_at": usage["reset_at"],
            })
            return

        # Phase 31: redeem an activation code (auth, 5 attempts/hour/account).
        # Every failure answers the same bytes: a caller cannot learn whether a
        # code is wrong, expired, unknown or already used.
        if path == "/api/plan/redeem":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._drain()
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            if self._rate_limited("plan:redeem:user:" + uid,
                                  LICENSE_ATTEMPTS_PER_HOUR, 3600, "user"):
                return
            length = self._clen()
            if length > 4096:
                self._drain()
                self._send_json(413, {"error": "payload too large"})
                return
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                req = json.loads(raw.decode("utf-8"))
                code = req.get("code") if isinstance(req, dict) else ""
            except (ValueError, UnicodeDecodeError):
                code = ""
            secret = _license_secret()
            if not secret:
                line = (f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                        f"rid={self._rid} plan/redeem disabled: B2_LICENSE_SECRET "
                        f"missing or shorter than {LICENSE_SECRET_MIN} bytes\n")
                with _LOG_LOCK:
                    print(line, end="", flush=True)
                self._send_json(503, {"error": "licenses_not_configured"})
                return
            found = plans.verify_code(code, secret)
            row = plans.license_row(code) if found else None
            if not found or (isinstance(row, dict) and row.get("redeemed_at")):
                self._send_json(400, {"error": "invalid_code"})
                return
            rec = plans.set_plan(uid, found["plan"], found["days"], "code",
                                 plans.code_hash(code))
            plans.mark_redeemed(code, uid, rec["until"])
            _audit("plan_redeemed", uid, _real_ip(self), self._rid,
                   {"plan": found["plan"], "days": found["days"]})
            self._send_json(200, {"ok": True, "plan": rec["plan"],
                                  "until": rec["until"], "source": rec["source"]})
            return

        # ---- Phase 33: billing (Stripe Checkout, portal, signed webhooks) ----
        if path == "/api/billing/status":
            if self.command != "GET":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            plan = _plan_for(uid)
            row = billing.get_sub(uid)
            self._send_json(200, {
                "plan": plan["plan"],
                "source": plan["source"],
                "renews_at": row.get("current_period_end"),
                "status": row.get("status") or (plan["source"] if plan["plan"] == "pro" else None),
                "grace_until": row.get("grace_until"),
                "portal_available": bool(row.get("customer_id")) and billing.portal_ready(),
                "billing_mode": billing.mode(),
            })
            return

        if path == "/api/billing/checkout":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._drain()
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            self._drain()
            if not billing.checkout_ready():
                self._send_json(503, {"error": "billing_not_configured"})
                return
            cfg = billing.config()
            idem = "%s-%s" % (uid, time.strftime("%Y-%m-%d", time.gmtime()))
            try:
                session = billing.create_checkout_session(
                    uid, cfg["price_id"],
                    cfg["public_url"] + "/?billing=success",
                    cfg["public_url"] + "/?billing=cancel",
                    idem)
            except billing.BillingError:
                _audit("billing_checkout_failed", uid, _real_ip(self), self._rid)
                self._send_json(502, {"error": "billing_provider_error"})
                return
            url = session.get("url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                _audit("billing_checkout_failed", uid, _real_ip(self), self._rid)
                self._send_json(502, {"error": "billing_provider_error"})
                return
            _audit("billing_checkout", uid, _real_ip(self), self._rid,
                   {"session": str(session.get("id") or "")[:64]})
            self._send_json(200, {"url": url, "id": session.get("id")})
            return

        if path == "/api/billing/portal":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._drain()
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            self._drain()
            if not billing.portal_ready():
                self._send_json(503, {"error": "billing_not_configured"})
                return
            customer = billing.get_sub(uid).get("customer_id")
            if not customer:
                self._send_json(400, {"error": "no_subscription"})
                return
            try:
                session = billing.create_portal_session(
                    customer, billing.config()["public_url"] + "/?billing=portal")
            except billing.BillingError:
                _audit("billing_portal_failed", uid, _real_ip(self), self._rid)
                self._send_json(502, {"error": "billing_provider_error"})
                return
            url = session.get("url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                self._send_json(502, {"error": "billing_provider_error"})
                return
            _audit("billing_portal", uid, _real_ip(self), self._rid)
            self._send_json(200, {"url": url})
            return

        # No auth here: the signature is the credential. The body is never
        # echoed, never logged and never applied twice for the same event id.
        if path == "/api/billing/webhook":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            length = self._clen()
            if length > BILLING_WEBHOOK_MAX_BYTES:
                self._drain()
                self._send_json(413, {"error": "payload too large"})
                return
            if not billing.webhook_ready():
                self._drain()
                self._send_json(503, {"error": "billing_not_configured"})
                return
            raw = self.rfile.read(length) if length > 0 else b""
            ok, event = billing.verify_webhook(
                raw, self.headers.get("Stripe-Signature", ""),
                billing.config()["webhook_secret"], time.time())
            if not ok:
                _audit("billing_bad_signature", "", _real_ip(self), self._rid,
                       {"bytes": len(raw)})
                self._send_json(400, {"error": "invalid_signature"})
                return
            kind, event_uid, applied, duplicate = _apply_billing_event_once(event)
            if applied and event_uid:
                _audit("billing_event", event_uid, _real_ip(self), self._rid,
                       {"type": kind[:60]})
            if kind == "invoice.payment_failed" and event_uid:
                # Audit the account only: never amounts, never the invoice.
                _audit("billing_payment_failed", event_uid, _real_ip(self), self._rid,
                       {"status": "past_due"})
            self._send_json(200, {"ok": True})
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
                    "password too short (min 10)": (400, "Password must be at least 10 characters."),
                    "name is empty": (400, "Username is required."),
                }.get(err, (400, err))
                self._send_json(code, {"error": msg})
                return
            _audit("register", req.get("name", ""), _real_ip(self), self._rid)
            tok = new_token(uid, self.headers.get("User-Agent", ""))
            u = store.get_user(uid)
            body = json.dumps({
                "id": uid, "name": u["name"], "color": u["color"], "token": tok,
                "strength": password_strength(req.get("password", "")),
            }, ensure_ascii=False).encode("utf-8")
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
            revoked_uid = revoke_token(req.get("token", ""))
            _audit("session_revoked", revoked_uid, _real_ip(self), self._rid,
                   {"reason": "logout"})
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

        # Password change (Bearer auth). Revokes every session, including this one,
        # and mints a replacement token for the caller.
        if path == "/api/password":
            if self.command != "POST":
                self._send(405, b"method not allowed", "text/plain"); return
            if self._rate_limited("password:" + _real_ip(self), 5, 3600):
                return
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
            # A password change revokes EVERY session of the user, including the
            # one making the request: a leaked password must not keep any old
            # token alive. A fresh token is minted and returned in the same
            # response, so this client is not left holding a dead credential.
            revoked = revoke_user_sessions(uid)
            fresh = new_token(uid, self.headers.get("User-Agent", ""))
            u = store.get_user(uid)
            _audit("password_change", u.get("name", uid) if u else uid, _real_ip(self), self._rid)
            _audit("session_revoked", uid, _real_ip(self), self._rid,
                   {"reason": "password_change", "count": revoked})
            self._send(200, json.dumps({"ok": True, "token": fresh}).encode("utf-8"),
                       "application/json; charset=utf-8")
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
                    "ai_left_today": _ai_left_for(uid),
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
                u = store.get_user(uid) or {}
                name = u.get("name", "")
                delete_user(uid)
                _scrub_audit_user({uid, name})
                # One final line, after the data is gone: the account id is the
                # only identifier left, never the username.
                _audit("account_delete", uid, _real_ip(self), self._rid)
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

        # Full data export (auth): progress + plan + usage + own audit events,
        # in one JSON file (GDPR-style portability).
        if path == "/api/export":
            if self.command != "GET":
                self._send(405, b"method not allowed", "text/plain"); return
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"}); return
            u = store.get_user(uid) or {}
            name = u.get("name", "")
            mine = {str(uid).lower(), str(name).lower()}
            events = [e for e in read_audit_events()
                      if str(e.get("user", "")).lower() in mine]
            data = read_user_progress(uid)
            if not isinstance(data, dict):
                data = {}
            data["account"] = public_user(u) if u else {"id": uid}
            data["usage"] = plans.usage_row(uid)
            data["audit"] = events
            data["exported_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            data["export_version"] = 1
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
                    self._reject(413, {"error": "progress too large"}); return
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
                    # Secrets never belong in the synced document: the legacy
                    # aiKey and any stray BYO block are dropped server-side too.
                    data["settings"].pop("aiKey", None)
                    data["settings"].pop("byo", None)
                # The plan mirror is read-only: plans.json is the source of truth,
                # so a client can never grant itself pro by PUTting the document.
                data.pop("plan", None)
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

        # --- Phase 36: which transport may this deployment advertise? --------
        # `live` is only true when the operator asserts Live AND the configured
        # model really lists bidiGenerateContent; `turn` is always available
        # because it is the transport that works with a plain API key.
        if path == "/api/speaking/capabilities":
            if self.command != "GET":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            self._send_json(200, {"live": _spk_live_available(), "turn": True})
            return

        # --- S3: Gemini Live examiner — ephemeral token + minute ledger -------
        # The browser connects straight to Google with a single-use token, so no
        # audio ever reaches this process. The key only signs the mint request.
        if path == "/api/speaking/token":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._drain()
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            if self._rate_limited("spk_tok:" + uid, SPK_TOKEN_RATE_PER_MIN, 60):
                return
            # S4: one token per voice. `role` picks the system instruction
            # (examiner or partner); `part` is echoed for the client's director.
            role, part, task = "examiner", 0, None
            if self._clen() > 0:
                left = self._clen()
                raw = self.rfile.read(min(left, 4096))
                left -= len(raw)
                while left > 0:              # keep the connection in sync
                    chunk = self.rfile.read(min(left, 4096))
                    if not chunk:
                        break
                    left -= len(chunk)
                try:
                    req = json.loads(raw.decode("utf-8") or "{}")
                except (ValueError, UnicodeDecodeError):
                    req = {}
                if isinstance(req, dict):
                    if req.get("role") == "partner":
                        role = "partner"
                    try:
                        part = int(req.get("part") or 0)
                    except (TypeError, ValueError):
                        part = 0
                    if part not in (1, 2, 3, 4):
                        part = 0
                    # Phase 35: the task the candidate sees on screen travels with
                    # the mint so the examiner asks exactly those questions.
                    # `clean_task()` whitelists and caps it; a malformed task
                    # degrades to the generic exam, it never rejects the mint.
                    task = req.get("task")
            api_key = _spk_google_key()
            if not api_key:
                # One line, no secret: only the missing knob is named.
                line = (f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                        f"rid={self._rid} speaking/token disabled: "
                        f"B2_SPK_GOOGLE_KEY missing\n")
                with _LOG_LOCK:
                    print(line, end="", flush=True)
                self._send_json(503, {"error": "speech_not_configured"})
                return
            if not self._speaking_gate(uid):
                return
            if _spk_remaining_s(uid) <= 0:
                reset = (date.today() + timedelta(days=1)).isoformat()
                self._send_json(429, {"error": "daily speaking limit reached",
                                      "reset": reset})
                return
            token, mint_err = _spk_mint_token(api_key)
            if not token:
                self._send_json(502, {"error": "token_mint_failed",
                                      "reason": mint_err})
                return
            # A failed mint never burns a mock: the plan meter is bumped only
            # once Google handed us a token.
            plans.speaking_add_mock(uid)
            store.speaking_add(uid, _spk_today(), 0, 1)
            _audit("token_minted", uid, _real_ip(self), self._rid,
                   {"part": part, "role": role})
            # `instruction` is the examiner's own system prompt (not a secret):
            # the browser has to send it in the setup message itself.
            # Phase 35: it is built from the part AND the task on screen, so the
            # examiner asks those questions, in that order, and nothing else.
            instruction = (speaking_prompts.partner_instruction(part or 1, task)
                           if role == "partner"
                           else speaking_prompts.examiner_instruction(part or 1, task))
            self._send_json(200, {
                "token": token,
                "expires_in": SPK_TOKEN_TTL_S,
                "model": _spk_model(),
                "ws_url": _spk_ws_url(),
                "role": role,
                "part": part,
                "instruction": instruction,
            })
            return

        # --- Phase 36: one spoken turn, one round trip ------------------------
        # POST {audio_b64, mime, part, role, history, task, session_id}
        #   → {transcript, reply, audio_b64, mime:"audio/wav", ms}
        # The audio of ONE turn travels up and is dropped; nothing is written to
        # disk, nothing text-shaped is logged. `say` (no audio) is the TTS-only
        # form used for the controller's scripted lines, so the exam can open
        # and hand over without a candidate turn in between.
        if path == "/api/speaking/turn":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._drain()
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            if self._rate_limited("spk_turn:" + uid, SPK_TURN_RATE_PER_MIN, 60, "user"):
                return
            if self._clen() > SPK_TURN_MAX_BODY:
                self._drain()
                self._send_json(413, {"error": "payload too large"})
                return
            raw = self.rfile.read(self._clen()) if self._clen() > 0 else b""
            try:
                req = json.loads(raw.decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("not dict")
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"error": "invalid_json"})
                return
            del raw
            api_key = _spk_google_key()
            if not api_key:
                self._send_json(503, {"error": "speech_not_configured"})
                return
            role = "partner" if req.get("role") == "partner" else "examiner"
            try:
                part = int(req.get("part") or 0)
            except (TypeError, ValueError):
                part = 0
            if part not in (1, 2, 3, 4):
                part = 0
            task = speaking_prompts.clean_task(req.get("task"))
            voice = SPK_TTS_VOICES.get(role, SPK_TTS_VOICES["examiner"])
            # Phase 38: `tts:"none"` means the browser speaks the reply text
            # with speechSynthesis — the turn costs the reply call only. The
            # default stays "gemini" so an old client keeps the old behaviour.
            tts = req.get("tts")
            tts = tts if tts in ("gemini", "none") else "gemini"

            # Phase 37: the client asks once, when a part opens, to pre-generate
            # the scripted lines it is about to speak. Free: no model call, no
            # mock, no minutes, and it returns immediately (the work is a
            # daemon thread).
            if req.get("warm") is True:
                if tts == "none":
                    # Nothing to pre-generate: the device voice needs no audio.
                    self._send_json(200, {"warmed": 0, "voice": voice,
                                          "tts": "none"})
                    return
                lines = _spk_warm_lines(req.get("lines"))
                if not lines:
                    lines = speaking_prompts.scripted_lines(part or 1, task, role)
                lines.append(_SPK_TURN_REPEAT)
                queued = _spk_warm_async(api_key, lines, voice)
                self._send_json(200, {"warmed": queued, "voice": voice})
                return

            # One mock per session, not per turn: the gate runs the first time a
            # session id is seen, and a known session keeps working afterwards.
            session_id = req.get("session_id")
            session_id = session_id.strip()[:64] if isinstance(session_id, str) else ""
            known = _spk_turn_session_known(uid, session_id)
            if not known and not self._speaking_gate(uid):
                return
            if _spk_remaining_s(uid) <= 0:
                reset = (date.today() + timedelta(days=1)).isoformat()
                self._send_json(429, {"error": "daily speaking limit reached",
                                      "reset": reset})
                return

            started = time.time()
            say = req.get("say")
            if "audio_b64" not in req and isinstance(say, str) and say.strip():
                text = say.strip()[:SPK_TURN_MAX_SAY]
                if tts == "none":
                    # No TTS call, no cache write, no quota: the browser speaks.
                    total = int((time.time() - started) * 1000)
                    if session_id and not known:
                        _spk_turn_session_mark(uid, session_id)
                        plans.speaking_add_mock(uid)
                    _audit("speaking_turn", uid, _real_ip(self), self._rid,
                           {"part": part, "role": role, "ms": total,
                            "say": True, "tts": "none"})
                    self._send_json(200, {
                        "transcript": "", "reply": text,
                        "audio_b64": None, "mime": None,
                        "ms": {"stt": 0, "llm": 0, "tts": 0,
                               "total": total, "cached": False},
                    })
                    return
                wav, tts_ms, cached, tts_err = _spk_tts_cached(api_key, text, voice)
                if tts_err:
                    self._send_json(502, {"error": "tts_failed", "reason": tts_err})
                    return
                if session_id and not known:
                    _spk_turn_session_mark(uid, session_id)
                    plans.speaking_add_mock(uid)
                _audit("speaking_turn", uid, _real_ip(self), self._rid,
                       {"part": part, "role": role, "ms": tts_ms,
                        "say": True, "cached": cached})
                self._send_json(200, {
                    "transcript": "", "reply": text,
                    "audio_b64": base64.b64encode(wav).decode("ascii"),
                    "mime": "audio/wav",
                    "ms": {"stt": 0, "llm": 0, "tts": tts_ms,
                           "total": tts_ms, "cached": cached},
                })
                return

            audio_b64 = req.get("audio_b64")
            if not isinstance(audio_b64, str) or not audio_b64:
                self._send_json(422, {"error": "invalid_audio"})
                return
            # Size and duration are decided from the base64 length: a 30 s clip
            # is refused before one byte is decoded.
            if len(audio_b64) > SPK_TURN_MAX_B64:
                self._send_json(413, {"error": "audio too large"})
                return
            mime = req.get("mime")
            mime = mime.strip().lower() if isinstance(mime, str) else ""
            if not mime.startswith(SPK_TURN_MIMES):
                mime = "audio/pcm;rate=16000"
            is_wav = "wav" in mime or mime.startswith("audio/l16")
            try:
                decoded = base64.b64decode(audio_b64, validate=False)
            except (ValueError, binascii.Error):
                self._send_json(422, {"error": "invalid_audio"})
                return
            audio_bytes = max(0, len(decoded) - (44 if is_wav else 0))
            if (audio_bytes > SPK_TURN_MAX_BYTES
                    or audio_bytes / float(SPK_PCM_BYTES_PER_S) > SPK_TURN_MAX_S):
                self._send_json(413, {"error": "audio too large"})
                return
            del decoded

            history = _spk_turn_history(req.get("history"))
            stream = req.get("stream") is True
            system = _spk_turn_instruction(role, part, task)
            transcript, reply, llm_ms, llm_err = _spk_turn_understand(
                api_key, system, history, audio_b64, mime)
            if llm_err:
                self._send_json(502, {"error": "turn_failed", "reason": llm_err})
                return
            # One upstream reply call, one tick of the instance meter. Fast mode
            # stops here (one call per turn); natural mode adds the TTS tick.
            _ai_total_consume()
            transcript = (transcript or "").strip()
            reply = (reply or "").strip()
            # Never invent what was not heard: an empty transcript gets the
            # server's own repeat request, whatever the model tried to say.
            if not transcript or not reply:
                reply = _SPK_TURN_REPEAT

            if tts == "none":
                # The browser owns the voice: no TTS request is built, cached or
                # paid for. The reply text is the whole answer.
                total = int((time.time() - started) * 1000)
                if session_id and not known:
                    _spk_turn_session_mark(uid, session_id)
                    plans.speaking_add_mock(uid)
                _audit("speaking_turn", uid, _real_ip(self), self._rid,
                       {"part": part, "role": role, "ms": total,
                        "tts": "none"})
                ms = {"stt": 0, "llm": llm_ms, "tts": 0,
                      "total": total, "cached": False}
                if stream:
                    self._send_ndjson_start()
                    self._send_ndjson({
                        "type": "text", "transcript": transcript,
                        "reply": reply,
                        "ms": {"stt": 0, "llm": llm_ms},
                    })
                    self._send_ndjson({"type": "audio", "audio_b64": None,
                                       "mime": None, "ms": ms})
                    return
                self._send_json(200, {
                    "transcript": transcript,
                    "reply": reply,
                    "audio_b64": None,
                    "mime": None,
                    "ms": ms,
                })
                return

            if stream:
                # Text first, audio second: the examiner's words reach the UI
                # while TTS is still running, and playback starts on arrival.
                self._send_ndjson_start()
                self._send_ndjson({
                    "type": "text", "transcript": transcript, "reply": reply,
                    "ms": {"stt": 0, "llm": llm_ms},
                })
                wav, tts_ms, cached, tts_err = _spk_tts_cached(api_key, reply, voice)
                if tts_err:
                    # The text is already on its way, so do not fail the turn:
                    # tell the client to use the device voice. A dead TTS quota
                    # must degrade, not break the exam.
                    self._send_ndjson({"type": "audio", "audio_b64": None,
                                       "fallback": "device", "reason": tts_err,
                                       "ms": {"stt": 0, "llm": llm_ms, "tts": tts_ms}})
                    return
                total = int((time.time() - started) * 1000)
                if session_id and not known:
                    _spk_turn_session_mark(uid, session_id)
                    plans.speaking_add_mock(uid)
                _audit("speaking_turn", uid, _real_ip(self), self._rid,
                       {"part": part, "role": role, "ms": total, "cached": cached})
                self._send_ndjson({
                    "type": "audio",
                    "audio_b64": base64.b64encode(wav).decode("ascii"),
                    "mime": "audio/wav",
                    "ms": {"stt": 0, "llm": llm_ms, "tts": tts_ms,
                           "total": total, "cached": cached},
                })
                return

            wav, tts_ms, cached, tts_err = _spk_tts_cached(api_key, reply, voice)
            if tts_err:
                # Same degrade as the streaming path: the turn happened, only the
                # voice is missing. The client speaks the text itself.
                self._send_json(200, {
                    "transcript": transcript, "reply": reply, "audio_b64": None,
                    "mime": "audio/wav", "fallback": "device", "reason": tts_err,
                    "ms": {"stt": 0, "llm": llm_ms, "tts": tts_ms,
                           "total": int((time.time() - started) * 1000)},
                })
                return
            total = int((time.time() - started) * 1000)
            if session_id and not known:
                _spk_turn_session_mark(uid, session_id)
                plans.speaking_add_mock(uid)
            _audit("speaking_turn", uid, _real_ip(self), self._rid,
                   {"part": part, "role": role, "ms": total, "cached": cached})
            self._send_json(200, {
                "transcript": transcript,
                "reply": reply,
                "audio_b64": base64.b64encode(wav).decode("ascii"),
                "mime": "audio/wav",
                "ms": {"stt": 0, "llm": llm_ms, "tts": tts_ms,
                       "total": total, "cached": cached},
            })
            return

        # Client-reported spoken seconds. The browser is the clock (it owns the
        # session), so the ledger is advisory but persisted: 0600 per user,
        # one file per day, the same lock as progress.json.
        if path == "/api/speaking/minute":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._drain()
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            if self._clen() > SPK_MINUTE_MAX_BODY:
                self._drain()
                self._send_json(413, {"error": "payload too large"})
                return
            raw = self.rfile.read(self._clen()) if self._clen() > 0 else b""
            try:
                req = json.loads(raw.decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("not dict")
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"error": "invalid json"})
                return
            seconds = req.get("seconds")
            if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                    or not math.isfinite(seconds)
                    or seconds < 0 or seconds > SPK_MINUTE_MAX_CALL_S):
                self._send_json(422, {"error": "invalid seconds"})
                return
            rec = store.speaking_add(uid, _spk_today(), float(seconds))
            plans.speaking_add_seconds(uid, seconds)
            per_user_min, _total_min = _spk_min_limits()
            plan_limits = _plan_for(uid)["limits"]["speaking"]
            plan_used = plans.speaking_used(uid, plan_limits["window"])
            self._send_json(200, {
                "remaining_s": _spk_remaining_s(uid),
                "used_s": int(round(rec["seconds"])),
                "cap_s": per_user_min * 60,
                "plan_remaining_s": max(0, int(plan_limits["minutes"] * 60
                                           - plan_used["seconds"])),
            })
            return

        # --- S5: four-scale speaking report ------------------------------------
        # The transcript is data, not instructions: it reaches the text model
        # only inside the phase-17 fence. Pronunciation is NOT asked from the
        # model — it is mapped here from the Azure PA scores (or reported as
        # "not measured"). The report is also the only place the log entry is
        # born, and it is born on the client: a failure here never touches the
        # log, the streak or the progress document.
        if path == "/api/speaking/report":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._drain()
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            if self._clen() > SPK_REPORT_MAX_BODY:
                self._drain()
                self._send_json(413, {"error": "payload too large"})
                return
            if self._rate_limited("spk_rep:" + uid, SPK_REPORT_RATE_PER_MIN, 60):
                return
            raw = self.rfile.read(self._clen()) if self._clen() > 0 else b""
            try:
                req = json.loads(raw.decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("not dict")
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"error": "invalid_json"})
                return
            del raw
            clean, bad = speaking_report.validate_payload(req)
            if bad:
                self._send_json(422, {"error": bad})
                return
            request_id = clean["request_id"]
            cached = _spk_report_cache_get(uid, request_id)
            if cached is not None:
                # Same request_id: replay the exact result, no second LLM call.
                self._send_json(200, cached)
                return
            # Phase 30: the report can run on the user's own key too. With a
            # user key the daily server quota is skipped (their cost) but the
            # per-minute limit above and the hourly account cap still apply.
            byo, byo_err = _byo_from_headers(self.headers)
            if byo_err:
                self._send_json(400, {"error": byo_err})
                return
            if byo:
                if self._rate_limited("ai:byo:hour:user:" + uid, BYO_RATE_PER_HOUR,
                                      3600, "user"):
                    return
            else:
                if not (os.environ.get("B2_AI_KEY") or "").strip():
                    # No shared text-model key: fail before spending a quota unit.
                    self._send_json(503, {"error": "ai_not_configured"})
                    return
                # The report is an LLM call, so it shares the writing allowance
                # (free: 3/day, pro: 60/month). No separate counter to drift.
                if not self._writing_gate(uid, _real_ip(self)):
                    return
            # Only the candidate's own turns are graded. Examiner and partner
            # turns are context for the proxies, never text for the model.
            candidate = speaking_report.candidate_text(clean["transcript"])
            abuse = _ai_abuse_reason(candidate)
            if abuse:
                # An injection attempt is audited but still graded as text:
                # the fence is the barrier, not a heuristic that can drop a
                # legitimate session.
                _audit("ai_blocked", uid, _real_ip(self), self._rid,
                       {"reason": abuse, "chars": len(candidate)})
            user_block, _nonce = speaking_report.report_message(
                _fit_ai_text(candidate),
                dialogue=_fit_ai_text(speaking_report.dialogue_text(clean["transcript"]))
                if clean["interactive"] else None)
            if not byo:
                self._writing_consume(uid, _real_ip(self))
            content, ai_err = _ai_text_complete(
                speaking_report.system_prompt(clean["interactive"]), user_block, byo=byo)
            if ai_err:
                code = 503 if ai_err == "ai_not_configured" else 502
                self._send_json(code, {"error": ai_err})
                return
            if content is None or len(content.encode("utf-8")) > AI_OUTPUT_MAX_BYTES:
                self._send_json(502, {"error": "bad_model_output"})
                return
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
            if _leaks_system_prompt(text, strong_only=True):
                _audit("ai_blocked", uid, _real_ip(self), self._rid,
                       {"reason": "prompt_leak"})
                self._send_json(502, {"error": "unsafe_output"})
                return
            try:
                model_obj = json.loads(text)
            except (ValueError, TypeError):
                self._send_json(502, {"error": "bad_model_output"})
                return
            graded = speaking_report.parse_model_output(model_obj, clean["interactive"])
            if graded is None:
                # Never echo the raw output: it is untrusted text.
                self._send_json(502, {"error": "bad_model_output"})
                return
            pron = speaking_report.band_from_pa(clean["pa"])
            result = {
                "bands": {
                    "grammar_vocabulary": graded["bands"]["grammar_vocabulary"],
                    "discourse_management": graded["bands"]["discourse_management"],
                    "pronunciation": pron["band"],
                    # Phase 35: graded only when the client declares that the
                    # session had an interlocutor (a partner voice). Without that
                    # declaration it stays null and the UI says "not scored".
                    "interactive_communication":
                        graded["bands"].get("interactive_communication"),
                },
                "derived": {
                    "pronunciation_score": pron["score"],
                    "pronunciation_source": pron["source"],
                },
                "proxies": speaking_report.proxies(clean["transcript"],
                                                   clean["metrics"]),
                "evidence": graded["evidence"],
                "fixes": graded["fixes"],
                "worst": pron["worst"],
                "part": clean["part"],
                "duration_s": clean["duration_s"],
                "metrics": clean["metrics"],
                "stored_transcript": False,
                "request_id": request_id,
            }
            if clean["store_transcript"]:
                try:
                    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
                    stamp += f"-{int(time.time() * 1000) % 1000:03d}"
                    store.write_speaking_transcript(uid, stamp, {
                        "type": "sp",
                        "date": date.today().isoformat(),
                        "part": clean["part"],
                        "duration_s": clean["duration_s"],
                        "request_id": request_id,
                        "transcript": clean["transcript"],
                        "metrics": clean["metrics"],
                        "bands": result["bands"],
                        "derived": result["derived"],
                    })
                    result["stored_transcript"] = True
                except (OSError, ValueError):
                    result["stored_transcript"] = False
            _spk_report_cache_put(uid, request_id, result)
            self._send_json(200, result)
            return

        # --- S2: Azure Pronunciation Assessment --------------------------------
        # One short candidate turn in, phoneme scores out. The audio is forwarded
        # and discarded inside this handler: never written to data/, never logged,
        # never kept in memory past the response. The Azure key never reaches the
        # browser. Without a key the endpoint says so (503) and the Pronunciation
        # band stays "not measured" instead of being guessed.
        if path == "/api/speaking/pa":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            uid, auth_err = self._auth()
            if not uid:
                self._drain()
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            api_key = _spk_azure_key()
            url = _spk_pa_url()
            if not api_key or not url:
                # One line, no secret: just which knob is missing.
                missing = "B2_SPK_AZURE_KEY" if not api_key else "B2_SPK_AZURE_REGION"
                line = (f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                        f"rid={self._rid} speaking/pa disabled: {missing} missing\n")
                with _LOG_LOCK:
                    print(line, end="", flush=True)
                self._drain()
                self._send_json(503, {"error": "speech_not_configured"})
                return
            if self._rate_limited("spk_pa:" + uid, SPK_PA_RATE_PER_MIN, 60):
                return
            raw = self.rfile.read(self._clen()) if self._clen() > 0 else b""
            try:
                req = json.loads(raw.decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("not dict")
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"error": "invalid json"})
                return
            del raw
            fmt = req.get("format")
            fmt = fmt.strip().lower() if isinstance(fmt, str) else ""
            if fmt not in ("wav", "ogg"):
                _audit("pa_rejected", uid, _real_ip(self), self._rid,
                       {"reason": "format"})
                self._send_json(422, {"error": "unsupported format"})
                return
            audio_b64 = req.get("audio_b64")
            if not isinstance(audio_b64, str) or not audio_b64:
                _audit("pa_rejected", uid, _real_ip(self), self._rid,
                       {"reason": "missing_audio"})
                self._send_json(422, {"error": "audio_b64 required"})
                return
            if len(audio_b64) > SPK_PA_MAX_B64:
                _audit("pa_rejected", uid, _real_ip(self), self._rid,
                       {"reason": "too_large"})
                self._send_json(413, {"error": "audio too large"})
                return
            try:
                audio = base64.b64decode(audio_b64, validate=True)
            except (ValueError, binascii.Error):
                _audit("pa_rejected", uid, _real_ip(self), self._rid,
                       {"reason": "invalid_base64"})
                self._send_json(422, {"error": "invalid base64"})
                return
            ok, reason = speech.validate_audio(audio, fmt)
            if not ok:
                del audio
                _audit("pa_rejected", uid, _real_ip(self), self._rid,
                       {"reason": "invalid_audio"})
                self._send_json(422, {"error": "invalid audio", "reason": reason})
                return
            ref_text = req.get("ref_text")
            ref_text = ref_text.strip()[:500] if isinstance(ref_text, str) else ""
            quota_key = "user:" + uid
            if _spk_pa_quota_left(quota_key) <= 0:
                del audio
                reset = (date.today() + timedelta(days=1)).isoformat()
                self._send_json(429, {"error": "daily pronunciation quota reached",
                                      "reset": reset})
                return
            _spk_pa_quota_consume(quota_key)
            ctype = ("audio/wav; codecs=audio/pcm; samplerate=16000"
                     if fmt == "wav" else "audio/ogg; codecs=opus")
            up_req = urllib.request.Request(
                url,
                data=audio,
                headers={
                    "Ocp-Apim-Subscription-Key": api_key,
                    "Pronunciation-Assessment": speech.pa_config_header(ref_text),
                    "Content-Type": ctype,
                },
                method="POST",
            )
            try:
                # No retry on purpose: a second attempt is a second bill.
                with urllib.request.urlopen(up_req, timeout=SPK_PA_TIMEOUT) as resp:
                    up_raw = resp.read(1024 * 1024)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
                del audio
                self._send_json(502, {"error": "upstream provider failed"})
                return
            del audio
            try:
                up_json = json.loads(up_raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send_json(502, {"error": "invalid provider response"})
                return
            del up_raw
            result = speech.parse_pa_response(up_json)
            if not result.get("ok"):
                self._send_json(422, {"error": result.get("error", "recognition_failed")})
                return
            self._send_json(200, result)
            return

        # Phase 30: "Test connection" for a user-supplied provider key. Sends
        # one token of work and answers only {ok, model} or {ok:false, code}:
        # never the key and never the provider's body.
        if path == "/api/ai/provider/test":
            if self.command != "POST":
                self._send_json(405, {"error": "method not allowed"})
                return
            self._drain()
            byo, byo_err = _byo_from_headers(self.headers)
            if byo_err:
                self._send_json(400, {"ok": False, "code": byo_err})
                return
            if not byo:
                self._send_json(400, {"ok": False, "code": "provider_key_required"})
                return
            auth_uid = None
            if self._bearer():
                auth_uid, _auth_err = self._auth()
            account = ("user:" + auth_uid) if auth_uid else ("ip:" + _real_ip(self))
            if self._rate_limited("ai:byo:hour:" + account, BYO_RATE_PER_HOUR, 3600,
                                  "user" if auth_uid else "ip"):
                return
            if self._rate_limited("ai:byo:test:" + account, BYO_TEST_RATE_PER_MIN, 60,
                                  "user" if auth_uid else "ip"):
                return
            payload = {
                "model": byo["model"],
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
            body, up_err = _provider_complete(byo["base"], byo["key"], byo["model"], payload)
            if up_err or "choices" not in body:
                self._send_json(502, {"ok": False, "code": up_err or "upstream_failed"})
                return
            self._send_json(200, {"ok": True, "model": byo["model"]})
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
            raw_text = req.get("text")
            # `task` is the strictly validated API (lowercase slug). `kind` is
            # the legacy field still sent by old clients: it keeps its original
            # 400 contract but goes through the same sanitising, abuse and
            # output guards, so it is not a way around the fase-17 protections.
            has_task = "task" in req
            if not isinstance(raw_text, str):
                self._send_json(422, {"error": "invalid text"})
                return
            if has_task:
                task_raw = req.get("task")
                task = task_raw.strip().lower() if isinstance(task_raw, str) else ""
                if task not in AI_TASKS:
                    self._send_json(422, {"error": "unknown task"})
                    return
                kind = task.capitalize()
            else:
                kind = req.get("kind")
                if kind not in AI_ALLOWED_KINDS:
                    self._send(400, json.dumps({"error": "invalid kind"}).encode("utf-8"), "application/json; charset=utf-8")
                    return
                task = kind.lower()
            if len(raw_text) > AI_TEXT_HARD_MAX_CHARS:
                self._send_json(413, {"error": "text too large"})
                return
            if _looks_binary(raw_text):
                _audit("ai_blocked", "", client_ip, self._rid,
                       {"reason": "binary", "chars": len(raw_text)})
                self._send_json(422, {"error": "text looks binary"})
                return
            clean_text = _sanitize_ai_text(raw_text)
            abuse = _ai_abuse_reason(clean_text)
            if abuse:
                _audit("ai_blocked", "", client_ip, self._rid,
                       {"reason": abuse, "chars": len(clean_text)})
                self._send_json(422, {"error": "off_topic", "reason": abuse})
                return
            if has_task:
                words = _word_count(clean_text)
                if (len(clean_text) < AI_TEXT_MIN_CHARS
                        or len(clean_text) > AI_TEXT_MAX_CHARS
                        or words < AI_TEXT_MIN_WORDS or words > AI_TEXT_MAX_WORDS):
                    self._send_json(422, {"error": "text must be between 40 and 700 words"})
                    return
            elif not (50 <= len(raw_text.strip()) <= 3000) or not (50 <= len(raw_text) <= 3000):
                self._send(400, json.dumps({"error": "text must be between 50 and 3000 chars"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            # Three key paths, in order of precedence:
            #   1. X-Provider-* headers (phase 30): the user's own key, their
            #      cost, so the daily server quota is skipped. The key lives in
            #      this request only and is never logged or stored.
            #   2. `provider_key`/`key` in the body: the same deal, kept for
            #      older clients.
            #   3. The owner's key: the daily quota protects it.
            byo, byo_err = _byo_from_headers(self.headers)
            if byo_err:
                self._send_json(400, {"error": byo_err})
                return
            legacy_key = req.get("provider_key") or req.get("key") or ""
            legacy_key = legacy_key.strip() if isinstance(legacy_key, str) else ""
            env_prov = B2_AI_PROVIDER if B2_AI_PROVIDER != DEFAULT_AI_PROVIDER else os.environ.get("B2_AI_PROVIDER", DEFAULT_AI_PROVIDER)
            requested = req.get("provider") or env_prov or DEFAULT_AI_PROVIDER
            requested = requested.strip().lower() if isinstance(requested, str) else DEFAULT_AI_PROVIDER
            auth_uid = None
            if self._bearer():
                auth_uid, _auth_err = self._auth()
            user_key = False
            if byo:
                api_key, base, model, wire = byo["key"], byo["base"], byo["model"], "openai"
                user_key = True
            elif legacy_key:
                if (len(legacy_key) > BYO_KEY_MAX
                        or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in legacy_key)):
                    self._send_json(400, {"error": "invalid_provider_key"})
                    return
                if requested not in ("deepseek", "gemini"):
                    self._send_json(400, {"error": "invalid provider"})
                    return
                api_key, wire = legacy_key, requested
                default_base = DEFAULT_DEEPSEEK_BASE if wire == "deepseek" else DEFAULT_GEMINI_BASE
                default_model = DEFAULT_DEEPSEEK_MODEL if wire == "deepseek" else DEFAULT_GEMINI_MODEL
                base = (B2_AI_BASE or os.environ.get("B2_AI_BASE") or default_base).strip()
                model = (req.get("model") or B2_AI_MODEL or os.environ.get("B2_AI_MODEL") or default_model).strip()
                user_key = True
            else:
                if requested not in ("deepseek", "gemini"):
                    self._send_json(400, {"error": "invalid provider"})
                    return
                api_key = (os.environ.get("B2_AI_KEY") or "").strip()
                if not api_key:
                    self._send_json(502, {"error": "missing provider key"})
                    return
                # Phase 31: the plan decides the allowance (free 3/day, pro
                # 60/month); B2_AI_DAILY_TOTAL still caps the whole instance.
                if not self._writing_gate(auth_uid, client_ip):
                    return
                self._writing_consume(auth_uid, client_ip)
                wire = requested
                default_base = DEFAULT_DEEPSEEK_BASE if wire == "deepseek" else DEFAULT_GEMINI_BASE
                default_model = DEFAULT_DEEPSEEK_MODEL if wire == "deepseek" else DEFAULT_GEMINI_MODEL
                base = (B2_AI_BASE or os.environ.get("B2_AI_BASE") or default_base).strip()
                model = (req.get("model") or B2_AI_MODEL or os.environ.get("B2_AI_MODEL") or default_model).strip()
            if user_key:
                # The user's key pays, so no daily quota — but the per-IP rate
                # limit above and this per-account ceiling still apply.
                account = ("user:" + auth_uid) if auth_uid else ("ip:" + client_ip)
                if self._rate_limited("ai:byo:hour:" + account, BYO_RATE_PER_HOUR, 3600,
                                      "user" if auth_uid else "ip"):
                    return
            # Fresh nonce per request: the fence cannot be predicted or
            # pre-closed by a text prepared in advance.
            student_block, _nonce = prompts.student_message(_fit_ai_text(clean_text), kind)
            if wire == "gemini":
                payload = {
                    "contents": [{"parts": [{"text": f"{prompts.WRITING_SYSTEM}\n\n{student_block}"}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
                }
            else:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompts.WRITING_SYSTEM},
                        {"role": "user", "content": student_block},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                }
            up_json, up_err = _provider_complete(base, api_key, model, payload, wire=wire)
            if up_err:
                self._send_json(502, {"error": "upstream provider failed"})
                return
            try:
                if wire == "gemini":
                    cand_text = up_json["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    cand_text = up_json["choices"][0]["message"]["content"]
                if not isinstance(cand_text, str):
                    raise ValueError("not text")
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                self._send_json(422, {"error": "invalid model json"})
                return
            if len(cand_text.encode("utf-8")) > AI_OUTPUT_MAX_BYTES:
                self._send_json(502, {"error": "model output too large"})
                return
            cand_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", cand_text.strip())
            if _leaks_system_prompt(cand_text):
                _audit("ai_blocked", "", client_ip, self._rid,
                       {"reason": "prompt_leak", "chars": len(cand_text)})
                self._send_json(502, {"error": "unsafe output"})
                return
            try:
                model_obj = json.loads(cand_text)
            except (ValueError, TypeError):
                self._send(422, json.dumps({"error": "invalid model json"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            if isinstance(model_obj, dict) and model_obj.get("refuse") is True:
                reason = model_obj.get("reason")
                if reason not in ("not_a_writing_task", "cannot_reveal_instructions"):
                    reason = "not_a_writing_task"
                self._send_json(200, {"refused": True, "reason": reason})
                return
            validated = _validate_ai_payload(model_obj)
            if not validated:
                self._send(422, json.dumps({"error": "schema validation failed"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            validated["model"] = model
            self._send(200, json.dumps(validated, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Product telemetry: {sid, events:[{n, t, p}]} -> append-only JSONL.
        # No auth required (visitor events matter); a valid token associates
        # uid, an invalid one is ignored (uid:null, never 401 here).
        if path == "/api/events":
            if self.command != "POST":
                self._send(405, b"method not allowed", "text/plain")
                return
            clen = self._clen()
            if clen > EVENTS_MAX_BYTES:
                self._drain()
                self._send_json(413, {"error": "events payload too large"})
                return
            if self._rate_limited("events:" + _real_ip(self), EVENTS_BATCH_LIMIT, 3600):
                return
            raw = self.rfile.read(clen)
            try:
                req = json.loads(raw.decode("utf-8"))
                if not isinstance(req, dict):
                    raise ValueError("not dict")
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"error": "invalid json"})
                return
            events = req.get("events")
            if not isinstance(events, list):
                self._send_json(400, {"error": "invalid events"})
                return
            if len(events) > EVENTS_MAX_BATCH:
                self._send_json(413, {"error": "too many events"})
                return
            sid = req.get("sid")
            sid = str(sid)[:64] if isinstance(sid, (str, int, float)) and not isinstance(sid, bool) else ""
            uid = None
            if self._bearer():
                try:
                    got, _auth_err = self._auth()
                    uid = got or None
                except Exception:
                    uid = None
            clean = []
            for ev in events:
                parsed = _sanitize_event(ev)
                if parsed:
                    clean.append(parsed)
            # Demo mode writes nothing to data/: events are accepted and dropped.
            if clean and not _is_demo():
                _append_events(clean, sid, uid, _ip_hash(_real_ip(self)))
            self._send_json(200, {"ok": True, "accepted": len(clean)})
            return

        # Owner-only product metrics (aggregates only, never stacks or content)
        if path == "/api/metrics":
            if self.command != "GET":
                self._send(405, b"method not allowed", "text/plain")
                return
            uid, auth_err = self._auth()
            if not uid:
                self._send_json(401, {"error": auth_err or "invalid session"})
                return
            if uid != "owner":
                self._send_json(403, {"error": "owner only"})
                return
            self._send_json(200, build_metrics())
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
class B2HTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer tuned for hundreds of students on one Pi 5.

    daemon_threads=True so a restart never waits on idle keep-alive threads;
    a 256-deep accept backlog absorbs bursts above the 512 live-connection cap.
    """
    daemon_threads = True
    request_queue_size = REQUEST_QUEUE_SIZE


if __name__ == "__main__":
    if not _is_demo():
        migrate_legacy()
    srv = B2HTTPServer((B2_HOST, PORT), H)
    print(f"B2First portal at http://{B2_HOST}:{srv.server_address[1]} (root={ROOT})")
    srv.serve_forever()
