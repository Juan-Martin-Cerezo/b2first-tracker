#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 tests — privacy, zero transcripts/audio on disk or wire, no PA, history purge.

Run: python3 tests/test_speaking_v3_privacy.py
"""
import glob
import json
import os
import stat
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

import helpers  # noqa: E402
from speaking_v3 import engine  # noqa: E402
from tools import purge_speaking_history  # noqa: E402


def _req(base, method, path, payload=None, token=None, headers=None):
    hdrs = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8")
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body) if body else {}
        except ValueError:
            return e.code, {"raw": body}


def _login(base, name="priv-owner", password="PrivOwnerPass123!"):
    _req(base, "POST", "/api/register", {"name": name, "password": password})
    st, obj = _req(base, "POST", "/api/login", {"name": name, "password": password})
    assert st == 200 and obj.get("token"), (st, obj)
    return obj["token"]


def _assert_no_key_recursive(obj, forbidden_keys):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k.lower() not in forbidden_keys, f"Forbidden key found: {k}"
            _assert_no_key_recursive(v, forbidden_keys)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_key_recursive(item, forbidden_keys)


def main():
    data_dir = helpers.isolated_data_dir(prefix="b2priv-")
    base = helpers.isolated_server(
        extra_env={"B2_SPK_TEST_MODE": "1", "B2_OWNER_UIDS": "priv-owner"},
        data_dir=data_dir,
    )
    tok = _login(base)

    # 1. Legacy endpoints are all gone (404)
    for method, legacy_path in [
        ("GET", "/api/speaking/capabilities"),
        ("POST", "/api/speaking/turn"),
        ("POST", "/api/speaking/partner"),
        ("POST", "/api/speaking/report"),
        ("POST", "/api/speaking/minute"),
        ("POST", "/api/speaking/token"),
        ("POST", "/api/speaking/pa"),
    ]:
        st, _ = _req(base, method, legacy_path, {} if method == "POST" else None, token=tok)
        assert st == 404, f"Legacy route {method} {legacy_path} still returned {st}"

    # 2. Run a session with unique canary words in spoken turns
    canary_evening = "canaryEveningRelaxationZebra"
    st, sess = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "01", "part": 1}, token=tok)
    assert st == 200
    sid = sess["session_id"]
    _assert_no_key_recursive(sess, {"transcript", "transcripts", "pronunciation"})

    for spoken_text in [
        "My name is Juan",
        "I live in Buenos Aires",
        f"In the evenings I relax at home and read {canary_evening} books with my family.",
    ]:
        st, resp = _req(
            base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
            {"audio_b64": "", "mime": "audio/wav"},
            token=tok,
            headers={"X-Test-Transcript": spoken_text},
        )
        assert st == 200, (st, resp)
        _assert_no_key_recursive(resp, {"transcript", "transcripts", "pronunciation", "text"})
        raw_resp = json.dumps(resp)
        assert canary_evening not in raw_resp, "Canary transcript leaked in HTTP response!"

    # 3. Inspect session file on disk: 0600 permissions, ZERO audio, ZERO transcript, ZERO canary
    sess_path = os.path.join(data_dir, "speaking_v3", "sessions", f"{sid}.json")
    assert os.path.isfile(sess_path), f"Session file missing: {sess_path}"
    mode = stat.S_IMODE(os.stat(sess_path).st_mode)
    assert mode == 0o600, f"Expected 0600 session file, got {oct(mode)}"
    sess_raw = open(sess_path, "r", encoding="utf-8").read()
    assert canary_evening not in sess_raw, "Canary transcript found in session file!"
    sess_doc = json.loads(sess_raw)
    _assert_no_key_recursive(sess_doc, {"transcript", "transcripts", "audio", "audio_b64", "candidate_text", "pronunciation"})

    # 4. Report has ONLY 3 bands (grammar_vocabulary, discourse, interactive), NO pronunciation
    st, rep_nosave = _req(base, "POST", f"/api/speaking/v3/sessions/{sid}/report", {"save": False}, token=tok)
    assert st == 200
    assert set(rep_nosave["bands"].keys()) == {"grammar_vocabulary", "discourse", "interactive"}
    assert rep_nosave["saved"] is False
    _assert_no_key_recursive(rep_nosave, {"pronunciation", "transcript", "transcripts"})
    assert "pronunciation" not in json.dumps(rep_nosave).lower()

    # Check save:false did NOT write progress.json speaking_v3
    prog_path = os.path.join(data_dir, "users", "priv-owner", "progress.json")
    if os.path.exists(prog_path):
        prog_before = json.load(open(prog_path))
        assert not prog_before.get("speaking_v3")

    # save:true saves compact bands/flags (no transcript, no pronunciation)
    st, rep_save = _req(base, "POST", f"/api/speaking/v3/sessions/{sid}/report", {"save": True}, token=tok)
    assert st == 200 and rep_save["saved"] is True
    prog_after = json.load(open(prog_path))
    assert len(prog_after.get("speaking_v3") or []) == 1
    assert canary_evening not in json.dumps(prog_after)
    assert "pronunciation" not in json.dumps(prog_after["speaking_v3"]).lower()

    # 5. Session expires after 24 hours
    old_doc = json.load(open(sess_path))
    old_doc["updated_at"] = time.time() - (25 * 3600)
    with open(sess_path, "w", encoding="utf-8") as fh:
        json.dump(old_doc, fh)
    st_exp, exp_err = _req(
        base, "POST", f"/api/speaking/v3/sessions/{sid}/turn",
        {"audio_b64": "", "mime": "audio/wav"},
        token=tok,
        headers={"X-Test-Transcript": "hello"},
    )
    assert st_exp == 410 and exp_err.get("error") == "session_expired", (st_exp, exp_err)
    assert not os.path.exists(sess_path)

    # 6. Without API key and outside test mode -> clear 503 speech_not_configured (no simulated audio!)
    old_test_mode = os.environ.pop("B2_SPK_TEST_MODE", None)
    old_key = os.environ.pop("B2_SPK_GOOGLE_KEY", None)
    try:
        st_nc, err_nc = _req(base, "POST", "/api/speaking/v3/sessions", {"test_id": "01", "part": 1}, token=tok)
        assert st_nc == 503 and err_nc.get("error") == "speech_not_configured", (st_nc, err_nc)
    finally:
        if old_test_mode is not None:
            os.environ["B2_SPK_TEST_MODE"] = old_test_mode
        if old_key is not None:
            os.environ["B2_SPK_GOOGLE_KEY"] = old_key

    # 7. Test purge_speaking_history tool on a mock data dir
    mock_data = tempfile.mkdtemp(prefix="b2purge-")
    u1_dir = os.path.join(mock_data, "users", "alice")
    os.makedirs(os.path.join(u1_dir, "speaking"), exist_ok=True)
    with open(os.path.join(u1_dir, "progress.json"), "w", encoding="utf-8") as fh:
        json.dump({"profile": {"name": "Alice"}, "writing": [{"band": 4}], "speaking": [{"old": 1}], "spxCustom": [{"x": 2}]}, fh)
    with open(os.path.join(u1_dir, "speaking", "old-tx.json"), "w", encoding="utf-8") as fh:
        json.dump({"transcript": "old"}, fh)
    os.makedirs(os.path.join(mock_data, "speaking_old"), exist_ok=True)
    os.makedirs(os.path.join(mock_data, "speaking_v3", "sessions"), exist_ok=True)
    with open(os.path.join(mock_data, "speaking_v3", "sessions", "keep.json"), "w", encoding="utf-8") as fh:
        json.dump({"keep": True}, fh)

    summary = purge_speaking_history.purge_speaking_history(data_dir=mock_data)
    assert summary["users_touched"] == 1
    assert summary["backup_path"] and os.path.isfile(summary["backup_path"])
    with tarfile.open(summary["backup_path"], "r:gz") as tar:
        names = tar.getnames()
        assert any("alice/progress.json" in n for n in names), names
    alice_after = json.load(open(os.path.join(u1_dir, "progress.json")))
    assert "speaking" not in alice_after and "spxCustom" not in alice_after
    assert alice_after["profile"] == {"name": "Alice"} and alice_after["writing"] == [{"band": 4}]
    assert not os.path.exists(os.path.join(mock_data, "speaking_old"))
    assert not os.path.exists(os.path.join(u1_dir, "speaking"))
    assert os.path.isfile(os.path.join(mock_data, "speaking_v3", "sessions", "keep.json"))

    # 8. Also verify live repo data/users/*/progress.json has been purged of legacy speaking keys
    for pf in glob.glob(os.path.join(REPO_ROOT, "data", "users", "*", "progress.json")):
        doc = json.load(open(pf, encoding="utf-8"))
        assert "speaking" not in doc, f"Legacy 'speaking' key still in {pf}"
        assert "spxCustom" not in doc, f"Legacy 'spxCustom' key still in {pf}"

    print("PASS test_speaking_v3_privacy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
