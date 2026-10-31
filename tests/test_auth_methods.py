"""Phase 34 acceptance: Google sign-in and passkeys.

Runs a private server with a temporary DATA_DIR and a stubbed Google token/JWKS
endpoint.  The RSA key used to sign the id_token is generated here with the
stdlib, so no network and no Google credentials are required.  The passkey
part uses Chromium's CDP virtual authenticator:

    cd tests && uv run --with playwright python test_auth_methods.py
"""
import hashlib
import http.client
import io
import json
import math
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# ---------------------------------------------------------------------------
# Google credentials: use the real ones when present, otherwise a local stub.
# The token endpoint and JWKS are always local, so a stub client id is enough
# to exercise every check.  With B2_TEST_GOOGLE_STUB=0 and no client id the
# suite skips loudly instead of pretending to pass.
# ---------------------------------------------------------------------------
CLIENT_ID = os.environ.get("B2_GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("B2_GOOGLE_CLIENT_SECRET", "").strip()
if not CLIENT_ID:
    if os.environ.get("B2_TEST_GOOGLE_STUB", "1") != "1":
        print("SKIP: no client id")
        sys.exit(0)
    CLIENT_ID = "test-client-id.apps.googleusercontent.com"
    print("NOTE: no B2_GOOGLE_CLIENT_ID; using a locally stubbed client id")
if not CLIENT_SECRET:
    CLIENT_SECRET = "test-client-secret"
SECRET_CODE = "google-code-secret-123"
RAW_EMAIL = "alice@example.com"

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else ("FAIL " + (detail or name))
    if not cond:
        failed.append(name)


# ---------------------------------------------------------------------------
# RSA key generation + RS256 signing (stdlib only)
# ---------------------------------------------------------------------------
_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)


def _probably_prime(n, rounds=24):
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d = n - 1
    s = 0
    while d % 2 == 0:
        s += 1
        d //= 2
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits):
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if candidate % 65537 != 0 and _probably_prime(candidate):
            return candidate


def _rsa_key(bits=1024):
    e = 65537
    while True:
        p = _prime(bits // 2)
        q = _prime(bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if math.gcd(e, phi) != 1:
            continue
        n = p * q
        return n, e, pow(e, -1, phi)


RSA_N, RSA_E, RSA_D = _rsa_key()


def _b64u(raw):
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _int_bytes(value):
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


JWKS = {"keys": [{
    "kty": "RSA", "alg": "RS256", "use": "sig", "kid": "test-key",
    "n": _b64u(_int_bytes(RSA_N)), "e": _b64u(_int_bytes(RSA_E)),
}]}


def make_id_token(claims):
    header = {"alg": "RS256", "kid": "test-key", "typ": "JWT"}
    head = _b64u(json.dumps(header, separators=(",", ":")).encode())
    body = _b64u(json.dumps(claims, separators=(",", ":")).encode())
    signed = (head + "." + body).encode("ascii")
    size = (RSA_N.bit_length() + 7) // 8
    digest_info = (bytes.fromhex("3031300d060960864801650304020105000420")
                   + hashlib.sha256(signed).digest())
    encoded = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), RSA_D, RSA_N).to_bytes(size, "big")
    return head + "." + body + "." + _b64u(signature)


def claims_for(nonce, sub="google-sub-1", aud=None, iss="https://accounts.google.com",
               exp=None):
    now = int(time.time())
    return {
        "iss": iss or "https://accounts.google.com",
        "aud": aud or CLIENT_ID,
        "sub": sub,
        "email": RAW_EMAIL,
        "email_verified": True,
        "name": "Alice Google",
        "iat": now,
        "exp": int(exp if exp is not None else now + 300),
        "nonce": nonce,
    }


# ---------------------------------------------------------------------------
# Stub Google endpoints
# ---------------------------------------------------------------------------
STUB = {"id_token": "", "form": {}}


class GoogleStub(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/jwks":
            self._json(200, JWKS)
            return
        if path == "/authorize":
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != "/token":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length)
        STUB["form"] = parse_qs(raw.decode("utf-8"))
        self._json(200, {
            "access_token": "stub-access-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "id_token": STUB["id_token"],
        })


