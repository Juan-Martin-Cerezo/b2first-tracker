#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decode-only WebAuthn helpers (stdlib only, no encoding library).

Covers exactly what the server needs to verify a registration and an
assertion made by a platform authenticator:

* CBOR decoding (definite-length items; enough for CTAP2 canonical CBOR);
* COSE_Key parsing for ES256 / P-256 public keys;
* authenticator-data and client-data parsing;
* ECDSA P-256 signature verification with modular arithmetic.

Attestation statements are checked for structure but their signatures are not
verified: the RP asks every client for ``attestation: "none"``, so there is
nothing to verify there.  Security rests on the RP-ID hash, the challenge,
the origin and the assertion signature.
"""
import base64
import binascii
import hashlib
import hmac
import json
import struct

__all__ = [
    "WebAuthnError",
    "b64url_encode",
    "b64url_decode",
    "loads",
    "loads_prefix",
    "parse_cose_key",
    "parse_authenticator_data",
    "verify_client_data",
    "verify_rp_id",
    "verify_assertion",
    "ecdsa_verify",
    "FLAG_UP",
    "FLAG_UV",
    "FLAG_AT",
]


class WebAuthnError(ValueError):
    """Malformed or untrusted WebAuthn data."""


# ---------------------------------------------------------------------------
# base64url
# ---------------------------------------------------------------------------
def b64url_encode(raw):
    """Unpadded base64url of bytes (the format WebAuthn JSON uses)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value):
    """Decode a base64url string, tolerating optional '=' padding."""
    if not isinstance(value, str):
        raise WebAuthnError("invalid base64url")
    text = value.strip()
    text += "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text.encode("ascii"))
    except (ValueError, UnicodeEncodeError, binascii.Error):
        raise WebAuthnError("invalid base64url") from None


# ---------------------------------------------------------------------------
# CBOR (decoder only)
# ---------------------------------------------------------------------------
_MAX_DEPTH = 12


def _read_uint(data, offset, additional):
    if additional < 24:
        return additional, offset
    size = {24: 1, 25: 2, 26: 4, 27: 8}.get(additional)
    if size is None:
        raise WebAuthnError("indefinite or reserved CBOR length")
    if offset + size > len(data):
        raise WebAuthnError("truncated CBOR")
    return int.from_bytes(data[offset:offset + size], "big"), offset + size


def _decode_item(data, offset, depth):
    if depth > _MAX_DEPTH:
        raise WebAuthnError("CBOR nesting too deep")
    if offset >= len(data):
        raise WebAuthnError("truncated CBOR")
    first = data[offset]
    offset += 1
    major, additional = first >> 5, first & 0x1F

    if major == 7:  # simple values / floats
        if additional == 20:
            return False, offset
        if additional == 21:
            return True, offset
        if additional in (22, 23):  # null / undefined
            return None, offset
        if additional == 24:
            if offset >= len(data):
                raise WebAuthnError("truncated CBOR")
            return data[offset], offset + 1
        if additional == 25:
            if offset + 2 > len(data):
                raise WebAuthnError("truncated CBOR")
            return struct.unpack(">e", data[offset:offset + 2])[0], offset + 2
        if additional == 26:
            if offset + 4 > len(data):
                raise WebAuthnError("truncated CBOR")
            return struct.unpack(">f", data[offset:offset + 4])[0], offset + 4
        if additional == 27:
            if offset + 8 > len(data):
                raise WebAuthnError("truncated CBOR")
            return struct.unpack(">d", data[offset:offset + 8])[0], offset + 8
        raise WebAuthnError("unsupported CBOR simple value")

    length, offset = _read_uint(data, offset, additional)

    if major == 0:
        return length, offset
    if major == 1:
        return -1 - length, offset
    if major == 2:
        if offset + length > len(data):
            raise WebAuthnError("truncated CBOR byte string")
        return bytes(data[offset:offset + length]), offset + length
    if major == 3:
        if offset + length > len(data):
            raise WebAuthnError("truncated CBOR text string")
        try:
            return data[offset:offset + length].decode("utf-8"), offset + length
        except UnicodeDecodeError:
            raise WebAuthnError("invalid CBOR text") from None
    if major == 4:
        items = []
        for _ in range(length):
            item, offset = _decode_item(data, offset, depth + 1)
            items.append(item)
        return items, offset
    if major == 5:
        items = {}
        for _ in range(length):
            key, offset = _decode_item(data, offset, depth + 1)
            value, offset = _decode_item(data, offset, depth + 1)
            try:
                items[key] = value
            except TypeError:
                raise WebAuthnError("unhashable CBOR map key") from None
        return items, offset
    if major == 6:  # tag: the tag number is irrelevant here
        return _decode_item(data, offset, depth + 1)
    raise WebAuthnError("unsupported CBOR major type")


