"""B7: syncPull() must preserve speaking state and merge instead of clobbering.

(a) D.speaking survives a pull whose server document has no speaking.
(b) Newer local edits are kept (and pushed) instead of being overwritten.
(c) A newer server document is merged by stable key, without duplicates.

    cd tests && uv run --with playwright python test_sync_merge.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
failed = []
SERVER = {}


def check(name, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + name + ((" :: " + str(detail)) if not cond and detail else ""))
    if not cond:
        failed.append(name)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(URL + "app", wait_until="networkidle")
        login_user(pg, URL, "sync-merge", "sync-merge-pass-9")

        def handler(route):
            req = route.request
            if req.method == "PUT":
                route.fulfill(status=200, content_type="application/json", body='{"ok":true}')
            else:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(SERVER))

        pg.route("**/api/progress*", handler)

        # (a) speaking survives a pull that does not carry it
        SERVER.clear()
        SERVER.update({"log": [], "errs": [], "updated_at": 2000, "settings": {}})
        pg.evaluate("""() => {
            D.speaking = {seen: {'1': ['p1']}, last: {}, partnerRot: 2};
            D.updated_at = 1000;
            syncStatus('ok');
        }""")
        spk = pg.evaluate("syncPull().then(() => D.speaking)")
        print("speaking after pull:", spk)
        check("D.speaking survives pull", isinstance(spk, dict) and spk.get("partnerRot") == 2, spk)
        check("D.speaking.seen survives pull",
              isinstance(spk, dict) and spk.get("seen", {}).get("1") == ["p1"], spk)

        # (b) newer local state with pending changes is not replaced
        SERVER.clear()
        SERVER.update({"log": [{"id": "srv-old", "type": "l", "date": "2026-01-01"}],
                       "errs": [], "updated_at": 1000, "settings": {}})
        pg.evaluate("""() => {
            D.log = [{id: 'local-new', type: 'ue', date: '2026-02-01', created_at: 5}];
            D.updated_at = 5000;
            syncStatus('local');
        }""")
        res = pg.evaluate("syncPull().then(() => ({log: D.log, ts: D.updated_at}))")
        print("local-newer result:", res)
        ids = [e.get("id") for e in res["log"]]
        check("newer local entry is kept", "local-new" in ids, ids)
        check("older server entry does not overwrite it", "srv-old" not in ids, ids)
        check("local timestamp is unchanged", res["ts"] == 5000, res["ts"])

        # (c) newer server document is merged by key, no duplicates
        SERVER.clear()
        SERVER.update({
            "log": [{"id": "B", "type": "w", "date": "2026-03-02", "created_at": 2},
                    {"id": "C", "type": "w", "date": "2026-03-03", "created_at": 3}],
            "errs": [{"id": "e1", "date": "2026-03-01"}, {"id": "e2", "date": "2026-03-02"}],
            "updated_at": 9000, "settings": {}})
        pg.evaluate("""() => {
            D.log = [{id: 'A', type: 'ue', date: '2026-03-01', created_at: 1},
                     {id: 'B', type: 'w', date: '2026-03-02', created_at: 2}];
            D.errs = [{id: 'e1', date: '2026-03-01'}];
            D.updated_at = 1000;
            syncStatus('ok');
        }""")
        merged = pg.evaluate("syncPull().then(() => ({log: D.log, errs: D.errs}))")
        log_ids = [e.get("id") for e in merged["log"]]
        err_ids = [e.get("id") for e in merged["errs"]]
        print("merged log:", log_ids, "errs:", err_ids)
        check("merged log keeps A, B and C", sorted(log_ids) == ["A", "B", "C"], log_ids)
        check("merged log has no duplicate B", log_ids.count("B") == 1, log_ids)
        check("merged errs has no duplicate e1", err_ids.count("e1") == 1, err_ids)
        check("merged errs keeps both e1 and e2", sorted(err_ids) == ["e1", "e2"], err_ids)

        browser.close()

    print()
    if failed:
        print("VERDICT: FAIL", failed)
        sys.exit(1)
    print("VERDICT: ok")


if __name__ == "__main__":
    main()
