"""Session shift controls now read the week rows instead of schedule inputs."""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
out = {}

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.wait_for_timeout(300)

    orig_week = pg.evaluate("JSON.stringify(D.settings.week || {})")
    orig_offset = pg.evaluate("D.sessionOffset || 0")

    # The week rows are the only place days/times are set.
    pg.evaluate("""() => {
        D.settings.week = {};
        ['mon','tue','thu','sat'].forEach((k, i) => {
            D.settings.week[k] = {mode:'auto', preset:null, parts:{ue:[],l:[],sp:[],w:[]},
                                  min:null, time:['15:30','18:00','19:00','10:00'][i]};
        });
        D.sessionOffset = 0;
        save();
        renderPlan();
        renderToday();
    }""")
    pg.wait_for_timeout(200)
    schedule = pg.evaluate("getSchedule()")
    out["schedule"] = schedule
    assert len(schedule) == 4, schedule
    assert [s["day"] for s in schedule] == [1, 2, 4, 6], schedule

    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(200)
    if not pg.is_visible("#v-plan button[onclick='advanceSession(1)']"):
        pg.click("#planTuning > summary")
        pg.wait_for_timeout(150)
    offset_initial = pg.evaluate("D.sessionOffset || 0")
    pg.click("#v-plan button[onclick='advanceSession(1)']")
    pg.wait_for_timeout(200)
    out["offset_initial"] = offset_initial
    out["offset_after_1"] = pg.evaluate("D.sessionOffset || 0")
    out["offset_badge"] = pg.text_content("#planOffsetBadge")
    assert out["offset_after_1"] == offset_initial + 1, out
    assert "+1" in out["offset_badge"], out

    # The banner on Today keeps the same shift action.
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(200)
    out["today_banner_visible"] = pg.is_visible("#nextBox")
    shift_btn = pg.query_selector("#nextBox button[onclick*='advanceSession']")
    if shift_btn and shift_btn.is_visible():
        shift_btn.click()
        pg.wait_for_timeout(200)
    out["offset_after_banner"] = pg.evaluate("D.sessionOffset || 0")
    assert out["offset_after_banner"] == offset_initial + 2, out

    # Restore.
    pg.evaluate(
        """([week, offset]) => {
        D.settings.week = JSON.parse(week);
        D.sessionOffset = offset;
        save();
        renderPlan();
        renderToday();
    }""",
        [orig_week, orig_offset],
    )
    out["offset_restored"] = pg.evaluate("D.sessionOffset || 0")
    assert out["offset_restored"] == orig_offset, out

    out["errores_js"] = errs
    assert errs == [], errs
    b.close()

print(json.dumps(out, indent=1, ensure_ascii=False))