def loads_prefix(data, offset=0):
    """Decode one item and return (value, next_offset)."""
    if not isinstance(data, (bytes, bytearray)):
        raise WebAuthnError("CBOR input must be bytes")
    return _decode_item(bytes(data), offset, 0)


def loads(data):
    """Decode exactly one CBOR item from `data` (trailing bytes are rejected)."""
    value, end = loads_prefix(data)
    if end != len(data):
        raise WebAuthnError("trailing bytes after CBOR item")
    return value


# ---------------------------------------------------------------------------
# COSE_Key (P-256 / ES256)
# ---------------------------------------------------------------------------
# NIST P-256 parameters.
P256_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
P256_A = P256_P - 3
P256_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
P256_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
P256_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5


def _point_add(p1, p2):
    """Affine point addition on P-256 (None is the point at infinity)."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P256_P == 0:
            return None
        slope = (3 * x1 * x1 + P256_A) * pow(2 * y1, -1, P256_P) % P256_P
    else:
        slope = (y2 - y1) * pow(x2 - x1, -1, P256_P) % P256_P
    x3 = (slope * slope - x1 - x2) % P256_P
    y3 = (slope * (x1 - x3) - y1) % P256_P
    return x3, y3


def _point_mul(point, scalar):
    result = None
    addend = point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def parse_cose_key(key):
    """Validate one decoded COSE_Key map and return its affine P-256 point."""
    if not isinstance(key, dict):
        raise WebAuthnError("COSE key is not a map")
    if key.get(1) != 2:            # kty: EC2
        raise WebAuthnError("unsupported COSE key type")
    if key.get(3) != -7:           # alg: ES256
        raise WebAuthnError("unsupported COSE algorithm")
    if key.get(-1) != 1:           # crv: P-256
        raise WebAuthnError("unsupported COSE curve")
    x_raw, y_raw = key.get(-2), key.get(-3)
    if not isinstance(x_raw, bytes) or len(x_raw) != 32:
        raise WebAuthnError("invalid COSE x coordinate")
    if not isinstance(y_raw, bytes) or len(y_raw) != 32:
        raise WebAuthnError("invalid COSE y coordinate")
    x = int.from_bytes(x_raw, "big")
    y = int.from_bytes(y_raw, "big")
    if not (0 <= x < P256_P and 0 <= y < P256_P):
        raise WebAuthnError("COSE point out of range")
    if (y * y - (x * x * x + P256_A * x + P256_B)) % P256_P != 0:
        raise WebAuthnError("COSE point is not on P-256")
    return {"x": x, "y": y}


def parse_cose_key_bytes(raw):
    """Parse the raw COSE_Key bytes that authenticator data carries."""
    return parse_cose_key(loads(raw))


# ---------------------------------------------------------------------------
# authenticator data / client data
# ---------------------------------------------------------------------------
FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40
FLAG_ED = 0x80


def parse_authenticator_data(data):
    """Split authenticator data into its fields (COSE key included when AT)."""
    if not isinstance(data, (bytes, bytearray)) or len(data) < 37:
        raise WebAuthnError("authenticator data too short")
    data = bytes(data)
    flags = data[32]
    out = {
        "rp_id_hash": data[0:32],
        "flags": flags,
        "up": bool(flags & FLAG_UP),
        "uv": bool(flags & FLAG_UV),
        "sign_count": int.from_bytes(data[33:37], "big"),
    }
    if flags & FLAG_AT:
        if len(data) < 55:
            raise WebAuthnError("truncated attested credential data")
        out["aaguid"] = data[37:53]
        cred_len = int.from_bytes(data[53:55], "big")
        if cred_len < 1 or 55 + cred_len > len(data):
            raise WebAuthnError("invalid credential id length")
        out["credential_id_bytes"] = data[55:55 + cred_len]
        cose_raw = data[55 + cred_len:]
        _, consumed = loads_prefix(cose_raw)
        out["public_key_cose"] = cose_raw[:consumed]
        out["public_key"] = parse_cose_key(loads(cose_raw[:consumed]))
        out["credential_id"] = b64url_encode(out["credential_id_bytes"])
    return out


def parse_client_data(raw):
    """Decode clientDataJSON into a dict (never trusting its contents yet)."""
    try:
        obj = json.loads(bytes(raw).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, TypeError):
        raise WebAuthnError("invalid client data") from None
    if not isinstance(obj, dict):
        raise WebAuthnError("invalid client data")
    return obj


def verify_client_data(raw, expected_type, expected_challenge, expected_origin):
    """Check type, challenge and origin; return the decoded client data."""
    obj = parse_client_data(raw)
    if obj.get("type") != expected_type:
        raise WebAuthnError("unexpected ceremony type")
    try:
        got = b64url_decode(obj.get("challenge"))
    except WebAuthnError:
        raise
    if not hmac.compare_digest(got, bytes(expected_challenge)):
        raise WebAuthnError("challenge mismatch")
    origin = obj.get("origin")
    if not isinstance(origin, str) or origin.rstrip("/") != (expected_origin or "").rstrip("/"):
        raise WebAuthnError("origin mismatch")
    if obj.get("crossOrigin") is True:
        raise WebAuthnError("cross-origin ceremony")
    return obj


def verify_rp_id(auth_data, rp_id):
    """The rpIdHash must be SHA-256 of the RP ID this server configured."""
    expected = hashlib.sha256((rp_id or "").encode("utf-8")).digest()
    if not hmac.compare_digest(auth_data["rp_id_hash"], expected):
        raise WebAuthnError("RP ID mismatch")


# ---------------------------------------------------------------------------
# ECDSA P-256 (DER signatures, SHA-256)
# ---------------------------------------------------------------------------
def _der_length(data, offset):
    if offset >= len(data):
        raise WebAuthnError("truncated DER")
    first = data[offset]
    if first < 0x80:
        return first, offset + 1
    size = first & 0x7F
    if size == 0 or size > 2 or offset + 1 + size > len(data):
        raise WebAuthnError("invalid DER length")
    return int.from_bytes(data[offset + 1:offset + 1 + size], "big"), offset + 1 + size


def _der_integer(data, offset):
    if offset >= len(data) or data[offset] != 0x02:
        raise WebAuthnError("invalid DER integer")
    length, offset = _der_length(data, offset + 1)
    if length < 1 or offset + length > len(data):
        raise WebAuthnError("truncated DER integer")
    raw = data[offset:offset + length]
    if raw[0] & 0x80:
        raise WebAuthnError("negative DER integer")
    return int.from_bytes(raw, "big"), offset + length


def der_signature(raw):
    """Parse an ECDSA DER SEQUENCE { r INTEGER, s INTEGER }."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 8 or raw[0] != 0x30:
        raise WebAuthnError("invalid DER signature")
    length, offset = _der_length(raw, 1)
    if offset + length != len(raw):
        raise WebAuthnError("invalid DER signature length")
    r, offset = _der_integer(raw, offset)
    s, offset = _der_integer(raw, offset)
    if offset != len(raw):
        raise WebAuthnError("trailing DER data")
    return r, s


def ecdsa_verify(public_key, signature, message):
    """Verify one ES256 signature over `message` (raw bytes)."""
    try:
        r, s = der_signature(signature)
    except WebAuthnError:
        return False
    if not (1 <= r < P256_N and 1 <= s < P256_N):
        return False
    z = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, P256_N)
    point = _point_add(
        _point_mul((P256_GX, P256_GY), (z * w) % P256_N),
        _point_mul((public_key["x"], public_key["y"]), (r * w) % P256_N),
    )
    return point is not None and (point[0] % P256_N) == r


def verify_assertion(public_key_cose, auth_data_raw, client_data_raw, signature):
    """Verify an assertion signature over authData || SHA-256(clientDataJSON)."""
    auth = parse_authenticator_data(auth_data_raw)
    if not auth.get("up"):
        raise WebAuthnError("user presence not set")
    key = parse_cose_key_bytes(public_key_cose)
    signed = bytes(auth_data_raw) + hashlib.sha256(bytes(client_data_raw)).digest()
    if not ecdsa_verify(key, signature, signed):
        raise WebAuthnError("invalid signature")
    return auth
