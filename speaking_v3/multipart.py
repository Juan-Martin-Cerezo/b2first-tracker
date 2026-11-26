#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stdlib-only multipart/form-data parser and image validator (Python 3.13+)."""
import re


_BOUNDARY_RE = re.compile(r'boundary=(?:"([^"]+)"|([^;\s]+))', re.IGNORECASE)
_NAME_RE = re.compile(r'name="([^"]+)"')
_FILENAME_RE = re.compile(r'filename="([^"]*)"')


def detect_image_type(data):
    """Detect real image format from magic bytes.

    Returns ``(mime, ext)`` or ``None`` if not PNG, JPEG, or WebP.
    Never trusts the client-supplied Content-Type or filename extension.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 12:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def parse_multipart(content_type, body, max_parts=24, max_file_bytes=5 * 1024 * 1024):
    """Parse a multipart/form-data request body.

    Returns ``(fields, files, error)`` where:
      - ``fields`` is ``dict[str, list[str]]``
      - ``files`` is ``dict[str, list[dict]]`` (keys normalised: ``images[]`` -> ``images``)
      - ``error`` is ``None`` or a short error string.
    """
    if not isinstance(content_type, str) or "multipart/form-data" not in content_type.lower():
        return None, None, "expected_multipart_form_data"
    m = _BOUNDARY_RE.search(content_type)
    if not m:
        return None, None, "missing_boundary"
    boundary = (m.group(1) or m.group(2) or "").strip()
    if not boundary or len(boundary) > 200:
        return None, None, "invalid_boundary"

    delim = b"--" + boundary.encode("latin-1", errors="ignore")
    if not isinstance(body, (bytes, bytearray)) or delim not in body:
        return None, None, "invalid_multipart_body"

    chunks = body.split(delim)
    fields = {}
    files = {}
    part_count = 0

    for chunk in chunks[1:]:
        if chunk.startswith(b"--"):
            break
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        elif chunk.endswith(b"\n"):
            chunk = chunk[:-1]
        if not chunk:
            continue

        part_count += 1
        if part_count > max_parts:
            return None, None, "too_many_parts"

        sep = b"\r\n\r\n"
        idx = chunk.find(sep)
        if idx < 0:
            sep = b"\n\n"
            idx = chunk.find(sep)
        if idx < 0:
            continue

        raw_headers = chunk[:idx].decode("utf-8", errors="replace")
        payload = chunk[idx + len(sep):]

        disp = ""
        part_ctype = "application/octet-stream"
        for line in raw_headers.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            kl = k.strip().lower()
            if kl == "content-disposition":
                disp = v.strip()
            elif kl == "content-type":
                part_ctype = v.strip().lower()

        nm = _NAME_RE.search(disp)
        if not nm:
            continue
        field_name = nm.group(1).strip()
        fnm = _FILENAME_RE.search(disp)

        if fnm is not None:
            filename = fnm.group(1).strip()
            if not payload and not filename:
                continue
            if len(payload) > max_file_bytes:
                return None, None, "image_too_large"
            norm_key = field_name[:-2] if field_name.endswith("[]") else field_name
            files.setdefault(norm_key, []).append({
                "filename": filename,
                "content_type": part_ctype,
                "data": bytes(payload),
            })
        else:
            if len(payload) > 64 * 1024:
                return None, None, "field_too_large"
            text = payload.decode("utf-8", errors="replace")
            norm_key = field_name[:-2] if field_name.endswith("[]") else field_name
            fields.setdefault(norm_key, []).append(text)

    return fields, files, None
