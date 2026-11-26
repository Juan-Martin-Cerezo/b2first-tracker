#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 tests — catalog of 4 Cambridge tests, assets, credits, clean images.

Run: python3 tests/test_speaking_v3_catalog.py
"""
import json
import os
import struct
import sys
import urllib.error
import urllib.request

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

import helpers  # noqa: E402
from speaking_v3 import catalog  # noqa: E402


def _req(base, method, path, payload=None, token=None):
    hdrs = {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _get_bytes(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def _png_dimensions(raw):
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", raw[16:24])
    return w, h


def _jpeg_dimensions(raw):
    assert raw[:3] == b"\xff\xd8\xff"
    i = 2
    while i < len(raw) - 9:
        if raw[i] != 0xFF:
            i += 1
            continue
        marker = raw[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", raw[i + 5:i + 9])
            return w, h
        if marker in (0xD8, 0xD9, 0x01) or (0xD0 <= marker <= 0xD7):
            i += 2
        else:
            seg_len = struct.unpack(">H", raw[i + 2:i + 4])[0]
            i += 2 + seg_len
    raise AssertionError("Could not parse JPEG dimensions")


def main():
    base = helpers.isolated_server(extra_env={"B2_SPK_TEST_MODE": "1"})
    _req(base, "POST", "/api/register", {"name": "cat-user", "password": "CatUserPass123!"})
    st, login = _req(base, "POST", "/api/login", {"name": "cat-user", "password": "CatUserPass123!"})
    assert st == 200
    tok = login["token"]

    # 1. GET /api/speaking/v3/catalog returns exactly 4 tests, no scripts/answers
    st, cat = _req(base, "GET", "/api/speaking/v3/catalog", token=tok)
    assert st == 200, (st, cat)
    tests = cat["tests"]
    assert len(tests) == 4, len(tests)
    assert [t["id"] for t in tests] == ["01", "02", "03", "04"]

    expected_titles = {
        "01": "B2 First Sample Paper 1",
        "02": "B2 First Sample Paper 2",
        "03": "B2 First for Schools Sample Paper 1",
        "04": "B2 First for Schools Sample Paper 2",
    }
    expected_variants = {"01": "first", "02": "first", "03": "for_schools", "04": "for_schools"}
    partners = set()
    for t in tests:
        assert set(t.keys()) == {"id", "title", "variant", "partner", "parts"}, t.keys()
        assert t["title"] == expected_titles[t["id"]], t
        assert t["variant"] == expected_variants[t["id"]], t
        assert t["parts"] == [1, 2, 3, 4]
        assert isinstance(t["partner"], str) and len(t["partner"]) >= 2
        partners.add(t["partner"])
    assert len(partners) == 4, f"Each test should have its own partner: {partners}"

    # Verify catalog never leaks scripts or questions
    cat_str = json.dumps(cat).lower()
    for secret in ("how do you like to spend", "all right?", "partner_monologue", "keywords", "decision_prompt"):
        assert secret not in cat_str, f"Catalog leaked script token: {secret}"

    # 2. Verify all 4 internal test JSONs + all 20 assets exist, serve HTTP 200, have clean dimensions & no examiner text
    all_tests = catalog.load_all_tests(force_reload=True)
    assert sorted(all_tests.keys()) == ["01", "02", "03", "04"]

    forbidden_asset_markers = (b"Interlocutor", b"Candidate A", b"Place Part 2 booklet", b"Retrieve Part")
    for tid, doc in sorted(all_tests.items()):
        assert set(doc["parts"].keys()) == {"1", "2", "3", "4"}
        assert doc["parts"]["1"]["duration_seconds"] == 120
        assert doc["parts"]["2"]["duration_seconds"] == 240
        assert doc["parts"]["3"]["duration_seconds"] == 240
        assert doc["parts"]["4"]["duration_seconds"] == 240

        p2_imgs = doc["images"]["part2_task1"] + doc["images"]["part2_task2"]
        assert len(p2_imgs) == 4
        for url in p2_imgs:
            assert url.startswith(f"/assets/speaking/exams/{tid}/")
            disk_path = os.path.join(REPO_ROOT, url.lstrip("/"))
            assert os.path.isfile(disk_path), f"Missing asset: {disk_path}"
            st_i, ctype, raw = _get_bytes(base, url)
            assert st_i == 200 and "jpeg" in ctype.lower()
            w, h = _jpeg_dimensions(raw)
            assert w >= 200 and h >= 200, (url, w, h)
            for marker in forbidden_asset_markers:
                assert marker not in raw, f"Examiner text marker {marker} found in {url}"

        card_url = doc["images"]["part3_card"]
        assert card_url == f"/assets/speaking/exams/{tid}/p3-card.png"
        card_path = os.path.join(REPO_ROOT, card_url.lstrip("/"))
        assert os.path.isfile(card_path), f"Missing Part 3 card: {card_path}"
        st_c, ctype_c, raw_c = _get_bytes(base, card_url)
        assert st_c == 200 and "png" in ctype_c.lower()
        cw, ch = _png_dimensions(raw_c)
        assert cw >= 300 and ch >= 150, (card_url, cw, ch)
        for marker in forbidden_asset_markers:
            assert marker not in raw_c, f"Examiner text marker {marker} found in {card_url}"

    # 3. Verify CREDITS.md exists and attributes Cambridge sample papers for personal practice
    credits_path = os.path.join(REPO_ROOT, "assets", "speaking", "exams", "CREDITS.md")
    assert os.path.isfile(credits_path)
    credits_txt = open(credits_path, "r", encoding="utf-8").read()
    assert "Cambridge" in credits_txt
    assert "personal" in credits_txt.lower()
    assert "redistribute" in credits_txt.lower()

    print("PASS test_speaking_v3_catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
