#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 catalog (4 official sample tests) and per-user own tasks."""
import json
import os
import re
import secrets
import shutil
import threading
import time

import store
from speaking_v3.multipart import detect_image_type

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(REPO_ROOT, "material", "speaking", "tests")

OWN_TASK_MAX_ITEMS = 20
OWN_TASK_MAX_IMAGES = 4
OWN_TASK_MAX_IMAGE_BYTES = 5 * 1024 * 1024
OWN_TASK_TITLE_MAX = 120
OWN_TASK_TEXT_MAX = 1200

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,48}$")
_SAFE_IMG_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_OWN_LOCK = threading.RLock()

_TESTS_CACHE = None
_TESTS_LOCK = threading.Lock()


def _clean_text(value, max_len=OWN_TASK_TEXT_MAX):
    s = _CTRL_RE.sub(" ", str(value or ""))
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s[:max_len]


def _clean_lines(value, max_items=12, max_len=240):
    raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for line in raw.split("\n"):
        cleaned = _clean_text(line, max_len=max_len)
        if cleaned:
            out.append(cleaned)
        if len(out) >= max_items:
            break
    return out


# ---------------------------------------------------------------------------
# Built-in 4 Cambridge Sample Tests
# ---------------------------------------------------------------------------
def load_all_tests(force_reload=False):
    """Load and cache material/speaking/tests/01.json..04.json."""
    global _TESTS_CACHE
    with _TESTS_LOCK:
        if _TESTS_CACHE is not None and not force_reload:
            return _TESTS_CACHE
        tests = {}
        if os.path.isdir(TESTS_DIR):
            for fname in sorted(os.listdir(TESTS_DIR)):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(TESTS_DIR, fname)
                with open(path, "r", encoding="utf-8") as fh:
                    doc = json.load(fh)
                tid = str(doc.get("id") or "").strip()
                if tid:
                    tests[tid] = doc
        _TESTS_CACHE = tests
        return tests


def list_public_tests():
    """Return catalog metadata for all 4 tests — NEVER scripts or answers."""
    tests = load_all_tests()
    out = []
    for tid in sorted(tests.keys()):
        t = tests[tid]
        out.append({
            "id": t["id"],
            "title": t["title"],
            "variant": t["variant"],
            "partner": t["partner"]["name"],
            "parts": [1, 2, 3, 4],
        })
    return out


def get_test(test_id):
    """Return the full internal test definition, or None."""
    tests = load_all_tests()
    return tests.get(str(test_id or "").strip())


# ---------------------------------------------------------------------------
# Per-user Own Tasks (multipart/form-data, stored under data/speaking_v3/own_tasks/)
# ---------------------------------------------------------------------------
def _own_tasks_root(uid):
    safe_uid = store._safe_uid(uid)
    return os.path.join(store.data_dir(), "speaking_v3", "own_tasks", safe_uid)


def _own_task_dir(uid, task_id):
    tid = str(task_id or "").strip()
    if not _SAFE_ID_RE.fullmatch(tid):
        return None
    root = _own_tasks_root(uid)
    cand = os.path.realpath(os.path.join(root, tid))
    if not cand.startswith(os.path.realpath(root) + os.sep):
        return None
    return cand


def _public_own_task(meta):
    """Public summary of an own task (no full scripts/answers)."""
    return {
        "id": meta["id"],
        "title": meta["title"],
        "part": meta["part"],
        "parts": [1, 2, 3, 4] if meta["part"] == 0 else [meta["part"]],
        "images": [
            f"/api/speaking/v3/own-tasks/{meta['id']}/images/{img}"
            for img in (meta.get("image_files") or [])
        ],
        "created_at": meta.get("created_at", 0),
    }


