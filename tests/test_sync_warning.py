"""B6: a permanent sync failure must be visible on the main screen.

A >500-char field makes PUT /api/progress answer 422; the topbar pill becomes
visible and the state is 'invalid'. Healthy data clears both.

    cd tests && uv run --with playwright python test_sync_warning.py
"""
import sys

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
failed = []


def check(name, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + name + ((" :: " + str(detail)) if not cond and detail else ""))
    if not cond:
        failed.append(name)


def state(pg):
    return pg.evaluate("""() => {
        const pill = document.getElementById('syncWarnPill');
        return {
            state: SYNC_STATE,
            field: SYNC_INVALID_FIELD,
            pill: pill ? getComputedStyle(pill).display : 'missing'
        };
    }""")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(URL + "app", wait_until="networkidle")
        login_user(pg, URL, "sync-warning", "sync-warning-pass-9")

        pg.evaluate("""() => {
            D.errs = [{date: '2026-01-01', code: 'G-ERR', desc: 'x'.repeat(600)}];
            save();
        }""")
        pg.wait_for_timeout(1400)
        bad = state(pg)
        print("after long field:", bad)
        check("state becomes invalid", bad["state"] == "invalid", bad["state"])
        check("server named the rejected field", bad["field"] != "", bad["field"])
        check("topbar pill is visible", bad["pill"] != "none", bad["pill"])

        pg.evaluate("""() => {
            D.errs = [{date: '2026-01-01', code: 'G-ERR', desc: 'short note'}];
            save();
        }""")
        pg.wait_for_timeout(1400)
        good = state(pg)
        print("after healthy data:", good)
        check("state returns to ok", good["state"] == "ok", good["state"])
        check("topbar pill is hidden", good["pill"] == "none", good["pill"])

        # The long-text inputs advertise the server's cap.
        caps = pg.evaluate("""() => {
            const ids = ['ueRef','soloRef','soloErrDesc','wPrompt','errDesc','errFix','errDesc2','errFix2','iaText'];
            const out = {};
            ids.forEach(id => { const el = document.getElementById(id); out[id] = el ? el.getAttribute('maxlength') : 'missing'; });
            return out;
        }""")
        print("maxlengths:", caps)
        for fid in ["ueRef", "soloRef", "soloErrDesc", "wPrompt", "errDesc", "errFix", "errDesc2", "errFix2"]:
            check(f"#{fid} maxlength 400", caps[fid] == "400", caps[fid])
        check("#iaText maxlength 4000", caps["iaText"] == "4000", caps["iaText"])

        browser.close()

    print()
    if failed:
        print("VERDICT: FAIL", failed)
        sys.exit(1)
    print("VERDICT: ok")


if __name__ == "__main__":
    main()
