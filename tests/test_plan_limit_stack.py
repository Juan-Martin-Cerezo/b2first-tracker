"""B2: the plan-limit modal must stack above the Speaking exam overlay.

Open the speaking exam (`.spx-overlay` at z-index 1200) and then show the
plan-limit modal. The element that actually receives a click at the centre of
the modal must belong to the modal, not to `#spxPanel`.

    cd tests && uv run --with playwright python test_plan_limit_stack.py
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


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(URL + "app", wait_until="networkidle")
        login_user(pg, URL, "limit-stack", "limit-stack-pass-9")

        pg.evaluate("try{openSpeakingExam()}catch(e){}")
        pg.wait_for_timeout(300)
        check("speaking overlay open",
              pg.evaluate("getComputedStyle(document.getElementById('spxOverlay')).display!=='none'"))
        pg.evaluate("showPlanLimit()")
        pg.wait_for_timeout(200)
        check("plan limit modal open",
              pg.evaluate("getComputedStyle(document.getElementById('planLimitModal')).display!=='none'"))

        hit = pg.evaluate("""() => {
            const card=document.querySelector('#planLimitModal .auth-card');
            if(!card)return {inModal:false,tag:'no-card'};
            const r=card.getBoundingClientRect();
            const el=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
            return {
                inModal: !!(el && el.closest('#planLimitModal')),
                tag: el ? el.tagName+'.'+String(el.className||'') : 'none',
                z: getComputedStyle(document.getElementById('planLimitModal')).zIndex
            };
        }""")
        check("click centre lands inside the modal", hit["inModal"], hit)
        print("hit:", hit)
        browser.close()

    print()
    if failed:
        print("VERDICT: FAIL", failed)
        sys.exit(1)
    print("VERDICT: ok")


if __name__ == "__main__":
    main()