def list_own_tasks(uid):
    """Return all own tasks belonging to `uid`, newest first."""
    with _OWN_LOCK:
        root = _own_tasks_root(uid)
        if not os.path.isdir(root):
            return []
        items = []
        for name in os.listdir(root):
            if not _SAFE_ID_RE.fullmatch(name):
                continue
            meta_path = os.path.join(root, name, "meta.json")
            meta = store.read_json_private(meta_path, None)
            if isinstance(meta, dict) and meta.get("id") == name:
                items.append(_public_own_task(meta))
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items


def _parse_part_field(raw_part):
    s = str(raw_part or "").strip().lower()
    if s in ("0", "full", "all"):
        return 0
    if s in ("1", "2", "3", "4"):
        return int(s)
    return None


def create_own_task(uid, fields, files):
    """Validate form fields + images and persist one own task for `uid`.

    Returns ``(public_meta, error_code, error_message)``.
    """
    def first(key):
        vals = fields.get(key) or []
        return vals[0] if vals else ""

    title = _clean_text(first("title"), max_len=OWN_TASK_TITLE_MAX)
    if not title:
        return None, 422, "title_required"

    part = _parse_part_field(first("part"))
    if part is None:
        return None, 422, "invalid_part"

    questions = _clean_lines(first("questions"))
    prompt = _clean_text(first("prompt"), max_len=500)
    discussion = _clean_text(first("discussion"), max_len=500)
    decision = _clean_text(first("decision"), max_len=500)

    raw_images = list(files.get("images") or [])
    if len(raw_images) > OWN_TASK_MAX_IMAGES:
        return None, 422, "too_many_images"

    validated_images = []
    for idx, img in enumerate(raw_images):
        data = img.get("data") or b""
        if not data:
            return None, 422, "empty_image"
        if len(data) > OWN_TASK_MAX_IMAGE_BYTES:
            return None, 413, "image_too_large"
        detected = detect_image_type(data)
        if detected is None:
            return None, 422, "invalid_image_type"
        mime, ext = detected
        validated_images.append({
            "filename": f"img-{idx + 1}{ext}",
            "mime": mime,
            "data": data,
        })

    # Per-part validation
    if part in (1, 4):
        if not questions:
            return None, 422, "questions_required"
    elif part == 2:
        if not prompt:
            return None, 422, "prompt_required"
        if len(validated_images) < 2:
            return None, 422, "two_images_required"
    elif part == 3:
        if not discussion:
            return None, 422, "discussion_required"
    elif part == 0:
        if not questions:
            return None, 422, "questions_required"
        if not prompt:
            return None, 422, "prompt_required"
        if len(validated_images) < 2:
            return None, 422, "two_images_required"
        if not discussion:
            return None, 422, "discussion_required"

    with _OWN_LOCK:
        existing = list_own_tasks(uid)
        if len(existing) >= OWN_TASK_MAX_ITEMS:
            return None, 429, "own_task_limit_reached"

        task_id = "own_" + secrets.token_hex(6)
        root = _own_tasks_root(uid)
        tdir = os.path.join(root, task_id)
        os.makedirs(tdir, mode=0o700, exist_ok=True)
        os.chmod(tdir, 0o700)

        saved_files = []
        try:
            for item in validated_images:
                fpath = os.path.join(tdir, item["filename"])
                tmp = fpath + ".tmp"
                with open(tmp, "wb") as fh:
                    fh.write(item["data"])
                os.chmod(tmp, 0o600)
                os.replace(tmp, fpath)
                os.chmod(fpath, 0o600)
                saved_files.append(item["filename"])

            meta = {
                "id": task_id,
                "title": title,
                "part": part,
                "questions": questions,
                "prompt": prompt,
                "discussion": discussion,
                "decision": decision or "Decide which two points are the most important.",
                "image_files": saved_files,
                "created_at": int(time.time()),
            }
            store.write_json_private(os.path.join(tdir, "meta.json"), meta)
        except OSError:
            shutil.rmtree(tdir, ignore_errors=True)
            return None, 500, "save_failed"

    return _public_own_task(meta), 201, None