stub = ThreadingHTTPServer(("127.0.0.1", 0), GoogleStub)
STUB_PORT = stub.server_address[1]
threading.Thread(target=stub.serve_forever, daemon=True).start()

os.environ["B2_DEMO"] = "0"
os.environ["B2_REGISTER"] = "open"
# This suite deliberately makes many auth calls in one minute; keep the
# anti-abuse buckets out of the way so the i18n scanner can still log in.
os.environ["B2_RATE_IP_AUTH"] = "1000"
os.environ["B2_RATE_IP_ANON"] = "1000"
os.environ["B2_RATE_USER_API"] = "1000"
os.environ["B2_GOOGLE_CLIENT_ID"] = CLIENT_ID
os.environ["B2_GOOGLE_CLIENT_SECRET"] = CLIENT_SECRET
os.environ["B2_GOOGLE_TOKEN_URL"] = f"http://127.0.0.1:{STUB_PORT}/token"
os.environ["B2_GOOGLE_JWKS_URL"] = f"http://127.0.0.1:{STUB_PORT}/jwks"
os.environ["B2_GOOGLE_AUTH_URL"] = f"http://127.0.0.1:{STUB_PORT}/authorize"

_tmp = tempfile.mkdtemp(prefix="b2auth-")
os.environ["DATA_DIR"] = _tmp

import server as S  # noqa: E402
import store  # noqa: E402
import webauthn  # noqa: E402

S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.B2_DEMO = False
S.B2_REGISTER = "open"

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
PORT = srv.server_address[1]
S.PORT = PORT
threading.Thread(target=srv.serve_forever, daemon=True).start()

# WebAuthn requires a secure-context origin whose RP ID is a real domain;
# localhost is the one loopback name Chromium accepts.
os.environ["B2_PUBLIC_URL"] = f"http://localhost:{PORT}"
os.environ["B2_RP_ID"] = "localhost"
BASE_LOCAL = f"http://localhost:{PORT}"
BASE_IP = f"http://127.0.0.1:{PORT}"


