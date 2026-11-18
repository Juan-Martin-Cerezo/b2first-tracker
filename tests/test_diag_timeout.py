"""B5: a diagnostic timeout must not erase answers already given.

Three correct answers followed by finishDiag(true) must keep correct === 3 and
tag only the nine unanswered items as T-LIM.

    cd tests && uv run --with playwright python test_diag_timeout.py
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


SETUP = """() => {
    const items = [];
    for (let i = 0; i < 12; i++) items.push({part: 1, answer: 0, taxonomy: 'G-ERR',
        explain: 'x', options: ['A', 'B', 'C', 'D']});
    DIAG_STATE.status = 'running';
    DIAG_STATE.items = items;
    DIAG_STATE.answers = {
        0: {choice: 0, timedOut: false},
        1: {choice: 0, timedOut: false},
        2: {choice: 0, timedOut: false}
    };
    DIAG_STATE.idx = 3;
    DIAG_STATE.totalSec = 600;
    DIAG_STATE.leftSec = 0;
    DIAG_STATE.startedAt = Date.now() - 1000;
    DIAG_STATE.iv = null;
    D.errs = [];
    D.log = [];
    D.diag = null;
    D.onboarded = true;
    finishDiag(true);
    return {
        correct: D.diag ? D.diag.correct : null,
        total: D.diag ? D.diag.total : null,
        tlim: D.errs.filter(e => e && e.tax === 'T-LIM').length,
        other: D.errs.filter(e => e && e.tax !== 'T-LIM').length
    };
}"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(URL + "app", wait_until="networkidle")
        login_user(pg, URL, "diag-timeout", "diag-timeout-pass-9")

        res = pg.evaluate(SETUP)
        print("result:", res)
        check("answered items keep their score", res["correct"] == 3, res["correct"])
        check("total is still 12", res["total"] == 12, res["total"])
        check("only unanswered items are T-LIM", res["tlim"] == 9, res["tlim"])
        check("answered wrong items keep their taxonomy", res["other"] == 0, res["other"])
        browser.close()

    print()
    if failed:
        print("VERDICT: FAIL", failed)
        sys.exit(1)
    print("VERDICT: ok")


if __name__ == "__main__":
    main()
