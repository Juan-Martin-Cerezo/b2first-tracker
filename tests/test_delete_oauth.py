"""Delete-account contract for accounts without a local password (Google-only).

A Google sign-up creates the local record with ``password_set: false``: there is
no password to type, so the live session is the proof of ownership. The UI used
to demand one anyway, which made "Delete my account" fail for every Google
account. This suite pins both halves of the fix:

  * ``GET /api/account`` reports ``has_password`` so the UI can hide the field;
  * ``DELETE /api/account`` with an empty body deletes a password-less account,
    while a normal account still needs its password.

Run with:  uv run --with playwright python test_delete_oauth.py
(the server comes from helpers.isolated_server; Playwright is not needed but is
tolerated by the shared helper module).
"""
import json
import os
import sys

from helpers import isolated_server, login_user, isolated_data_dir

URL = isolated_server() + "/"

FAILS = []


def check(name, ok, detail=""):
    print(("OK " if ok else "FAIL ") + name + ((" :: " + str(detail)) if not ok else ""))
    if not ok:
        FAILS.append(name)


def req(method, path, payload=None, token=None):
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(URL + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def users_file():
    for root, _dirs, files in os.walk(os.environ["B2_DATA_DIR"]):
        if "users.json" in files and os.path.dirname(root) == os.environ["B2_DATA_DIR"]:
            return os.path.join(root, "users.json")
    return os.path.join(os.environ["B2_DATA_DIR"], "users.json")


def mark_no_password(uid):
    path = users_file()
    with open(path, encoding="utf-8") as f:
        users = json.load(f)
    users[uid]["password_set"] = False
    users[uid]["oauth"] = True
    with open(path, "w", encoding="utf-8") as f:
        json.dump(users, f)


def main():
    import server as S  # noqa: F401  (ensures the isolated dir is adopted)

    with __import__("playwright.sync_api", fromlist=["sync_playwright"]).sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_context().new_page()
        pg.goto(URL)

        # 1. A Google-only account: has_password=false and delete with {} works.
        g = login_user(pg, URL, "oauth-deleter", "oauth-deleter-pass-9")
        mark_no_password(g["id"])
        status, body = req("GET", "/api/account", token=g["token"])
        j = json.loads(body) if status == 200 else {}
        check("1a_get_account_200", status == 200, (status, body[:120]))
        check("1b_has_password_false", j.get("has_password") is False, j.get("has_password"))
        check("1c_oauth_flag", j.get("oauth") is True, j.get("oauth"))
        status, body = req("DELETE", "/api/account", {}, token=g["token"])
        check("2a_delete_without_password_200", status == 200, (status, body[:160]))
        users = json.load(open(users_file(), encoding="utf-8"))
        check("2b_record_gone", g["id"] not in users, g["id"])
        check("2c_data_dir_gone",
              not os.path.isdir(os.path.join(os.environ["B2_DATA_DIR"], "users", g["id"])))
        status, _ = req("GET", "/api/account", token=g["token"])
        check("2d_token_dead", status == 401, status)

        # 2. A normal account still needs the password.
        n = login_user(pg, URL, "password-keeper", "password-keeper-pass-9")
        status, body = req("GET", "/api/account", token=n["token"])
        j = json.loads(body) if status == 200 else {}
        check("3a_has_password_true", j.get("has_password") is True, j.get("has_password"))
        status, _ = req("DELETE", "/api/account", {}, token=n["token"])
        check("3b_empty_body_refused", status == 401, status)
        status, _ = req("DELETE", "/api/account", {"password": "wrong-password-9"}, token=n["token"])
        check("3c_wrong_password_refused", status == 401, status)
        users = json.load(open(users_file(), encoding="utf-8"))
        check("3d_record_still_there", n["id"] in users)
        status, _ = req("DELETE", "/api/account", {"password": "password-keeper-pass-9"},
                        token=n["token"])
        check("3e_right_password_deletes", status == 200, status)

        br.close()

    print("\nexit", 1 if FAILS else 0, "fails:", FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
