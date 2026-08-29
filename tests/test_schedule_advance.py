import json
from playwright.sync_api import sync_playwright
from helpers import login_owner

URL = "http://127.0.0.1:8088/"
out = {}

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="networkidle")
    login_owner(pg, URL)
    pg.wait_for_timeout(300)

    # 1. Check default schedule rows count
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(200)
    initial_rows = pg.eval_on_selector_all("#scheduleRowsContainer .row", "els => els.length")
    out["initial_schedule_rows"] = initial_rows

    # 2. Add new session days (Total 4 days: Mon, Tue, Thu, Sat)
    pg.evaluate("""() => {
        D.settings.schedule = [
            { day: 1, time: '15:30' },
            { day: 2, time: '18:00' },
            { day: 4, time: '19:00' },
            { day: 6, time: '10:00' }
        ];
        D.sessionOffset = 0;
        save();
        renderPlan();
        renderToday();
    }""")
    pg.wait_for_timeout(200)

    rows_after_add = pg.eval_on_selector_all("#scheduleRowsContainer .row", "els => els.length")
    out["rows_after_add"] = rows_after_add
    out["preview_items_count"] = pg.eval_on_selector_all("#planUpcomingPreview > div", "els => els.length")

    # 3. Check session shift / fast-forward (+1) from Plan view
    offset_initial = pg.evaluate("D.sessionOffset || 0")
    pg.click("#v-plan button[onclick='advanceSession(1)']")
    pg.wait_for_timeout(200)
    offset_after_1 = pg.evaluate("D.sessionOffset || 0")
    badge_text = pg.text_content("#planOffsetBadge")
    out["offset_initial"] = offset_initial
    out["offset_after_1"] = offset_after_1
    out["offset_badge"] = badge_text

    # 4. Check advance via banner on TODAY view
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(200)
    out["today_banner_visible"] = pg.is_visible("#nextBox")
    
    # Click shift (+1) from banner
    shift_btn = pg.query_selector("#nextBox button[onclick*='advanceSession']")
    if shift_btn and shift_btn.is_visible():
        shift_btn.click()
        pg.wait_for_timeout(200)
    offset_after_banner = pg.evaluate("D.sessionOffset || 0")
    out["offset_after_banner"] = offset_after_banner

    # 5. Reset offset
    pg.evaluate("resetSessionOffset();")
    out["offset_after_reset"] = pg.evaluate("D.sessionOffset || 0")

    out["errores_js"] = errs
    b.close()

print(json.dumps(out, indent=1, ensure_ascii=False))
