import json
from playwright.sync_api import sync_playwright
from helpers import isolated_server, login_owner, login_user, dismiss_onboarding

URL = isolated_server() + "/"
out = {}

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")

    # 1. Login as Owner
    login_owner(pg, URL)
    pg.wait_for_timeout(300)
    out["owner_title"] = pg.text_content("#userTitle")
    out["owner_nav_a"] = pg.text_content("#navLblMonA")
    out["owner_nav_b"] = pg.text_content("#navLblFriA")
    out["owner_st1_time"] = pg.text_content("#st1TimeBadge")
    out["owner_rot_a"] = pg.text_content("#navLblMonA")
    out["owner_rot_b"] = pg.text_content("#navLblFriA")
    out["owner_ses_a_time"] = pg.text_content("#st1TimeBadge")
    out["owner_ses_b_time"] = pg.text_content("#st3TimeBadge")

    # 2. Switch to Maria Fatima (Ses A: Tue 17:00, Ses B: Thu 17:00)
    # A fabricated session no longer boots the app: the token has to exist on
    # the server, so Maria gets a real throwaway account and then her own plan.
    maria_user = login_user(pg, URL, "maria-fatima", "Maria-fatima-2026!")
    maria_data = {
        "log": [], "errs": [], "stage": 0, "onboarded": True,
        "settings": {
            "sesA": {"day": 2, "time": "17:00"},
            "sesB": {"day": 4, "time": "17:00"},
            "ueMin": 50, "planMin": 5, "writeMin": 35, "revMin": 20, "listenMin": 40,
            "sp1Sec": 60, "sp2Sec": 180, "wMin": 140, "wMax": 190, "even": 3, "odd": 4,
            "rueCycle": [1, 2, 3, 4, 5, 6, 7],
            "wCycle": ["Essay", "Article", "Report", "Review", "Email"],
            "lCycle": [1, 2, 3, 4], "spCycle": [1, 2, 3, 4],
            "e0": {"w": 14, "u": 60, "l": 3},
            "e1": {"w": 16, "wm": 45, "u": 75, "l": 24},
            "e2": {"r": 80, "rm": 50, "w": 16, "l": 26, "ln": 4}
        }
    }
    # Boot the app as Maria instead of poking its internals: the Today view now
    # rebuilds its own header, so a manual render left the page half-drawn.
    pg.evaluate("""([u, d]) => {
        localStorage.setItem('b2first_user', JSON.stringify(u));
        localStorage.setItem('b2first_tracker_v1_' + u.id, JSON.stringify(d));
    }""", [maria_user, maria_data])
    pg.reload(wait_until="load")
    pg.wait_for_timeout(900)
    dismiss_onboarding(pg)
    pg.wait_for_timeout(300)

    out["maria_title"] = pg.text_content("#userTitle")
    out["maria_nav_a"] = pg.text_content("#navLblMonA")
    out["maria_nav_b"] = pg.text_content("#navLblFriA")
    out["maria_st1_badge"] = pg.text_content("#st1WkBadge")
    out["maria_st1_time"] = pg.text_content("#st1TimeBadge")
    out["maria_st3_badge"] = pg.text_content("#st3WkBadge")
    out["maria_st3_time"] = pg.text_content("#st3TimeBadge")
    out["maria_rot_a"] = pg.text_content("#navLblMonA")
    out["maria_rot_b"] = pg.text_content("#navLblFriA")
    out["maria_ses_a_time"] = pg.text_content("#st1TimeBadge")
    out["maria_ses_b_time"] = pg.text_content("#st3TimeBadge")

    # 3. Open User Modal (the chip now contains a logout button, so call the
    #    app's own opener instead of clicking the chip's centre)
    pg.evaluate("openUserModal()")
    pg.wait_for_timeout(300)
    out["modal_visible"] = pg.is_visible("#userModal")
    out["modal_user"] = pg.text_content("#modalUserName")
    out["modal_stage"] = pg.text_content("#modalUserStage")
    pg.click("#userModal .del")
    pg.wait_for_timeout(200)
    out["modal_closed"] = not pg.is_visible("#userModal")

    out["errores_js"] = errs
    b.close()

print(json.dumps(out, indent=1, ensure_ascii=False))
