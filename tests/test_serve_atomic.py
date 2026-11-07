"""Phase 115: /app never serves a half-written index.html.

The runner rewrites index.html in place while the server is live. A request
that lands mid-write used to receive the markup before the <script> defining
its handlers, which produced `ReferenceError: onLPartChange is not defined`.

This suite copies the real document to a temp file, points the running server
at it, and rewrites it the way a deploy would: truncated in half, empty,
restored with a marker, then deleted. Every interrupted state must keep serving
the last complete copy, byte for byte.

Run with:  uv run --with playwright python test_serve_atomic.py
"""
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request

from helpers import isolated_server

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = isolated_server()

sys.path.insert(0, REPO_ROOT)
import server as S  # noqa: E402  (after isolated_server configures DATA_DIR)

SRC = os.path.join(REPO_ROOT, "index.html")
TMP = tempfile.mkdtemp(prefix="b2atomic-")
TARGET = os.path.join(TMP, "index.html")
shutil.copyfile(SRC, TARGET)

# The server reads the module global on every request, so this switches the
# served document without touching the real index.html.
S.TRACKER = TARGET


def get(path="/app"):
    """Return (status, body) for a GET, including error statuses."""
    try:
        with urllib.request.urlopen(URL + path) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def write(data):
    with open(TARGET, "wb") as f:
        f.write(data)


def check_complete(body, label):
    assert b"</html>" in body, f"{label}: served document is not closed"
    assert b"onLPartChange" in body, f"{label}: handler is missing from the body"


def main():
    status, original = get()
    assert status == 200, f"initial /app answered {status}"
    check_complete(original, "initial")
    assert b"onLPartChange" in original

    # 1. Rewrite interrupted at half the file: keep the last good copy.
    write(original[: len(original) // 2])
    status, half = get()
    assert status == 200, f"truncated /app answered {status}"
    assert half == original, "a half-written index.html leaked to the client"
    check_complete(half, "truncated")

    # 2. Empty file (the writer opened it but has not written yet).
    write(b"")
    status, empty = get()
    assert status == 200, f"empty /app answered {status}"
    assert empty == original, "an empty index.html leaked to the client"
    check_complete(empty, "empty")

    # 3. Restore the document plus a marker: the new version must be served.
    marker = b"\n<!-- atomic-serve-marker -->\n"
    updated = original + marker
    write(updated)
    status, fresh = get()
    assert status == 200, f"restored /app answered {status}"
    assert fresh == updated, "the restored document was not picked up"
    assert marker in fresh

    # 4. Deleted file: still serve the last good copy.
    os.remove(TARGET)
    status, gone = get()
    assert status == 200, f"missing /app answered {status}"
    assert gone == updated, "a missing index.html dropped the last good copy"
    check_complete(gone, "deleted")

    # 5. No valid copy was ever cached: 503 with a clear page, never empty HTML.
    S.TRACKER = os.path.join(TMP, "never-existed.html")
    status, body = get()
    assert status == 503, f"unavailable /app answered {status}"
    assert b"temporarily unavailable" in body.lower()

    # 6. B2_NO_CACHE=1: truncating the file and requesting /app still returns
    # the good HTML (and omits ETag) — atomic protection does not depend on cache.
    target_nc = os.path.join(TMP, "index-nocache.html")
    shutil.copyfile(SRC, target_nc)
    S.TRACKER = target_nc
    os.environ["B2_NO_CACHE"] = "1"
    S.B2_NO_CACHE = True
    try:
        with urllib.request.urlopen(URL + "/app") as r:
            assert r.status == 200, f"B2_NO_CACHE=1 initial /app answered {r.status}"
            assert r.headers.get("ETag") is None, "B2_NO_CACHE=1 sent an ETag"
            assert r.read() == original
        with open(target_nc, "wb") as f:
            f.write(original[: len(original) // 2])
        with urllib.request.urlopen(URL + "/app") as r:
            nc_half = r.read()
            assert r.status == 200, f"B2_NO_CACHE=1 truncated /app answered {r.status}"
            assert r.headers.get("ETag") is None, "B2_NO_CACHE=1 sent an ETag on fallback"
        assert nc_half == original, "B2_NO_CACHE=1 leaked a truncated index.html"
        check_complete(nc_half, "no-cache-truncated")
    finally:
        os.environ.pop("B2_NO_CACHE", None)
        S.B2_NO_CACHE = False

    # The rejected reads must be recorded without exposing any content.
    data_dir = os.environ.get("B2_DATA_DIR", "")
    errors = os.path.join(data_dir, "errors") if data_dir else ""
    assert errors and os.path.isdir(errors), "invalid reads were not logged"
    joined = b""
    for name in os.listdir(errors):
        if name.endswith(".jsonl"):
            with open(os.path.join(errors, name), "rb") as f:
                joined += f.read()
    assert b"invalid_static" in joined, "invalid_static was not recorded"

    print("atomic serve OK: half, empty, restored, deleted, unavailable, B2_NO_CACHE=1")


if __name__ == "__main__":
    main()
