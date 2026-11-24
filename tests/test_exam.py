import json
from playwright.sync_api import sync_playwright
from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    out["scroll_ok"] = pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")

    # EXAMEN tab
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(300)
    out["ex_timer"] = pg.evaluate("document.getElementById('exTimer').textContent")
    out["ex_guide_len"] = pg.evaluate("document.getElementById('exGuide').innerText.length")
    out["ex_links"] = pg.eval_on_selector_all("#exGuide a", "els => els.length")
    out["ex_chips"] = pg.eval_on_selector_all("#exGuide .chip", "els => els.length")
    assert out["ex_links"] == 0, f"#exGuide should have 0 loose links, got {out['ex_links']}"
    assert out["ex_chips"] == 0, f"#exGuide should have 0 chips, got {out['ex_chips']}"
    assert "open the exam papers" not in pg.inner_text("#exGuide").lower()
    assert pg.eval_on_selector_all("#exGuide button", "els => els.length") == 0, "#exGuide should have pace text only, no Open materials button"
    assert pg.evaluate("document.getElementById('exActiveLibBtn')") is None, "#exActiveLibBtn should be removed"
    assert pg.evaluate("document.getElementById('examLibraryLink')") is None, "#examLibraryLink should be removed"
    # Card's Open materials button opens Library filtered to that paper and scope='full'
    pg.click("#examSelectGrid .exam-card[data-paper='rue'] .exam-card-mat-btn")
    pg.wait_for_timeout(200)
    lib_from_card = pg.evaluate(
        """() => ({
            view: (document.querySelector('.view.active') || {}).id || '',
            paper: EXLIB_PRACTICE_STATE.paper,
            scope: EXLIB_PRACTICE_STATE.scope,
        })"""
    )
    assert lib_from_card == {"view": "v-practice", "paper": "rue", "scope": "full"}, lib_from_card
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(200)
    # cambiar a Writing via hidden #exPaper contract
    pg.evaluate("document.getElementById('exPaper').value='w'; renderEx()")
    pg.wait_for_timeout(200)
    out["ex_w_timer"] = pg.evaluate("document.getElementById('exTimer').textContent")
    out["ex_w_links"] = pg.eval_on_selector_all("#exGuide a", "els => els.length")
    assert out["ex_w_links"] == 0, f"#exGuide for Writing should have 0 loose links: {out['ex_w_links']}"
    assert pg.eval_on_selector_all("#exGuide button", "els => els.length") == 0, "#exGuide for Writing should have 0 buttons"
    # start timer and verify the countdown
    pg.click("button[data-action='exStart']")
    pg.wait_for_timeout(2100)
    out["ex_corriendo"] = pg.evaluate("exIv !== null")
    out["ex_timer_tras2s"] = pg.evaluate("document.getElementById('exTimer').textContent")
    pg.evaluate("document.querySelector(\"button[data-action='exPause']\").click()")
    out["ex_pausado"] = pg.evaluate("exIv === null")
    pg.evaluate("exLeft = 590; exTick()")  # simular <10min -> rojo
    out["ex_color_warn"] = pg.evaluate("document.getElementById('exTimer').style.color")

    # PRACTICE: the 15-part catalogue (plus Writing) now lives here
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(300)
    out["partes_total"] = pg.eval_on_selector_all("#partsList .step", "els => els.length")
    out["partes_grupos"] = pg.eval_on_selector_all("#partsList .folder", "els => els.length")
    # registrar un part UoE P5
    pg.evaluate("""window.__origExamLog = JSON.stringify(D.log);
                   savePart(4);""")  # index 4 = R&UoE Part 5
    out["log_ue_p5"] = pg.evaluate("D.log.some(e => e.type==='ue' && e.part===5)")
    out["log_modo"] = pg.evaluate("(D.log.find(e => e.type==='ue' && e.part===5)||{}).note")
    # restore test data
    pg.evaluate("D.log = JSON.parse(window.__origExamLog); save(); refreshAll();")

    out["errores_js"] = errs
    b.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
