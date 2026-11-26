#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 tests — multipart own tasks (form fields + images, no JSON).

Run: python3 tests/test_speaking_v3_own_task.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

import helpers  # noqa: E402

# Minimal valid 1x1 PNG bytes
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _encode_multipart(fields, files=None, boundary="----B2TestBoundary98765"):
    chunks = []
    for k, v in fields:
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
            f"{v}\r\n".encode("utf-8")
        )
    for field_name, filename, content_type, data in (files or []):
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
            + data
            + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", b"".join(chunks)


def _req(base, method, path, payload=None, token=None, headers=None, raw_body=None):
    hdrs = dict(headers or {})
    data = raw_body
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
            ctype = r.headers.get("Content-Type", "")
            if "json" in ctype:
                return r.status, json.loads(body.decode("utf-8"))
            return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else {}


def _login(base, name="own-owner", password="OwnOwnerPass123!"):
    _req(base, "POST", "/api/register", {"name": name, "password": password})
    st, obj = _req(base, "POST", "/api/login", {"name": name, "password": password})
    assert st == 200 and obj.get("token"), (st, obj)
    return obj["token"]


def _turn(base, sid, tok, text, extra=None):
    body = {"audio_b64": "", "mime": "audio/wav"}
    if extra:
        body.update(extra)
    st, obj = _req(
        base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
        body, token=tok, headers={"X-Test-Transcript": text},
    )
    assert st == 200, (st, obj)
    return obj


