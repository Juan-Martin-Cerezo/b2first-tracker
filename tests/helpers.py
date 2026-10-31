"""Helpers for the tests: start a session before interacting with the app.

The frontend requires a session. Tests must NOT depend on the owner's real
password (it is a human secret and it gets rotated), so they use a dedicated
account that the helper registers on first use and reuses afterwards.

Override with B2_TEST_USER / B2_TEST_PASS when running against another host.

Isolation (mandatory for anything that creates accounts): call
`isolated_server()` before touching the app. It starts the real `server.py`
on a free port with a throwaway data directory, so account records, tokens
and progress never land in the repo's `data/`.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OWNER_NAME = os.environ.get("B2_TEST_USER", "test-runner")
OWNER_PASS = os.environ.get("B2_TEST_PASS", "test-runner-pass-9")


def _api(url, path, payload, token=None):
    import json
    import urllib.request

    req = urllib.request.Request(
        url + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def _ensure_account(url, name, password):
    """Register the account if it does not exist yet (ignore 409)."""
    import urllib.error

    try:
        _api(url, "api/register", {"name": name, "password": password})
    except urllib.error.HTTPError:
        return  # already registered (409) or registration closed: try login
    except Exception:
        return


def login_user(pg, url, name, password, register=True):
    """Log an arbitrary account in via the API and set the session locally.

    Returns the user record (id, name, color, token) so suites can seed their
    own progress document without borrowing the shared test account.
    """
    import json

    if register:
        _ensure_account(url, name, password)
    u = _api(url, "api/login", {"name": name, "password": password})
    pg.evaluate(
        "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(u))
    )
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    dismiss_onboarding(pg)
    return u


def dismiss_onboarding(pg):
    """Get the mandatory first-run setup out of the way.

    Suite accounts are created empty on purpose, so the app walks them through the
    onboarding — which covers the whole page and makes every later click time out.
    The app's own flag is set, not a test-only backdoor, and any tour overlay that
    is already on screen is hidden.
    """
    pg.evaluate("""() => {
        try { D.onboarded = true; if (typeof save === 'function') save(); } catch (e) {}
        for (const id of ['onboardingOverlay', 'tourOverlay', 'obOverlay']) {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        }
        document.body.classList.remove('ob-open', 'tour-open');
    }""")
    pg.wait_for_timeout(250)


def login_owner(pg, url):
    """Log in as the shared throwaway test account."""
    return login_user(pg, url, OWNER_NAME, OWNER_PASS)


# ---------------------------------------------------------------------------
# Isolation: one temporary data dir per suite, never the repo's data/
# ---------------------------------------------------------------------------

def isolated_data_dir(prefix="b2test-"):
    """Create a throwaway data dir and export it as B2_DATA_DIR.

    server.py reads the variable at import time, so this must run before the
    first `import server`. Safe to call again later: the newest dir wins.
    """
    import tempfile

    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    path = tempfile.mkdtemp(prefix=prefix)
    os.environ["B2_DATA_DIR"] = path
    return path


def _adopt_data_dir(path):
    """Point server.py and store.py at `path`, whatever they were imported with."""
    import server as S
    import store

    S.DATA_DIR = path
    store.DATA_DIR = path
    # server.py derives these at import time; re-derive them for the new dir.
    S.PROG_FILE = os.path.join(path, "progress.json")
    S.BK_DIR = os.path.join(path, "backups")
    S.USERS_FILE = os.path.join(path, "users.json")
    S.TOKENS_FILE = os.path.join(path, "tokens.json")
    S.USERS_DIR = os.path.join(path, "users")
    return S


def isolated_server(extra_env=None, data_dir=None):
    """Start the real server.py on a free port over a private, empty data dir.

    Returns the base URL without a trailing slash. The server is shut down at
    interpreter exit (atexit): the request handler logs to stdout, so letting a
    daemon thread die during finalization aborts the process with a
    `_enter_buffered_busy` fatal error. `extra_env` is applied before the server
    module is imported (its config is read then).
    """
    import atexit
    import threading

    path = data_dir or isolated_data_dir()
    for k, v in (extra_env or {}).items():
        os.environ[str(k)] = str(v)
    S = _adopt_data_dir(path)
    srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    def _stop():
        srv.shutdown()
        srv.server_close()          # waits for in-flight handlers (block_on_close)
        thread.join(2)

    atexit.register(_stop)
    return "http://127.0.0.1:%d" % srv.server_address[1]

