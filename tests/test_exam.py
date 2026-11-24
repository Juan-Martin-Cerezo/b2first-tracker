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
    assert pg.eval_on_selector_all("#examSelectGrid .exam-card-mat-btn", "els => els.length") == 0, "Loose Open materials card buttons should be removed"
    assert pg.locator("#v-exam .u4-fullmock-btn").count() == 0, ".u4-fullmock-btn should be removed"
    exam_txt_low = pg.inner_text("#v-exam").lower()
    assert "start full mock" not in exam_txt_low and "empezar simulacro completo" not in exam_txt_low, "Old full mock button text still in #v-exam"
    cards_check = pg.evaluate(
        """() => {
            const grid = document.getElementById('examSelectGrid');
            const gr = grid.getBoundingClientRect();
            const cards = [...grid.querySelectorAll(':scope > .exam-card')];
            const mapped = cards.map((c, idx) => {
                const r = c.getBoundingClientRect();
                return {
                    idx,
                    isFull: c.classList.contains('exam-card-full'),
                    title: (c.querySelector('.exam-card-title')?.textContent || '').trim(),
                    meta: (c.querySelector('.exam-card-min')?.textContent || '').trim(),
                    top: Math.round(r.top),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                };
            });
            const byVisual = [...mapped].sort((a, b) => a.top - b.top);
            return {
                count: cards.length,
                gridW: Math.round(gr.width),
                domLastIsFull: mapped[mapped.length - 1]?.isFull === true,
                visualFirst: byVisual[0],
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
        }"""
    )
    assert cards_check["count"] == 5, cards_check
    assert cards_check["domLastIsFull"], cards_check
    assert cards_check["visualFirst"]["isFull"], cards_check
    assert cards_check["visualFirst"]["title"] == "Full mock", cards_check
    assert cards_check["visualFirst"]["meta"] == "195′ + 14′ Speaking", cards_check
    assert cards_check["visualFirst"]["h"] >= 44, cards_check
    assert abs(cards_check["visualFirst"]["w"] - cards_check["gridW"]) <= 2, cards_check
    assert cards_check["overflow"] <= 1, cards_check
    # Click and Enter on .exam-card-full both open #fullMockPreflight + wizard step 1
    pg.click("#examSelectGrid .exam-card-full")
    pg.wait_for_timeout(200)
    assert pg.evaluate("!document.getElementById('fullMockPreflight').hidden && document.getElementById('mockStartModal').dataset.step === '1'")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    pg.evaluate("closeFullMockPreflight()")
    pg.wait_for_timeout(150)
    pg.focus("#examSelectGrid .exam-card-full")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(200)
    assert pg.evaluate("!document.getElementById('fullMockPreflight').hidden && document.getElementById('mockStartModal').dataset.step === '1'")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    pg.evaluate("closeFullMockPreflight()")
    pg.wait_for_timeout(150)
    # Clicking a paper card opens the guided wizard in step 1 without leaving #v-exam
    pg.click("#examSelectGrid .exam-card[data-paper='rue']")
    pg.wait_for_timeout(200)
    assert pg.evaluate("(document.querySelector('.view.active')||{}).id === 'v-exam' && document.getElementById('mockStartModal').dataset.step === '1'")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
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
