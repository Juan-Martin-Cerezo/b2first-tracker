#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Google sign-in, stdlib only: authorization-code + PKCE and RS256 JWT checks.

No SDK, no JWT library, no client secret in the browser.  The flow is:

    browser -> /api/auth/google/start -> Google consent
    Google  -> /api/auth/google/callback?code&state -> token endpoint -> id_token

The token exchange happens server-side with ``urllib.request``; the id_token is
verified against Google's JWKS with ``pow(signature, e, n)`` and a hand-built
PKCS#1 v1.5 DigestInfo block.  The client never sees the code, the secret or
the id_token.
"""
import base64
import binascii
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

__all__ = [
    "OAuthError",
    "b64url_encode",
    "b64url_decode",
    "new_pkce",
    "authorize_url",
    "exchange_code",
    "verify_id_token",
    "fetch_jwks",
    "GOOGLE_ISSUERS",
]

GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_ENDPOINT = "https://www.googleapis.com/oauth2/v3/certs"
_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")

_JWKS_CACHE = {}
_JWKS_LOCK = None


class OAuthError(ValueError):
    """The provider answered with something we refuse to trust."""


try:  # keep the module importable without a threading import at module top
    import threading as _threading
    _JWKS_LOCK = _threading.Lock()
except Exception:  # pragma: no cover - threading is always present
    _JWKS_LOCK = None


# ---------------------------------------------------------------------------
# base64url
# ---------------------------------------------------------------------------
def b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value):
    if not isinstance(value, str):
        raise OAuthError("invalid base64url")
    text = value.strip()
    text += "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text.encode("ascii"))
    except (ValueError, UnicodeEncodeError, binascii.Error):
        raise OAuthError("invalid base64url") from None


# ---------------------------------------------------------------------------
# PKCE + authorization request
# ---------------------------------------------------------------------------
def new_pkce():
    """Return (verifier, S256 challenge) as base64url strings."""
    verifier = b64url_encode(os.urandom(48))          # 64 chars, inside 43..128
    challenge = b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def authorize_url(client_id, redirect_uri, state, challenge, nonce,
                  endpoint=AUTHORIZE_ENDPOINT):
    """Build the Google consent URL (no secret, no code in it)."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "nonce": nonce,
        "access_type": "online",
        "prompt": "select_account",
    }
    return endpoint + "?" + urllib.parse.urlencode(params)


