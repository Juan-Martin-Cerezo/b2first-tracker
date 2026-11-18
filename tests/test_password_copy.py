"""B4: the password UI must promise the same minimum the server enforces.

10-character mixed passwords are no longer scored as valid; 12 are. The visible
copy in registration and in Change Password says 12+, in English and Spanish.

    cd tests && uv run --with playwright python test_password_copy.py
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
        pg.wait_for_timeout(300)

        check("10 chars mixed is not scored", pg.evaluate("passwordStrength('Abcdef1234')") == 0,
              pg.evaluate("passwordStrength('Abcdef1234')"))
        check("12 chars mixed is scored", pg.evaluate("passwordStrength('Abcdef123456')") >= 1,
              pg.evaluate("passwordStrength('Abcdef123456')"))

        pg.evaluate("switchAuthTab('register')")
        pg.fill("#regPass", "Abcdef1234")
        hint = pg.inner_text("#regPwHint")
        check("10-char hint is not 'Fair'", "Fair" not in hint, hint)
        pg.fill("#regPass", "Abcdef123456")
        hint12 = pg.inner_text("#regPwHint")
        check("12-char hint is scored", "Fair" in hint12 or "Strong" in hint12, hint12)

        pg.fill("#regPass", "")
        label = pg.inner_text("label[data-i18n='auth_password_min']")
        check("registration label says 12+", "12" in label, label)
        check("registration hint says 12+", "12" in pg.inner_text("#regPwHint"), pg.inner_text("#regPwHint"))
        check("change-password placeholder says 12+",
              "12" in pg.get_attribute("#pwNew", "placeholder"), pg.get_attribute("#pwNew", "placeholder"))

        login_user(pg, URL, "password-copy", "password-copy-pass-9")

        # Spanish copy (after login, so save() has a real session)
        pg.evaluate("setLang('es')")
        pg.wait_for_timeout(200)
        es_hint = pg.evaluate("document.getElementById('regPwHint').textContent")
        check("ES registration hint says 12+", "12" in es_hint, es_hint)
        check("ES change-password placeholder says 12+",
              "12" in pg.get_attribute("#pwNew", "placeholder"), pg.get_attribute("#pwNew", "placeholder"))
        pg.evaluate("setLang('en')")
        pg.evaluate("openUserModal()")
        pg.wait_for_timeout(250)
        check("visible user modal copy has no 10+",
              "10+" not in pg.inner_text("#userModal"), "10+ found")
        check("visible user modal placeholder says 12+",
              "12" in pg.get_attribute("#pwNew", "placeholder"))
        browser.close()

    print()
    if failed:
        print("VERDICT: FAIL", failed)
        sys.exit(1)
    print("VERDICT: ok")


if __name__ == "__main__":
    main()
