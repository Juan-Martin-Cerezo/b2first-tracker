#!/usr/bin/env python3
"""Manual smoke test for POST /api/speaking/turn and POST /api/speaking/partner.

Logs in via /api/login, sends either:
- a WAV file as base64 (`tts: "none"`, fresh `session_id`) to `/api/speaking/turn`,
  printing `{http, ms, transcript, reply}` (and `finish_reason` when present); or
- with `--partner`, a JSON payload `{question, topic, candidate_said, mode,
  candidate_context}` to `/api/speaking/partner`, printing `{http, ms, line}`.

Standard library only. Never prints passwords, tokens or API keys.

Usage:
    python3 tools/speaking_smoke.py \\
        --url https://example.com \\
        --user alice \\
        --password secret \\
        --wav tests/fixtures/candidate_b2.wav \\
        --part 1

    python3 tools/speaking_smoke.py \\
        --url https://example.com \\
        --user alice \\
        --password secret \\
        --partner
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
        description="Smoke test /api/speaking/turn or /api/speaking/partner and print JSON.")
    parser.add_argument("--url", required=True, help="Base URL of the server")
    parser.add_argument("--user", required=True, help="Account username")
    parser.add_argument("--password", required=True, help="Account password")
    parser.add_argument("--wav", help="Path to input WAV file (required unless --partner)")
    parser.add_argument("--part", type=int, choices=(1, 2, 3, 4), default=1,
                        help="Speaking exam part (1-4, default 1)")
    parser.add_argument("--role", choices=("examiner", "partner"),
                        default="examiner", help="Voice role (default examiner)")
    parser.add_argument("--partner", action="store_true",
                        help="Test POST /api/speaking/partner and print {http, ms, line}")
    parser.add_argument("--question",
                        default="Why do you think school trips are useful for students?",
                        help="Question for --partner mode")
    parser.add_argument("--topic", default="School trips",
                        help="Topic for --partner mode")
    parser.add_argument("--said",
                        default="I think school trips help students learn outside the classroom.",
                        help="Candidate utterance for --partner mode")
    parser.add_argument("--mode", choices=("partner", "examiner"), default="partner",
                        help="Mode for --partner endpoint (default partner)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="HTTP timeout in seconds (default 60)")
    args = parser.parse_args()

    parsed = urllib.parse.urlsplit(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        parser.error("--url must be an absolute http(s) URL")
    if not args.partner and not args.wav:
        parser.error("--wav is required unless --partner is set")
    base = args.url.rstrip("/")

    login_status, login_body = _post_json(
        base + "/api/login",
        {"name": args.user, "password": args.password},
        timeout=args.timeout,
    )
    token = login_body.get("token") if isinstance(login_body, dict) else None
    if login_status != 200 or not isinstance(token, str) or not token:
        err_msg = (login_body.get("error") if isinstance(login_body, dict) else None) or "login_failed"
        if args.partner:
            out = {"http": login_status, "ms": 0, "line": None, "error": err_msg}
        else:
            out = {
                "http": login_status,
                "ms": 0,
                "transcript": None,
                "reply": None,
                "error": err_msg,
            }
        print(json.dumps(out, ensure_ascii=False))
        return 1

    if args.partner:
        payload = {
            "question": args.question,
            "topic": args.topic,
            "candidate_said": args.said,
            "mode": args.mode,
            "candidate_context": [],
        }
        started = time.monotonic()
        status, body = _post_json(
            base + "/api/speaking/partner",
            payload,
            token=token,
            timeout=args.timeout,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        data = body if isinstance(body, dict) else {}
        out = {
            "http": status,
            "ms": elapsed_ms,
            "line": data.get("line"),
        }
        if status != 200 and "error" in data:
            out["error"] = data.get("error")
        print(json.dumps(out, ensure_ascii=False))
        return 0 if status == 200 and isinstance(out["line"], str) and out["line"].strip() else 1

    with open(args.wav, "rb") as fh:
        audio_b64 = base64.b64encode(fh.read()).decode("ascii")

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