# ---------------------------------------------------------------------------
# Token endpoint
# ---------------------------------------------------------------------------
def _read_json_response(response, limit=64 * 1024):
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise OAuthError("provider response too large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise OAuthError("provider returned invalid JSON") from None
    if not isinstance(value, dict):
        raise OAuthError("provider returned invalid JSON")
    return value


def exchange_code(token_url, client_id, client_secret, code, redirect_uri,
                  code_verifier, timeout=10):
    """Trade an authorization code for tokens.  Raises OAuthError on failure.

    The request and response are never logged: `code`, `id_token` and the
    client secret stay in this function's locals.
    """
    fields = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    if client_secret:                 # a PKCE public client has no secret
        fields["client_secret"] = client_secret
    body = urllib.parse.urlencode(fields).encode("ascii")
    request = urllib.request.Request(
        token_url, data=body, method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise OAuthError("token exchange rejected")
            return _read_json_response(response)
    except urllib.error.HTTPError:
        raise OAuthError("token exchange rejected") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise OAuthError("token endpoint unreachable") from None


def fetch_jwks(url, timeout=5, ttl=300):
    """Fetch and cache Google's signing keys for `ttl` seconds."""
    now = time.time()
    cached = _JWKS_CACHE.get(url)
    if cached and now - cached[0] < ttl:
        return cached[1]
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise OAuthError("JWKS unavailable")
            data = _read_json_response(response)
    except urllib.error.HTTPError:
        raise OAuthError("JWKS unavailable") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise OAuthError("JWKS unreachable") from None
    if not isinstance(data.get("keys"), list):
        raise OAuthError("JWKS has no keys")
    if _JWKS_LOCK is not None:
        with _JWKS_LOCK:
            _JWKS_CACHE[url] = (now, data)
    else:  # pragma: no cover
        _JWKS_CACHE[url] = (now, data)
    return data


# ---------------------------------------------------------------------------
# RS256 (PKCS#1 v1.5 + SHA-256)
# ---------------------------------------------------------------------------
def _rsa_public(jwk):
    try:
        modulus = int.from_bytes(b64url_decode(jwk["n"]), "big")
        exponent = int.from_bytes(b64url_decode(jwk["e"]), "big")
    except (KeyError, OAuthError, TypeError):
        raise OAuthError("invalid RSA key") from None
    if modulus <= 0 or exponent <= 1:
        raise OAuthError("invalid RSA key")
    return modulus, exponent


def _rsa_verify_sha256(modulus, exponent, message, signature):
    size = (modulus.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    value = int.from_bytes(signature, "big")
    if value >= modulus:
        return False
    encoded = pow(value, exponent, modulus).to_bytes(size, "big")
    digest_info = _SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
    if size < len(digest_info) + 11:
        return False
    expected = (b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3)
                + b"\x00" + digest_info)
    return hmac.compare_digest(encoded, expected)


def _json_segment(segment):
    try:
        value = json.loads(b64url_decode(segment).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, OAuthError):
        raise OAuthError("invalid JWT segment") from None
    if not isinstance(value, dict):
        raise OAuthError("invalid JWT segment")
    return value


def _choose_key(jwks, kid):
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list):
        raise OAuthError("JWKS has no keys")
    rsa = [k for k in keys if isinstance(k, dict) and k.get("kty") == "RSA"]
    if kid:
        rsa = [k for k in rsa if k.get("kid") == kid]
    if len(rsa) != 1:
        raise OAuthError("no matching signing key")
    key = rsa[0]
    if key.get("alg") not in (None, "RS256"):
        raise OAuthError("unexpected signing algorithm")
    return key


def verify_id_token(token, jwks, audience, nonce, now=None):
    """Verify signature + iss/aud/exp/nonce and return the claims.

    Raises OAuthError for anything that is not a fresh, correctly signed,
    correctly addressed Google id_token.  The caller never logs `token`.
    """
    if not isinstance(token, str):
        raise OAuthError("missing id_token")
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise OAuthError("malformed id_token")
    header = _json_segment(parts[0])
    if header.get("alg") != "RS256":
        raise OAuthError("unexpected id_token algorithm")
    if header.get("typ") not in (None, "JWT"):
        raise OAuthError("unexpected id_token type")
    key = _choose_key(jwks, header.get("kid"))
    modulus, exponent = _rsa_public(key)
    signed = (parts[0] + "." + parts[1]).encode("ascii")
    signature = b64url_decode(parts[2])
    if not _rsa_verify_sha256(modulus, exponent, signed, signature):
        raise OAuthError("bad id_token signature")

    claims = _json_segment(parts[1])
    now = time.time() if now is None else now

    issuer = claims.get("iss")
    if issuer not in GOOGLE_ISSUERS:
        raise OAuthError("unexpected issuer")

    aud = claims.get("aud")
    if isinstance(aud, list):
        if audience not in aud:
            raise OAuthError("unexpected audience")
    elif aud != audience:
        raise OAuthError("unexpected audience")

    azp = claims.get("azp")
    if azp is not None and azp != audience:
        raise OAuthError("unexpected authorized party")

    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)) or exp <= now:
        raise OAuthError("id_token expired")

    iat = claims.get("iat")
    if iat is not None and (isinstance(iat, bool) or not isinstance(iat, (int, float))
                            or iat > now + 300):
        raise OAuthError("id_token issued in the future")

    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise OAuthError("id_token has no subject")

    got_nonce = claims.get("nonce")
    if not isinstance(got_nonce, str) or not hmac.compare_digest(got_nonce, nonce):
        raise OAuthError("nonce mismatch")

    return claims
