#!/usr/bin/env python3
"""Manual smoke test for POST /api/speaking/turn using a real WAV file.

Logs in via /api/login, sends the WAV file as base64 (`tts: "none"`, fresh
`session_id`) to `/api/speaking/turn`, and prints one JSON object with:
`http`, `ms`, `transcript`, `reply`, and `finish_reason` when present.

Standard library only. Never prints passwords, tokens or API keys.

Usage:
    python3 tools/speaking_smoke.py \\
        --url https://example.com \\
        --user alice \\
        --password secret \\
        --wav tests/fixtures/candidate_b2.wav \\
        --part 1
"""
import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def _post_json(url, payload, token=None, timeout=60.0):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw) if raw else {}
            except ValueError:
                body = {}
            return resp.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        return exc.code, body


def main():
    parser = argparse.ArgumentParser(
        description="Send a real WAV file to /api/speaking/turn and print JSON.")
    parser.add_argument("--url", required=True, help="Base URL of the server")
    parser.add_argument("--user", required=True, help="Account username")
    parser.add_argument("--password", required=True, help="Account password")
    parser.add_argument("--wav", required=True, help="Path to input WAV file")
    parser.add_argument("--part", type=int, choices=(1, 2, 3, 4), default=1,
                        help="Speaking exam part (1-4, default 1)")
    parser.add_argument("--role", choices=("examiner", "partner"),
                        default="examiner", help="Voice role (default examiner)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="HTTP timeout in seconds (default 60)")
    args = parser.parse_args()

    parsed = urllib.parse.urlsplit(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        parser.error("--url must be an absolute http(s) URL")
    base = args.url.rstrip("/")

    with open(args.wav, "rb") as fh:
        audio_b64 = base64.b64encode(fh.read()).decode("ascii")

    login_status, login_body = _post_json(
        base + "/api/login",
        {"name": args.user, "password": args.password},
        timeout=args.timeout,
    )
    token = login_body.get("token") if isinstance(login_body, dict) else None
    if login_status != 200 or not isinstance(token, str) or not token:
        out = {
            "http": login_status,
            "ms": 0,
            "transcript": None,
            "reply": None,
            "error": (login_body.get("error") if isinstance(login_body, dict) else None)
                     or "login_failed",
        }
        print(json.dumps(out, ensure_ascii=False))
        return 1

    payload = {
        "audio_b64": audio_b64,
        "mime": "audio/wav",
        "part": args.part,
        "role": args.role,
        "tts": "none",
        "session_id": "smoke-" + uuid.uuid4().hex[:12],
        "history": [],
    }
    started = time.monotonic()
    status, body = _post_json(
        base + "/api/speaking/turn",
        payload,
        token=token,
        timeout=args.timeout,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    data = body if isinstance(body, dict) else {}

    out = {
        "http": status,
        "ms": elapsed_ms,
        "transcript": data.get("transcript"),
        "reply": data.get("reply"),
    }
    if "finish_reason" in data and data.get("finish_reason") is not None:
        out["finish_reason"] = data.get("finish_reason")
    if status != 200:
        if "error" in data:
            out["error"] = data.get("error")
        if "reason" in data:
            out["reason"] = data.get("reason")

    print(json.dumps(out, ensure_ascii=False))
    return 0 if status == 200 and isinstance(out["reply"], str) and out["reply"].strip() else 1


if __name__ == "__main__":
    sys.exit(main())