def req(method, path, body=None, token=None):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
    conn.request(method, path, body=data, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    status = response.status
    hdrs = dict(response.getheaders())
    conn.close()
    return status, hdrs, raw


def header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def json_body(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}


def google_begin():
    status, headers, _ = req("GET", "/api/auth/google/start")
    location = header(headers, "Location")
    query = parse_qs(urlsplit(location).query)
    state = (query.get("state") or [""])[0]
    pending = S._GOOGLE_STATES.get(state)
    return status, location, query, state, (pending or {}).get("nonce", "")


def callback(state, code=SECRET_CODE):
    return req("GET", "/api/auth/google/callback?" + "&".join([
        "code=" + quote(code, safe=""),
        "state=" + quote(state, safe=""),
    ]))


class Captured:
    def __enter__(self):
        self._old = sys.stdout
        self.buffer = io.StringIO()
        sys.stdout = self.buffer
        return self

    def __exit__(self, *_exc):
        sys.stdout = self._old
        self.text = self.buffer.getvalue()


# ---------------------------------------------------------------------------
# 1. /api/config advertises Google only because B2_GOOGLE_CLIENT_ID is set.
# ---------------------------------------------------------------------------
status, _headers, raw = req("GET", "/api/config")
config = json_body(raw)
check("G1_config_google", status == 200 and config.get("google") is True, str(config))

# ---------------------------------------------------------------------------
# 2. Start builds a PKCE authorization request and a single-use state.
# ---------------------------------------------------------------------------
status, location, query, state, nonce = google_begin()
check("G2_start_302", status == 302 and bool(state), f"{status} {location}")
check("G3_start_google", location.startswith(f"http://127.0.0.1:{STUB_PORT}/authorize?"),
      location)
check("G4_scope", (query.get("scope") or [""])[0] == "openid email profile", location)
check("G5_pkce_s256",
      (query.get("code_challenge_method") or [""])[0] == "S256"
      and len((query.get("code_challenge") or [""])[0]) >= 43, location)
check("G6_redirect_uri",
      (query.get("redirect_uri") or [""])[0] == f"{BASE_LOCAL}/api/auth/google/callback",
      location)
check("G7_nonce", bool(nonce), "missing nonce")

# ---------------------------------------------------------------------------
# 3. First sign-in of an unknown Google account: explicit confirmation,
#    then create with a chosen local username and the email hash opt-in.
# ---------------------------------------------------------------------------
status, location, query, state, nonce = google_begin()
valid_token = make_id_token(claims_for(nonce))
STUB["id_token"] = valid_token
with Captured() as captured:
    status, headers, raw = callback(state)
location = header(headers, "Location")
link_query = parse_qs(urlsplit(location).query)
link_ticket = (link_query.get("google_link") or [""])[0]
check("G8_unknown_redirects_to_confirmation",
      status == 302 and bool(link_ticket) and "google_login" not in link_query,
      f"{status} {location}")
check("G9_code_exchange_used_pkce",
      STUB["form"].get("grant_type", [""])[0] == "authorization_code"
      and bool(STUB["form"].get("code_verifier", [""])[0])
      and STUB["form"].get("code", [""])[0] == SECRET_CODE,
      str({k: v[:1] for k, v in STUB["form"].items() if k != "client_secret"}))

status, _headers, raw = req("GET", "/api/auth/google/pending?ticket=" + quote(link_ticket))
pending = json_body(raw)
check("G10_pending_suggests_name",
      status == 200 and bool(pending.get("suggested")) and pending.get("has_email") is True,
      f"{status} {pending}")

users_path = os.path.join(_tmp, "users.json")
users_before = json.load(open(users_path, encoding="utf-8")) if os.path.exists(users_path) else {}
check("G11a_no_silent_account",
      all((u.get("name") or "") != "google-alice" for u in users_before.values()),
      str([u.get("name") for u in users_before.values()]))

status, _headers, raw = req("POST", "/api/auth/google/complete", {
    "ticket": link_ticket, "mode": "create", "name": "google-alice",
    "store_email": True,
})
created = json_body(raw)
uid = created.get("id", "")
token = created.get("token", "")
check("G11_create_explicit",
      status == 200 and uid and token and created.get("name") == "google-alice",
      f"{status} {created}")
check("G12_session_shape",
      set(created) >= {"id", "name", "color", "token"}, str(sorted(created)))

oauth_path = os.path.join(_tmp, "oauth.json")
oauth_map = json.load(open(oauth_path, encoding="utf-8"))
users = json.load(open(os.path.join(_tmp, "users.json"), encoding="utf-8"))
record = users.get(uid, {})
check("G13_oauth_mapping", oauth_map.get("google-sub-1") == uid, str(oauth_map))
check("G13b_oauth_private",
      (os.stat(oauth_path).st_mode & 0o777) == 0o600,
      oct(os.stat(oauth_path).st_mode & 0o777))
check("G14_no_password_fallback", record.get("password_set") is False, str(record.get("password_set")))
check("G15_email_hash_only",
      record.get("email_hash") == hashlib.sha256(RAW_EMAIL.encode()).hexdigest()
      and RAW_EMAIL not in json.dumps(users), str(record.get("email_hash")))
check("G16_password_login_refused",
      req("POST", "/api/login", {"name": "google-alice", "password": "anything-123"} )[0] == 401)

# A second unknown Google account that does NOT opt in must store no email hash.
_s, _loc, _q, state, nonce = google_begin()
STUB["id_token"] = make_id_token(claims_for(nonce, sub="google-sub-no-email"))
status, headers, raw = callback(state, code="no-email-code")
ticket = (parse_qs(urlsplit(header(headers, "Location")).query).get("google_link") or [""])[0]
status, _headers, raw = req("POST", "/api/auth/google/complete", {
    "ticket": ticket, "mode": "create", "name": "google-bob", "store_email": False,
})
bob = json_body(raw)
users = json.load(open(os.path.join(_tmp, "users.json"), encoding="utf-8"))
bob_record = users.get(bob.get("id", ""), {})
check("G16a_no_optin_no_email",
      status == 200 and bool(bob.get("id")) and "email_hash" not in bob_record,
      str(bob_record))

# ---------------------------------------------------------------------------
# 4. Second sign-in of the same sub: one-time login ticket -> session.
# ---------------------------------------------------------------------------
status, location, query, state, nonce = google_begin()
STUB["id_token"] = make_id_token(claims_for(nonce))
status, headers, raw = callback(state, code="second-code")
location = header(headers, "Location")
login_query = parse_qs(urlsplit(location).query)
login_ticket = (login_query.get("google_login") or [""])[0]
check("G17_known_redirects_to_session",
      status == 302 and bool(login_ticket) and "google_link" not in login_query,
      f"{status} {location}")
status, _headers, raw = req("GET", "/api/auth/google/session?ticket=" + quote(login_ticket))
session = json_body(raw)
check("G18_known_session", status == 200 and session.get("id") == uid
      and bool(session.get("token")), f"{status} {session}")
status, _headers, raw = req("GET", "/api/me", token=session.get("token", ""))
check("G19_session_token_works", status == 200, f"{status} {raw[:80]}")
check("G20_ticket_is_single_use",
      req("GET", "/api/auth/google/session?ticket=" + quote(login_ticket))[0] == 400)

# ---------------------------------------------------------------------------
# 5. Every tampered id_token is rejected with 400.
# ---------------------------------------------------------------------------
def rejected(name, builder, sub="google-sub-reject"):
    _s, _loc, _q, state, nonce = google_begin()
    token = builder(nonce)
    STUB["id_token"] = token
    status, _headers, raw = callback(state, code="reject-code")
    check(name, status == 400, f"{status} {raw[:120]}")


def tampered(nonce):
    token = make_id_token(claims_for(nonce))
    head, body, signature = token.split(".")
    raw = bytearray(urlsafe_b64decode(signature + "=" * (-len(signature) % 4)))
    raw[len(raw) // 2] ^= 0x01
    return head + "." + body + "." + _b64u(bytes(raw))


rejected("G21_bad_signature", tampered)
rejected("G22_wrong_aud", lambda n: make_id_token(claims_for(n, aud="other-client")))
rejected("G23_wrong_iss",
         lambda n: make_id_token(claims_for(n, iss="https://evil.example")))
rejected("G24_expired", lambda n: make_id_token(claims_for(n, exp=time.time() - 60)))
rejected("G25_wrong_nonce", lambda n: make_id_token(claims_for(n + "-wrong")))

_s, _loc, _q, reuse_state, reuse_nonce = google_begin()
STUB["id_token"] = make_id_token(claims_for(reuse_nonce, sub="google-sub-reuse"))
first = callback(reuse_state, code="reuse-code")[0]
second = callback(reuse_state, code="reuse-code")[0]
check("G26_state_single_use", first == 302 and second == 400, f"{first} then {second}")

# ---------------------------------------------------------------------------
# 6. Password login still works and a password change revokes every session.
# ---------------------------------------------------------------------------
PASS_USER = "password-user"
PASS_OLD = "password-old-9!"
PASS_NEW = "password-new-9!"
status, _headers, raw = req("POST", "/api/register",
                            {"name": PASS_USER, "password": PASS_OLD})
registered = json_body(raw)
tok1 = registered.get("token", "")
status, _headers, raw = req("POST", "/api/login",
                            {"name": PASS_USER, "password": PASS_OLD})
tok2 = json_body(raw).get("token", "")
check("P1_password_login", status == 200 and bool(tok1) and bool(tok2), raw[:100])
status, _headers, raw = req("POST", "/api/password",
                            {"current": PASS_OLD, "next": PASS_NEW}, token=tok1)
fresh = json_body(raw)
check("P2_password_change", status == 200 and bool(fresh.get("token")), raw[:120])
check("P3_old_sessions_revoked",
      req("GET", "/api/me", token=tok1)[0] == 401
      and req("GET", "/api/me", token=tok2)[0] == 401)
check("P4_fresh_token_valid", req("GET", "/api/me", token=fresh.get("token", ""))[0] == 200)
check("P5_old_password_refused",
      req("POST", "/api/login", {"name": PASS_USER, "password": PASS_OLD})[0] == 401)
check("P6_new_password_works",
      req("POST", "/api/login", {"name": PASS_USER, "password": PASS_NEW})[0] == 200)

# ---------------------------------------------------------------------------
# 7. No secret in data/ or in the captured server output.
# ---------------------------------------------------------------------------
def tree_text(root):
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    yield path, handle.read()
            except (OSError, UnicodeDecodeError):
                continue


secrets_to_hide = [SECRET_CODE, valid_token, CLIENT_SECRET, RAW_EMAIL]
disk_hits = [(needle, path) for needle in secrets_to_hide
             for path, text in tree_text(_tmp) if needle in text]
log_hits = [needle for needle in secrets_to_hide if needle in captured.text]
check("N1_no_secret_on_disk", not disk_hits, str(disk_hits)[:200])
check("N2_no_secret_in_log", not log_hits, str(log_hits)[:200])

# ---------------------------------------------------------------------------
# 8. Passkeys with Chromium's virtual authenticator.
# ---------------------------------------------------------------------------
PASSKEY_USER = "passkey-user"
PASSKEY_PASS = "passkey-user-9!"
status, _headers, raw = req("POST", "/api/register",
                            {"name": PASSKEY_USER, "password": PASSKEY_PASS})
passkey_account = json_body(raw)
passkey_uid = passkey_account.get("id", "")
passkey_token = passkey_account.get("token", "")
check("K1_passkey_account", status == 200 and bool(passkey_uid) and bool(passkey_token),
      f"{status} {raw[:120]}")

status, _headers, raw = req("POST", "/api/webauthn/register/begin",
                            {"password": "wrong-password", "label": "Laptop"}, token=passkey_token)
check("K2_register_needs_password", status == 401, f"{status} {raw[:100]}")
status, _headers, raw = req("POST", "/api/webauthn/register/begin",
                            {"password": PASSKEY_PASS, "label": "Laptop"}, token=passkey_token)
begin = json_body(raw)
check("K3_register_begin",
      status == 200 and bool(begin.get("publicKey", {}).get("challenge"))
      and begin.get("publicKey", {}).get("rp", {}).get("id") == "localhost",
      f"{status} {raw[:160]}")

status, _headers, raw = req("GET", "/api/webauthn/credentials", token=passkey_token)
creds = json_body(raw)
check("K4_empty_list", status == 200 and creds.get("credentials") == []
      and creds.get("has_password") is True, str(creds))

VIRTUAL = {
    "protocol": "ctap2", "transport": "usb", "hasResidentKey": True,
    "hasUserVerification": True, "isUserVerified": True,
    "automaticPresenceSimulation": True,
}

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context_a = browser.new_context()
    page_a = context_a.new_page()
    cdp_a = context_a.new_cdp_session(page_a)
    cdp_a.send("WebAuthn.enable")
    auth_id = cdp_a.send("WebAuthn.addVirtualAuthenticator",
                         {"options": VIRTUAL})["authenticatorId"]
    page_a.goto(BASE_LOCAL, wait_until="networkidle")
    page_a.evaluate(
        "u => localStorage.setItem('b2first_user', JSON.stringify(u))", passkey_account)
    page_a.reload(wait_until="networkidle")
    page_a.wait_for_timeout(300)

    page_a.evaluate(
        "() => {document.getElementById('passkeyLabel').value='Test device';"
        "document.getElementById('passkeyPassword').value=%s;}" % json.dumps(PASSKEY_PASS))
    page_a.evaluate("addPasskey()")
    page_a.wait_for_timeout(500)
    status_text = page_a.evaluate("document.getElementById('passkeyStatus').textContent")

    passkey_file = os.path.join(_tmp, "webauthn", passkey_uid + ".json")
    stored = []
    if os.path.exists(passkey_file):
        stored = json.load(open(passkey_file, encoding="utf-8"))
    check("K5_registered", len(stored) == 1 and stored[0].get("label") == "Test device",
          f"{status_text} {stored}")
    check("K6_file_private",
          os.path.exists(passkey_file)
          and (os.stat(passkey_file).st_mode & 0o777) == 0o600,
          oct(os.stat(passkey_file).st_mode & 0o777) if os.path.exists(passkey_file) else "missing")
    webauthn_dir = os.path.join(_tmp, "webauthn")
    check("K6b_dir_private",
          os.path.isdir(webauthn_dir)
          and (os.stat(webauthn_dir).st_mode & 0o777) == 0o700,
          oct(os.stat(webauthn_dir).st_mode & 0o777) if os.path.isdir(webauthn_dir) else "missing")
    check("K7_cose_stored",
          bool(stored) and bool(stored[0].get("public_key_cose"))
          and int(stored[0].get("sign_count", -1)) >= 0,
          str(stored[:1])[:200])

    status, _headers, raw = req("GET", "/api/webauthn/credentials", token=passkey_token)
    listed = json_body(raw)
    check("K8_listed",
          len(listed.get("credentials", [])) == 1
          and listed["credentials"][0].get("label") == "Test device", str(listed))

    exported = cdp_a.send("WebAuthn.getCredentials", {"authenticatorId": auth_id})
    exported_creds = exported.get("credentials") or []
    check("K9_authenticator_credential", len(exported_creds) == 1,
          str(len(exported_creds)))

    context_b = browser.new_context()
    page_b = context_b.new_page()
    cdp_b = context_b.new_cdp_session(page_b)
    cdp_b.send("WebAuthn.enable")
    auth_id_b = cdp_b.send("WebAuthn.addVirtualAuthenticator",
                           {"options": VIRTUAL})["authenticatorId"]
    if exported_creds:
        cdp_b.send("WebAuthn.addCredential", {
            "authenticatorId": auth_id_b, "credential": exported_creds[0]})
    page_b.goto(BASE_LOCAL, wait_until="networkidle")
    page_b.evaluate("localStorage.removeItem('b2first_user')")
    page_b.reload(wait_until="networkidle")
    page_b.wait_for_timeout(300)

    login_js = """async () => {
      try {
        const u = await passkeyLogin();
        saveUserSession(u);
        return {ok: true, id: u.id, token: u.token};
      } catch (e) {
        return {ok: false, msg: String(e && e.message || e), status: e && e.status || 0};
      }
    }"""
    result = page_b.evaluate(login_js)
    check("K10_fresh_context_signs_in",
          bool(result.get("ok")) and result.get("id") == passkey_uid
          and bool(result.get("token")), str(result))
    check("K11_passkey_token_works",
          req("GET", "/api/me", token=result.get("token", ""))[0] == 200)

    # A counter that goes backwards must be refused.
    tampered_store = json.load(open(passkey_file, encoding="utf-8"))
    tampered_store[0]["sign_count"] = int(tampered_store[0].get("sign_count", 0)) + 1000
    with open(passkey_file, "w", encoding="utf-8") as handle:
        json.dump(tampered_store, handle)
    os.chmod(passkey_file, 0o600)
    bumped = page_b.evaluate(login_js)
    check("K12_counter_backwards_rejected",
          not bumped.get("ok") and bumped.get("status") == 400, str(bumped))

    context_b.close()
    context_a.close()
    browser.close()

# ---------------------------------------------------------------------------
# 9. i18n: the full string scanner must find zero untranslated text.
# ---------------------------------------------------------------------------
req("POST", "/api/register", {"name": "text-scan-user", "password": "text-scan-pass-9!"})
env = os.environ.copy()
env["B2_URL"] = BASE_LOCAL
scan = subprocess.run(
    [sys.executable, os.path.join(REPO, "tools", "scan_texts.py")],
    cwd=os.path.join(REPO, "tests"), env=env, capture_output=True, text=True,
    timeout=180)
check("I1_no_hardcoded_strings", scan.returncode == 0,
      (scan.stdout + scan.stderr)[-400:])

# ---------------------------------------------------------------------------
srv.shutdown()
stub.shutdown()
shutil.rmtree(_tmp, ignore_errors=True)

print(json.dumps(out, ensure_ascii=False, indent=1))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print(f"OK {len(out)} checks")
sys.exit(0)
