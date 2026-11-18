#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOTP second factor (RFC 6238) and one-time recovery codes.

Stdlib only: hmac/hashlib/struct/base64/secrets. The secret is base32, the
code is 6 digits, the step is 30 s and verification accepts the current step
plus/minus one to absorb clock drift. Comparison is constant-time.

This module has no HTTP or storage knowledge: server.py owns the account
record, the rate limits and the audit trail.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

__all__ = [
    "DIGITS",
    "STEP_SECONDS",
    "WINDOW",
    "generate_secret",
    "otpauth_uri",
    "totp",
    "verify",
    "generate_recovery_codes",
    "hash_recovery_code",
    "normalize_recovery_code",
    "RECOVERY_CODE_COUNT",
]

DIGITS = 6
STEP_SECONDS = 30
WINDOW = 1                      # accept t-1, t, t+1
RECOVERY_CODE_COUNT = 10
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def _normalize_secret(secret):
    """Upper-case base32 without spaces or separators, padded to 8 chars."""
    value = "".join(str(secret or "").split()).replace("-", "").upper()
    return value + "=" * ((-len(value)) % 8)


def generate_secret():
    """A fresh 160-bit base32 secret (32 characters, no padding)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret):
    return base64.b32decode(_normalize_secret(secret), casefold=True)


def _hotp(key, counter):
    """RFC 4226 HOTP for one counter value, 6 digits."""
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def totp(secret, at=None):
    """The 6-digit code for `at` (epoch seconds, default now)."""
    stamp = time.time() if at is None else at
    return _hotp(_key(secret), int(stamp) // STEP_SECONDS)


def verify(secret, code, at=None, window=WINDOW):
    """True when `code` matches the current step +/- `window` (constant-time)."""
    text = str(code or "").strip()
    if len(text) != DIGITS or not text.isdigit():
        return False
    stamp = time.time() if at is None else at
    counter = int(stamp) // STEP_SECONDS
    key = _key(secret)
    ok = False
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_hotp(key, counter + offset), text):
            ok = True
    return ok


def otpauth_uri(secret, account, issuer="B2 First Tracker"):
    """The provisioning URI an authenticator app scans or pastes."""
    label = quote(f"{issuer}:{account}", safe="")
    params = (
        f"secret={_normalize_secret(secret).rstrip('=')}"
        f"&issuer={quote(issuer, safe='')}"
        "&algorithm=SHA1&digits=6&period=30"
    )
    return f"otpauth://totp/{label}?{params}"


def normalize_recovery_code(code):
    """Recovery codes are compared as upper-case alphanumerics only."""
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def hash_recovery_code(code):
    """sha256 of the normalized recovery code; only this is stored."""
    return hashlib.sha256(normalize_recovery_code(code).encode("utf-8")).hexdigest()


def generate_recovery_codes(count=RECOVERY_CODE_COUNT):
    """`count` plaintext recovery codes in xxxx-xxxx form (shown once)."""
    out = []
    for _ in range(count):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(8))
        out.append(f"{raw[:4]}-{raw[4:]}")
    return out