def main():
    base = helpers.isolated_server(extra_env={
        "B2_SPK_TEST_MODE": "1",
        "B2_OWNER_UIDS": "own-owner",
    })
    tok = _login(base)

    # 1. Validation failures by part
    # Part 1 without questions -> 422
    ct, body = _encode_multipart([("title", "No Qs"), ("part", "1")])
    st, err = _req(base, "POST", "/api/speaking/v3/own-tasks", token=tok, headers={"Content-Type": ct}, raw_body=body)
    assert st == 422 and err.get("error") == "questions_required", (st, err)

    # Part 2 with only 1 image -> 422
    ct, body = _encode_multipart(
        [("title", "One Img"), ("part", "2"), ("prompt", "Compare these photos")],
        [("images[]", "a.png", "image/png", TINY_PNG)],
    )
    st, err = _req(base, "POST", "/api/speaking/v3/own-tasks", token=tok, headers={"Content-Type": ct}, raw_body=body)
    assert st == 422 and err.get("error") == "two_images_required", (st, err)

    # Fake image (text masquerading as PNG) -> 422
    ct, body = _encode_multipart(
        [("title", "Fake Img"), ("part", "2"), ("prompt", "Compare")],
        [
            ("images[]", "a.png", "image/png", b"not actually a png file"),
            ("images[]", "b.png", "image/png", TINY_PNG),
        ],
    )
    st, err = _req(base, "POST", "/api/speaking/v3/own-tasks", token=tok, headers={"Content-Type": ct}, raw_body=body)
    assert st == 422 and err.get("error") == "invalid_image_type", (st, err)

    # Part 3 without discussion -> 422
    ct, body = _encode_multipart([("title", "No Disc"), ("part", "3")])
    st, err = _req(base, "POST", "/api/speaking/v3/own-tasks", token=tok, headers={"Content-Type": ct}, raw_body=body)
    assert st == 422 and err.get("error") == "discussion_required", (st, err)

    # 2. Create a valid single Part 2 own task via multipart form (no JSON!)
    ct, body = _encode_multipart(
        [
            ("title", "City vs Countryside"),
            ("part", "2"),
            ("prompt", "Say why people enjoy living in these places"),
        ],
        [
            ("images[]", "city.png", "image/png", TINY_PNG),
            ("images[]", "country.png", "image/png", TINY_PNG),
        ],
    )
    st, created_p2 = _req(base, "POST", "/api/speaking/v3/own-tasks", token=tok, headers={"Content-Type": ct}, raw_body=body)
    assert st == 201, (st, created_p2)
    tid_p2 = created_p2["id"]
    assert created_p2["part"] == 2
    assert len(created_p2["images"]) == 2

    # Image serves cleanly to owner (200) and is denied without auth (401)
    st, img_bytes = _req(base, "GET", created_p2["images"][0], token=tok)
    assert st == 200 and img_bytes == TINY_PNG
    st_noauth, _ = _req(base, "GET", created_p2["images"][0])
    assert st_noauth == 401

    # Listed in GET /own-tasks and GET /catalog
    st, listing = _req(base, "GET", "/api/speaking/v3/own-tasks", token=tok)
    assert st == 200 and any(x["id"] == tid_p2 for x in listing["own_tasks"])
    st, cat = _req(base, "GET", "/api/speaking/v3/catalog", token=tok)
    assert st == 200 and any(x["id"] == tid_p2 for x in cat["own_tasks"])

    # Execute single Part 2 own task end-to-end
    st, s_p2 = _req(base, "POST", "/api/speaking/v3/sessions", {"own_task_id": tid_p2, "part": 2}, token=tok)
    assert st == 200, (st, s_p2)
    sid_p2 = s_p2["session_id"]
    _turn(base, sid_p2, tok, "Juan")
    r_enter = _turn(base, sid_p2, tok, "Buenos Aires")
    assert r_enter["state"]["phase"] == "part2"
    assert r_enter["ui"]["images"] == created_p2["images"]
    r_long = _turn(base, sid_p2, tok, "Both photographs show places to live, whereas the first is a busy city and the second is calm countryside.")
    assert r_long["state"]["step"] == "user_followup"
    r_end = _turn(base, sid_p2, tok, "I would prefer living in the countryside because it is peaceful and quieter.")
    assert r_end["done"] is True

    # 3. Create and execute a FULL own task (part="full")
    ct, body = _encode_multipart(
        [
            ("title", "Work and Technology"),
            ("part", "full"),
            ("questions", "How do you use technology at work?\nDo you prefer working from home?\nWhat skills will matter most in the future?"),
            ("prompt", "Compare the two workplaces and say which is more productive"),
            ("discussion", "How can companies improve staff wellbeing at work?"),
            ("decision", "Decide which two ideas help employees the most"),
        ],
        [
            ("images[]", "office.png", "image/png", TINY_PNG),
            ("images[]", "remote.png", "image/png", TINY_PNG),
            ("images[]", "card.png", "image/png", TINY_PNG),
        ],
    )
    st, created_full = _req(base, "POST", "/api/speaking/v3/own-tasks", token=tok, headers={"Content-Type": ct}, raw_body=body)
    assert st == 201 and created_full["part"] == 0 and created_full["parts"] == [1, 2, 3, 4], (st, created_full)
    tid_full = created_full["id"]

    st, sf = _req(base, "POST", "/api/speaking/v3/sessions", {"own_task_id": tid_full, "part": 0}, token=tok)
    assert st == 200
    fsid = sf["session_id"]
    _turn(base, fsid, tok, "Juan")
    r = _turn(base, fsid, tok, "Argentina")
    assert r["state"]["phase"] == "part1"
    for ans in [
        "I use technology every day at work to organise tasks and communicate.",
        "I prefer working from home a couple of days a week because it saves time.",
        "Communication and problem solving skills will matter most in the future.",
    ]:
        r = _turn(base, fsid, tok, ans)
    assert r["state"]["phase"] == "part2"
    r = _turn(base, fsid, tok, "Both workplaces look modern, whereas the first is an office and the second is at home.")
    assert r["state"]["step"] == "user_followup"
    r = _turn(base, fsid, tok, "I would prefer the home workplace because it is quieter and more productive.")
    assert r["state"]["phase"] == "part3" and r["ui"]["card"] == created_full["images"][2]

    # Delete both own tasks
    st, d1 = _req(base, "DELETE", f"/api/speaking/v3/own-tasks/{tid_p2}", token=tok)
    assert st == 200 and d1["deleted"] is True
    st, d2 = _req(base, "DELETE", f"/api/speaking/v3/own-tasks/{tid_full}", token=tok)
    assert st == 200 and d2["deleted"] is True
    st, listing2 = _req(base, "GET", "/api/speaking/v3/own-tasks", token=tok)
    assert st == 200 and listing2["own_tasks"] == []

    print("PASS test_speaking_v3_own_task")
    return 0


if __name__ == "__main__":
    sys.exit(main())
