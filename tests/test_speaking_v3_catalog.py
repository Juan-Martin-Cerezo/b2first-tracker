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
from speaking_v3 import catalog, engine, tone  # noqa: E402


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
    expected_partner_sex = {"01": "male", "02": "female", "03": "male", "04": "female"}
    partners = set()
    for t in tests:
        assert set(t.keys()) == {"id", "title", "variant", "partner", "partner_sex", "parts"}, t.keys()
        assert t["title"] == expected_titles[t["id"]], t
        assert t["variant"] == expected_variants[t["id"]], t
        assert t["partner_sex"] == expected_partner_sex[t["id"]], t
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
        assert doc["partner"]["sex"] == expected_partner_sex[tid], (tid, doc["partner"])
        assert doc["examiner"] == {"name": "Mr Thompson", "sex": "male"}, (tid, doc.get("examiner"))
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

    # 4. Sex normalisation, tone examiner-name override, and session API metadata
    assert catalog.normalize_sex("female") == "female"
    assert catalog.normalize_sex("FEMALE") == "female"
    assert catalog.normalize_sex("male") == "male"
    for bad_sex in ("invalid", "other", "", None, 42):
        assert catalog.normalize_sex(bad_sex) == "male", bad_sex
    norm_doc = catalog._normalize_test_doc({
        "id": "99",
        "partner": {"name": "Sam", "sex": "invalid_value"},
        "examiner": {"name": "Ms Clarke", "sex": "not_valid"},
    })
    assert norm_doc["partner"]["sex"] == "male", norm_doc
    assert norm_doc["examiner"] == {"name": "Ms Clarke", "sex": "male"}, norm_doc

    greet_override = tone.opening_greeting(hour=10, examiner_name="Ms Clarke")
    assert greet_override == "Good morning. My name is Ms Clarke. And your names are?", greet_override
    assert tone.check_examiner_line(greet_override) == []

    # Own-task partner_sex validation: default male, accept female, reject invalid
    helpers.isolated_data_dir(prefix="b2cat-own-")
    import store
    store.DATA_DIR = os.environ["B2_DATA_DIR"]
    os.environ["B2_SPK_TEST_MODE"] = "1"
    own_bad, own_code, own_err = catalog.create_own_task(
        "cat-own-u",
        {"title": ["Bad sex"], "part": ["1"], "questions": ["How are you?"], "partner_sex": ["robot"]},
        {},
    )
    assert own_bad is None and own_code == 422 and own_err == "invalid_partner_sex"
    own_ok, own_code2, own_err2 = catalog.create_own_task(
        "cat-own-u",
        {"title": ["Female partner task"], "part": ["1"], "questions": ["How are you?"], "partner_sex": ["female"]},
        {},
    )
    assert own_code2 == 201 and own_err2 is None and own_ok["partner_sex"] == "female", own_ok
    own_test = catalog.get_own_task_as_test("cat-own-u", own_ok["id"])
    assert own_test["partner"]["sex"] == "female" and own_test["examiner"]["sex"] == "male"

    # Session API tests against live isolated server: paper 02 -> female, paper 01 -> male
    st_s2, s2 = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "02", "part": 1}, token=tok)
    assert st_s2 == 200, (st_s2, s2)
    assert s2["partner_sex"] == "female", s2
    assert s2["examiner_name"] == "Mr Thompson" and s2["examiner_sex"] == "male", s2
    assert s2["state"]["partner_sex"] == "female" and s2["state"]["examiner_sex"] == "male", s2

    st_s1, s1 = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "01", "part": 1}, token=tok)
    assert st_s1 == 200, (st_s1, s1)
    assert s1["partner_sex"] == "male", s1
    assert s1["examiner_name"] == "Mr Thompson" and s1["examiner_sex"] == "male", s1
    assert s1["state"]["partner_sex"] == "male" and s1["state"]["examiner_sex"] == "male", s1

    # Session whose test JSON lacks partner.sex and examiner -> defaults to male / Mr Thompson without error
    base_doc = json.loads(json.dumps(catalog.get_test("01")))
    base_doc["partner"].pop("sex", None)
    base_doc.pop("examiner", None)
    orig_get_test = catalog.get_test
    catalog.get_test = lambda tid: base_doc
    try:
        res_missing, code_missing, err_missing = engine.create_session("cat-own-u", test_id="01", part=1, hour=10)
        assert code_missing == 200 and err_missing is None, (code_missing, err_missing)
        assert res_missing["partner_sex"] == "male", res_missing
        assert res_missing["examiner_name"] == "Mr Thompson" and res_missing["examiner_sex"] == "male", res_missing
        assert res_missing["state"]["partner_sex"] == "male", res_missing
    finally:
        catalog.get_test = orig_get_test

    print("PASS test_speaking_v3_catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
