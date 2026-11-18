"""B1: passkey sign-in and passkey management must be reachable.

With WebAuthn available, `#passkeyLoginBtn` is shown and `#passkeySection`
inside the profile modal is visible; without it, both stay hidden and the
profile explains why. The modal must also carry exactly one `#passkeyStatus`
and one `#passkeyAddBtn` (the duplicate orphan pair used to make the visible
"Add a passkey" button write into a hidden node).

    cd tests && uv run --with playwright python test_passkey_ui.py
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


WITH_PK = "window.PublicKeyCredential=window.PublicKeyCredential||function(){};"
NO_PK = ("try{Object.defineProperty(window,'PublicKeyCredential',"
         "{value:undefined,configurable:true,writable:true})}"
         "catch(e){window.PublicKeyCredential=undefined}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        ctx = browser.new_context()
        pg = ctx.new_page()
        pg.add_init_script(WITH_PK)
        pg.goto(URL + "app", wait_until="networkidle")
        pg.wait_for_timeout(400)
        check("webauthn present", pg.evaluate("!!window.PublicKeyCredential"))
        check("login button visible",
              pg.evaluate("getComputedStyle(document.getElementById('passkeyLoginBtn')).display!=='none'"))
        check("alt separator visible",
              pg.evaluate("getComputedStyle(document.getElementById('authAltSep')).display!=='none'"))
        login_user(pg, URL, "passkey-ui", "passkey-ui-pass-9")
        pg.evaluate("openUserModal()")
        pg.wait_for_timeout(400)
        check("profile passkey section visible",
              pg.evaluate("getComputedStyle(document.getElementById('passkeySection')).display!=='none'"))
        check("no unsupported notice when supported",
              pg.evaluate("getComputedStyle(document.getElementById('passkeyUnsupported')).display==='none'"))
        check("single #passkeyStatus",
              pg.evaluate("document.querySelectorAll('#passkeyStatus').length===1"),
              pg.evaluate("document.querySelectorAll('#passkeyStatus').length"))
        check("single #passkeyAddBtn",
              pg.evaluate("document.querySelectorAll('#passkeyAddBtn').length===1"),
              pg.evaluate("document.querySelectorAll('#passkeyAddBtn').length"))
        ctx.close()

        ctx2 = browser.new_context()
        pg2 = ctx2.new_page()
        pg2.add_init_script(NO_PK)
        pg2.goto(URL + "app", wait_until="networkidle")
        pg2.wait_for_timeout(400)
        check("webauthn absent", pg2.evaluate("!window.PublicKeyCredential"))
        check("login button hidden without webauthn",
              pg2.evaluate("getComputedStyle(document.getElementById('passkeyLoginBtn')).display==='none'"))
        check("alt separator hidden without providers",
              pg2.evaluate("getComputedStyle(document.getElementById('authAltSep')).display==='none'"))
        login_user(pg2, URL, "passkey-nopk", "passkey-nopk-pass-9")
        pg2.evaluate("openUserModal()")
        pg2.wait_for_timeout(400)
        check("profile passkey section hidden without webauthn",
              pg2.evaluate("getComputedStyle(document.getElementById('passkeySection')).display==='none'"))
        check("unsupported explanation visible",
              pg2.evaluate("getComputedStyle(document.getElementById('passkeyUnsupported')).display!=='none'"))
        check("unsupported explanation has text",
              pg2.evaluate("document.getElementById('passkeyUnsupported').textContent.trim().length>10"))
        check("still a single #passkeyStatus",
              pg2.evaluate("document.querySelectorAll('#passkeyStatus').length===1"))
        ctx2.close()

        browser.close()

    print()
    if failed:
        print("VERDICT: FAIL", failed)
        sys.exit(1)
    print("VERDICT: ok")


if __name__ == "__main__":
    main()