def get_own_task_meta(uid, task_id):
    with _OWN_LOCK:
        tdir = _own_task_dir(uid, task_id)
        if not tdir or not os.path.isdir(tdir):
            return None
        meta = store.read_json_private(os.path.join(tdir, "meta.json"), None)
        return meta if isinstance(meta, dict) else None


def delete_own_task(uid, task_id):
    with _OWN_LOCK:
        tdir = _own_task_dir(uid, task_id)
        if not tdir or not os.path.isdir(tdir):
            return False
        shutil.rmtree(tdir, ignore_errors=True)
        return True


def forget_user_own_tasks(uid):
    """GDPR cleanup: remove all own tasks belonging to `uid`."""
    with _OWN_LOCK:
        try:
            root = _own_tasks_root(uid)
        except ValueError:
            return
        if os.path.isdir(root):
            shutil.rmtree(root, ignore_errors=True)


def get_own_task_image(uid, task_id, filename):
    if not isinstance(filename, str) or not _SAFE_IMG_RE.fullmatch(filename):
        return None, None
    if filename.startswith(".") or ".." in filename:
        return None, None
    tdir = _own_task_dir(uid, task_id)
    if not tdir or not os.path.isdir(tdir):
        return None, None
    full = os.path.realpath(os.path.join(tdir, filename))
    if not full.startswith(os.path.realpath(tdir) + os.sep) or not os.path.isfile(full):
        return None, None
    try:
        with open(full, "rb") as fh:
            data = fh.read(OWN_TASK_MAX_IMAGE_BYTES + 1)
    except OSError:
        return None, None
    detected = detect_image_type(data)
    if not detected:
        return None, None
    return data, detected[0]


def _extract_keywords(text):
    words = re.findall(r"[a-z]{4,}", str(text or "").lower())
    stop = {"that", "this", "with", "from", "they", "them", "have", "what", "when",
            "where", "which", "about", "your", "would", "could", "should", "think",
            "people", "things", "these", "those", "very", "more", "most", "some"}
    return [w for w in dict.fromkeys(words) if w not in stop]


def get_own_task_as_test(uid, task_id):
    """Build a test-compatible structure from a user's saved own task."""
    meta = get_own_task_meta(uid, task_id)
    if not meta:
        return None

    img_urls = [
        f"/api/speaking/v3/own-tasks/{meta['id']}/images/{fn}"
        for fn in (meta.get("image_files") or [])
    ]
    p2_imgs = img_urls[:2]
    p2_partner_imgs = img_urls[2:4] if len(img_urls) >= 4 else p2_imgs
    p3_card = img_urls[2] if len(img_urls) == 3 else (img_urls[0] if meta["part"] == 3 and img_urls else None)

    raw_qs = meta.get("questions") or [
        "How do you like to spend your free time?",
        "What do you enjoy doing at the weekend?",
        "Tell us about something you have learnt recently.",
    ]
    q_objs = [
        {
            "text": q if q.endswith(("?", ".")) else q + "?",
            "followups": ["Why?"],
            "topic": _clean_text(q.rstrip("?."), max_len=80).lower(),
            "keywords": _extract_keywords(q) or ["think", "enjoy", "prefer", "because"],
        }
        for q in raw_qs
    ]

    p2_prompt = meta.get("prompt") or "Compare the photographs and describe what is happening."
    if not p2_prompt.endswith((".", "?")):
        p2_prompt += "."
    p3_disc = meta.get("discussion") or "Discuss the main ideas shown in this task."
    if not p3_disc.endswith((".", "?")):
        p3_disc += "."
    p3_dec = meta.get("decision") or "Decide which two points are the most important."
    if not p3_dec.endswith((".", "?")):
        p3_dec += "."

    return {
        "id": meta["id"],
        "title": meta["title"],
        "variant": "own_task",
        "own_task_part": meta["part"],
        "partner": {
            "name": "Alex",
            "home": "Bristol",
            "voice": "Kore",
            "persona": "A B2 First candidate from Bristol speaking natural British English.",
        },
        "images": {
            "part2_task1": p2_imgs,
            "part2_task2": p2_partner_imgs,
            "part3_card": p3_card,
        },
        "parts": {
            "1": {
                "duration_seconds": 120,
                "opening": "First we'd like to know something about you.",
                "categories": [{"name": meta["title"], "questions": q_objs}],
            },
            "2": {
                "duration_seconds": 240,
                "opening": (
                    "In this part of the test, I'm going to give each of you two photographs. "
                    "I'd like you to talk about your photographs on your own for about a minute, "
                    "and also to answer a question about your partner's photographs."
                ),
                "task1": {
                    "title": meta["title"],
                    "images": p2_imgs,
                    "photo_descriptions": ["the first photograph", "the second photograph"],
                    "intro": "{candidate}, it's your turn first. Here are your photographs.",
                    "prompt": f"I'd like you to compare the photographs, and answer this question: {p2_prompt}",
                    "card_question": p2_prompt,
                    "check": "All right?",
                    "long_turn_seconds": 60,
                    "compare_followup": "Which photograph appeals to you more, and why?",
                    "followup_to_partner": "{partner}, which of these situations do you find more interesting? Why?",
                    "followup_seconds": 30,
                    "topic": meta["title"].lower(),
                    "keywords": _extract_keywords(p2_prompt + " " + meta["title"]) + ["both", "photograph", "picture", "whereas", "while"],
                },
                "task2": {
                    "title": meta["title"],
                    "images": p2_partner_imgs,
                    "photo_descriptions": ["the first photograph", "the second photograph"],
                    "intro": "Now, {partner}, here are your photographs.",
                    "prompt": f"I'd like you to compare the photographs, and consider: {p2_prompt}",
                    "card_question": p2_prompt,
                    "check": "All right?",
                    "long_turn_seconds": 60,
                    "partner_monologue": (
                        "Both photographs show quite different aspects of this topic. "
                        "In the first picture, the situation looks calmer and more focused, "
                        "whereas in the second photograph there seems to be more activity and energy. "
                        "I suppose each one has its own advantages depending on what someone prefers."
                    ),
                    "followup_to_user": "{candidate}, which of these situations would you prefer? Why?",
                    "followup_seconds": 30,
                    "topic": meta["title"].lower(),
                    "keywords": _extract_keywords(p2_prompt + " " + meta["title"]) + ["first", "second", "prefer", "situation", "because"],
                },
            },
            "3": {
                "duration_seconds": 240,
                "title": meta["title"],
                "card_image": p3_card,
                "card_question": p3_disc,
                "options": (meta.get("questions") or [])[:5] or [
                    "the first idea", "the second idea", "the third idea"
                ],
                "prep_seconds": 15,
                "discussion_seconds": 120,
                "decision_seconds": 60,
                "opening": (
                    "Now, I'd like you to talk about something together for about two minutes. "
                    "Here is a topic and a question for you to discuss. First you have some time to look at the task."
                ),
                "start_discussion": f"Now, talk to each other about this: {p3_disc}",
                "decision_prompt": f"Thank you. Now you have about a minute to decide: {p3_dec}",
                "closing": "Thank you.",
                "topic": _clean_text(p3_disc.rstrip("?."), max_len=80).lower(),
                "keywords": _extract_keywords(p3_disc + " " + p3_dec + " " + meta["title"]) + ["agree", "disagree", "important", "think", "two", "option", "idea"],
            },
            "4": {
                "duration_seconds": 240,
                "topic": meta["title"].lower(),
                "prompts": ["What do you think?", "Do you agree?", "And you?"],
                "questions": q_objs,
                "closing": "Thank you. That is the end of the test.",
            },
        },
    }
