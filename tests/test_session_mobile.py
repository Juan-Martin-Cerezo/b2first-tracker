"""Phase session-mobile acceptance: 3-step session coach and mobile usability.

Verifies:
  1. Opening a RUE session from Practice Start at 390x844 shows #sessionCoach
     with 3 numbered steps (ES: "Abrí el ejercicio en Contents", "Iniciá el tiempo",
     "Phase 2"; EN symmetric).
  2. Step 1 opens Contents tab, and returning to Session marks Step 1 done (✓).
  3. Step 2 starts #ueTimer (changes within 2s), button toggles to Pause/Pausar,
     and the live mm:ss value appears in the coach.
  4. Step 3 switches to Phase 2 (#uePhase2 visible), save button is visible and
     >= 48px tall / full-width; saving marks Step 3 done (✓).
  5. #sessionBar stays sticky below the app topbar after window.scrollTo(0, 900);
     tabs are 50/50 full-width and >= 48px tall.
  6. At 390x844: scrollWidth <= clientWidth, all visible inputs and buttons in
     #sessionWorkspace are >= 44px tall, timer >= 20px, .row inputs 1-col full-width,
     2-col phase-stepper for RUE/L and 1-col for Writing, zero overlap of #qlFab
     with coach, timer, or save button.
  7. Same 1-4 flow for Listening and Writing (skill-specific copy & actions).
  8. At 1280x800: coach renders in 3 columns, tabs and timer intact, zero overflow.
  9. Symmetric EN/ES copy, zero inline handlers, zero console/page errors.

Saves screenshots in tests/out/:
  session_coach_390_light.png, session_coach_390_dark.png,
  session_phase2_390_light.png, session_coach_1280_light.png.
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
INLINE_HANDLER_RE = re.compile(r'\bon[a-z]+\s*=\s*"')


def seed_mat_if_empty(pg):
    pg.evaluate("loadMaterial()")
    pg.wait_for_timeout(300)
    if pg.evaluate("Object.keys(MAT).length") == 0:
        pg.evaluate(
            """() => {
                const keys = [
                    'rueS1','rueS2','keyS1','keyS2','lpR1','lpR2','fR2',
                    'wS1','wS2','lpW1','lpW2','lS1','lkS1','auS1','tsS1','lpL1','lpL2',
                    'spS1','exC0','lpSp2','hb'
                ];
                keys.forEach(k => { MAT[k] = '/files/test-' + k + '.pdf'; });
                renderParts(); renderGuides(); renderExercisesLibrary();
            }"""
        )


def open_practice_part(pg, skill_type, part_num):
    """Open Practice -> By part -> click Start for the matching PARTS entry."""
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(200)
    pg.evaluate(
        """() => {
            const det = document.getElementById('practicePartsDetails');
            if (det && !det.open) det.open = true;
        }"""
    )
    pg.wait_for_timeout(150)
    idx = pg.evaluate(
        """([tp, num]) => PARTS.findIndex(p => p.type === tp && Number(p.n) === Number(num))""",
        [skill_type, part_num],
    )
    assert idx >= 0, f"PARTS entry not found for type={skill_type} n={part_num}"
    pg.click(f"#partsList .step button[data-action='startPart'][data-i='{idx}']")
    pg.wait_for_timeout(250)


def check_mobile_geometry(pg, label):
    """Verify zero overflow, >=44px targets, sticky bar, and zero FAB overlap at 390x844."""
    geo = pg.evaluate(
        """() => {
            const vw = window.innerWidth;
            const sw = document.documentElement.scrollWidth;
            const cw = document.documentElement.clientWidth;
            const ws = document.getElementById('sessionWorkspace');
            const bar = document.getElementById('sessionBar');
            const fab = document.getElementById('qlFab');
            const tabs = [...document.querySelectorAll('#sessionTabs .practice-tab')].map(b => {
                const r = b.getBoundingClientRect();
                return {text: b.textContent.trim(), w: Math.round(r.width), h: Math.round(r.height)};
            });
            const controls = [...ws.querySelectorAll('button, input, select, textarea')].filter(el => {
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }).map(el => {
                const r = el.getBoundingClientRect();
                return {
                    id: el.id || el.dataset.action || el.tagName.toLowerCase(),
                    tag: el.tagName.toLowerCase(),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    right: Math.round(r.right),
                };
            });
            const smallControls = controls.filter(c => c.h < 44);
            const overflowControls = controls.filter(c => c.right > vw + 1);
            const box = el => {
                if (!el) return null;
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return null;
                const r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) return null;
                return {top: r.top, bottom: r.bottom, left: r.left, right: r.right, w: r.width, h: r.height};
            };
            return {
                vw, sw, cw,
                tabs,
                barSticky: bar ? getComputedStyle(bar).position : '',
                smallControls,
                overflowControls,
                fabBox: box(fab),
                coachBox: box(document.getElementById('sessionCoach')),
            };
        }"""
    )
    assert geo["sw"] <= geo["cw"], f"{label}: horizontal overflow {geo['sw']} > {geo['cw']}"
    assert geo["overflowControls"] == [], f"{label}: controls overflow viewport: {geo['overflowControls']}"
    assert geo["smallControls"] == [], f"{label}: controls < 44px height: {geo['smallControls']}"
    assert len(geo["tabs"]) == 2, f"{label}: expected 2 tabs, got {geo['tabs']}"
    for tab in geo["tabs"]:
        assert tab["h"] >= 48, f"{label}: session tab < 48px: {tab}"
    assert abs(geo["tabs"][0]["w"] - geo["tabs"][1]["w"]) <= 2, f"{label}: tabs not 50/50: {geo['tabs']}"
    assert geo["barSticky"] == "sticky", f"{label}: #sessionBar not sticky: {geo['barSticky']}"
    assert geo["fabBox"] is None, f"{label}: #qlFab should be hidden in session focus, got {geo['fabBox']}"
    return geo


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    console_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.on(
        "console",
        lambda m: console_errors.append(m.text)
        if m.type == "error" and "Failed to load resource" not in m.text
        else None,
    )

    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(300)
    seed_mat_if_empty(pg)

    # 1. Open RUE session from Practice Start at 390x844, switch to Session tab.
    open_practice_part(pg, "ue", 2)
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(200)

    coach_rue = pg.evaluate(
        """() => {
            const c = document.getElementById('sessionCoach');
            const steps = [...c.querySelectorAll('.session-coach-step')].map(s => ({
                step: s.dataset.coachStep,
                text: s.innerText.trim(),
                done: s.classList.contains('is-done'),
                active: s.classList.contains('is-active'),
                fontSize: parseFloat(getComputedStyle(s.querySelector('.session-coach-title')).fontSize),
                btnH: Math.round(s.querySelector('.session-coach-btn').getBoundingClientRect().height),
                btnW: Math.round(s.querySelector('.session-coach-btn').getBoundingClientRect().width),
            }));
            const timerEl = document.getElementById('ueTimer');
            const timerBtn = document.querySelector('#uePhase1 [data-action="ueTimer.start"]');
            const stepperCols = [...document.querySelectorAll('#uePhaseStepper .phase-step')].map(s => ({
                top: Math.round(s.getBoundingClientRect().top),
                h: Math.round(s.getBoundingClientRect().height),
            }));
            return {
                visible: !c.hidden && getComputedStyle(c).display !== 'none',
                steps,
                timerFont: timerEl ? parseFloat(getComputedStyle(timerEl).fontSize) : 0,
                timerBtnW: timerBtn ? Math.round(timerBtn.getBoundingClientRect().width) : 0,
                timerBtnH: timerBtn ? Math.round(timerBtn.getBoundingClientRect().height) : 0,
                stepperCols,
                wsHtml: document.getElementById('sessionWorkspace').outerHTML,
            };
        }"""
    )
    assert coach_rue["visible"], "#sessionCoach is not visible"
    assert len(coach_rue["steps"]) == 3, f"Expected 3 coach steps: {coach_rue['steps']}"
    assert "Abrí el ejercicio en Contents" in coach_rue["steps"][0]["text"], coach_rue["steps"][0]
    assert "Iniciá el tiempo" in coach_rue["steps"][1]["text"], coach_rue["steps"][1]
    assert "Phase 2" in coach_rue["steps"][2]["text"], coach_rue["steps"][2]
    assert "Cargá correctas, total y minutos, y guardá." in coach_rue["steps"][2]["text"], coach_rue["steps"][2]
    assert coach_rue["steps"][0]["active"] and not coach_rue["steps"][0]["done"]
    for st in coach_rue["steps"]:
        assert st["fontSize"] >= 14, f"Coach font size < 14px: {st}"
        assert st["btnH"] >= 44, f"Coach button height < 44px: {st}"
        assert st["btnW"] >= 280, f"Coach button not full-width on 390: {st}"
    assert coach_rue["timerFont"] >= 20, f"Timer font < 20px: {coach_rue['timerFont']}"
    assert coach_rue["timerBtnW"] >= 44 and coach_rue["timerBtnH"] >= 44, coach_rue
    assert coach_rue["stepperCols"][0]["top"] == coach_rue["stepperCols"][1]["top"], (
        f"RUE 2-phase stepper should be 2 equal columns on mobile: {coach_rue['stepperCols']}"
    )
    assert not INLINE_HANDLER_RE.search(coach_rue["wsHtml"]), "Inline handler in #sessionWorkspace"

    check_mobile_geometry(pg, "RUE Phase 1 ES")

    # Screenshot 1: session_coach_390_light.png
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light'); window.scrollTo(0, 0)")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "session_coach_390_light.png"))

    # Screenshot 2: session_coach_390_dark.png
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); window.scrollTo(0, 0)")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), "Dark 390 overflow"
    pg.screenshot(path=os.path.join(OUT, "session_coach_390_dark.png"))
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(100)

    # 2. Step 1 opens Contents, returning marks Step 1 done (✓).
    pg.click("#sessionCoachBtn1")
    pg.wait_for_timeout(200)
    assert pg.evaluate("!document.getElementById('sessionTabContents').hidden"), "Step 1 did not open Contents"
    assert pg.evaluate("document.getElementById('sessionTabContentsBtn').classList.contains('active')")
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(150)
    s1_after = pg.evaluate(
        """() => ({
            done: document.getElementById('sessionCoachStep1').classList.contains('is-done'),
            num: document.getElementById('sessionCoachNum1').textContent.trim(),
            desc: document.getElementById('sessionCoachDesc1').textContent.trim(),
            s2Active: document.getElementById('sessionCoachStep2').classList.contains('is-active'),
        })"""
    )
    assert s1_after["done"] and s1_after["num"] == "✓", f"Step 1 not marked done: {s1_after}"
    assert "Ejercicio abierto" in s1_after["desc"], f"Step 1 done copy missing: {s1_after}"
    assert s1_after["s2Active"], "Step 2 did not become active after Step 1"

    # 3. Step 2 starts #ueTimer (changes in 2s), button passes to Pausar, live value shown in coach.
    t_before = pg.inner_text("#ueTimer").strip()
    pg.click("#sessionCoachBtn2")
    pg.wait_for_timeout(2200)
    t_after = pg.inner_text("#ueTimer").strip()
    assert t_after != t_before, f"#ueTimer did not tick in 2s: {t_before} -> {t_after}"
    s2_state = pg.evaluate(
        """() => ({
            done: document.getElementById('sessionCoachStep2').classList.contains('is-done'),
            btn: document.getElementById('sessionCoachBtn2').textContent.trim(),
            coachTimer: document.getElementById('sessionCoachTimer').textContent.trim(),
            ueTimer: document.getElementById('ueTimer').textContent.trim(),
        })"""
    )
    assert s2_state["done"], f"Step 2 not marked done: {s2_state}"
    assert s2_state["btn"] == "Pausar", f"Step 2 button did not change to Pausar: {s2_state}"
    assert s2_state["coachTimer"] == s2_state["ueTimer"], f"Coach timer != #ueTimer: {s2_state}"

    # 5. #sessionBar sticky after scrollTo(0, 900)
    pg.evaluate("window.scrollTo(0, 900)")
    pg.wait_for_timeout(200)
    bar_rect = pg.evaluate(
        """() => {
            const r = document.getElementById('sessionBar').getBoundingClientRect();
            return {top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height)};
        }"""
    )
    assert 0 <= bar_rect["top"] < 120 and bar_rect["bottom"] <= 844, f"#sessionBar not sticky in viewport: {bar_rect}"
    pg.evaluate("window.scrollTo(0, 0)")
    pg.wait_for_timeout(150)

    # 4. Step 3 goes to Phase 2 (#uePhase2 visible), save button visible & >= 48px, saving marks Step 3 done.
    pg.click("#sessionCoachBtn3")
    pg.wait_for_timeout(250)
    p2_state = pg.evaluate(
        """() => {
            const p2 = document.getElementById('uePhase2');
            const saveBtn = p2.querySelector('button[data-action="saveUE"]');
            const r = saveBtn.getBoundingClientRect();
            const inputs = [...p2.querySelectorAll('input, select')].map(el => ({
                id: el.id,
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height),
                left: Math.round(el.getBoundingClientRect().left),
            }));
            return {
                p2Visible: getComputedStyle(p2).display !== 'none',
                saveH: Math.round(r.height),
                saveW: Math.round(r.width),
                saveBottom: Math.round(r.bottom),
                inputs,
            };
        }"""
    )
    assert p2_state["p2Visible"], "#uePhase2 did not become visible"
    assert p2_state["saveH"] >= 48 and p2_state["saveW"] >= 280, f"saveUE button geometry: {p2_state}"
    assert p2_state["saveBottom"] <= 844, f"saveUE button not in viewport: {p2_state}"
    for inp in p2_state["inputs"]:
        assert inp["h"] >= 44 and inp["w"] >= 280, f"Phase 2 input not 1-col full-width >=44px: {inp}"
    check_mobile_geometry(pg, "RUE Phase 2 ES")

    # Screenshot 3: session_phase2_390_light.png (show sticky #sessionBar + #uePhase2 inputs + save button)
    pg.evaluate("if (document.activeElement) document.activeElement.blur();")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "session_phase2_390_light.png"))

    # Save RUE -> Step 3 marked done
    pg.fill("#ueOk", "6")
    pg.click("#uePhase2 button[data-action='saveUE']")
    pg.wait_for_timeout(250)
    assert pg.evaluate("document.getElementById('sessionCoachStep3').classList.contains('is-done')"), "Step 3 not marked done after saveUE"
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)
    out["rue_390"] = {"t_before": t_before, "t_after": t_after, "bar_top_scrolled": bar_rect["top"], "p2_save_h": p2_state["saveH"]}

    # 7a. Listening (1-4 flow)
    open_practice_part(pg, "lp", 1)
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(200)
    l_desc3 = pg.inner_text("#sessionCoachDesc3").strip()
    assert "post-mortem" in l_desc3.lower() and "guardá" in l_desc3.lower(), f"Listening coach copy wrong: {l_desc3!r}"
    pg.click("#sessionCoachBtn1")
    pg.wait_for_timeout(150)
    assert pg.evaluate("!document.getElementById('sessionTabContents').hidden")
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('sessionCoachStep1').classList.contains('is-done')")
    lt_before = pg.inner_text("#lTimer").strip()
    pg.click("#sessionCoachBtn2")
    pg.wait_for_timeout(2200)
    lt_after = pg.inner_text("#lTimer").strip()
    assert lt_after != lt_before, f"#lTimer did not tick: {lt_before} -> {lt_after}"
    assert pg.inner_text("#sessionCoachBtn2").strip() == "Pausar"
    assert pg.inner_text("#sessionCoachTimer").strip() == lt_after
    pg.click("#sessionCoachBtn3")
    pg.wait_for_timeout(200)
    l_p2 = pg.evaluate(
        """() => {
            const p2 = document.getElementById('lPhase2');
            const ok = document.getElementById('lOk');
            const btn = p2.querySelector('button[data-action="saveL"]');
            return {
                p2Visible: getComputedStyle(p2).display !== 'none',
                okVisible: ok && getComputedStyle(ok).display !== 'none' && ok.getBoundingClientRect().height >= 44,
                btnH: btn ? Math.round(btn.getBoundingClientRect().height) : 0,
            };
        }"""
    )
    assert l_p2["p2Visible"] and l_p2["okVisible"] and l_p2["btnH"] >= 48, f"Listening Phase 2 issue: {l_p2}"
    check_mobile_geometry(pg, "Listening Phase 2 ES")
    pg.fill("#lOk", "6")
    pg.click("#lPhase2 button[data-action='saveL']")
    pg.wait_for_timeout(200)
    assert pg.evaluate("document.getElementById('sessionCoachStep3').classList.contains('is-done')")
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)
    out["listening_390"] = {"t_before": lt_before, "t_after": lt_after, "p2": l_p2}

    # 7b. Writing (1-4 flow)
    open_practice_part(pg, "w", 1)
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(200)
    w_desc3 = pg.inner_text("#sessionCoachDesc3").strip()
    assert "Check with AI (Phase 3)" in w_desc3, f"Writing coach copy wrong: {w_desc3!r}"
    w_stepper_cols = pg.eval_on_selector_all(
        "#wPhaseStepper .phase-step", "els => els.map(e => Math.round(e.getBoundingClientRect().top))"
    )
    assert len(set(w_stepper_cols)) == 3, f"Writing 3-phase stepper should stack to 1 col on 390: {w_stepper_cols}"
    pg.click("#sessionCoachBtn1")
    pg.wait_for_timeout(150)
    assert pg.evaluate("!document.getElementById('sessionTabContents').hidden")
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('sessionCoachStep1').classList.contains('is-done')")
    wt_before = pg.inner_text("#wPlanTimer").strip()
    pg.click("#sessionCoachBtn2")
    pg.wait_for_timeout(2200)
    wt_after = pg.inner_text("#wPlanTimer").strip()
    assert wt_after != wt_before, f"#wPlanTimer did not tick: {wt_before} -> {wt_after}"
    assert pg.inner_text("#sessionCoachBtn2").strip() == "Pausar"
    assert pg.inner_text("#sessionCoachTimer").strip() == wt_after
    pg.click("#sessionCoachBtn3")
    pg.wait_for_timeout(200)
    w_p3 = pg.evaluate(
        """() => {
            const p3 = document.getElementById('wPhase3');
            const cta = p3.querySelector('.w-phase3-cta');
            const btn = document.getElementById('rubAiBtn');
            return {
                p3Visible: getComputedStyle(p3).display !== 'none',
                btnH: btn ? Math.round(btn.getBoundingClientRect().height) : 0,
                btnW: btn ? Math.round(btn.getBoundingClientRect().width) : 0,
                ctaW: cta ? Math.round(cta.getBoundingClientRect().width) : 0,
            };
        }"""
    )
    assert w_p3["p3Visible"] and w_p3["btnH"] >= 48 and abs(w_p3["btnW"] - w_p3["ctaW"]) <= 2, f"Writing Phase 3 issue: {w_p3}"
    check_mobile_geometry(pg, "Writing Phase 3 ES")

    # 9. Symmetric EN/ES copy check on open session
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(250)
    en_coach = pg.evaluate(
        """() => ({
            s1: document.getElementById('sessionCoachTitle1').textContent.trim(),
            s2: document.getElementById('sessionCoachTitle2').textContent.trim(),
            s3: document.getElementById('sessionCoachTitle3').textContent.trim(),
            d3: document.getElementById('sessionCoachDesc3').textContent.trim(),
            b1: document.getElementById('sessionCoachBtn1').textContent.trim(),
            b3: document.getElementById('sessionCoachBtn3').textContent.trim(),
            tabs: [...document.querySelectorAll('#sessionTabs .practice-tab')].map(b => b.textContent.trim()),
        })"""
    )
    assert "Open the exercise in Contents" in en_coach["s1"], en_coach
    assert "Start the timer" in en_coach["s2"], en_coach
    assert "Review your text with Check with AI (Phase 3)." == en_coach["d3"], en_coach
    assert en_coach["tabs"] == ["Session", "Contents"], en_coach
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)

    # 8. Desktop 1280x800: coach in 3 columns, tabs & timer intact, zero overflow.
    pg.set_viewport_size({"width": 1280, "height": 800})
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)
    open_practice_part(pg, "ue", 2)
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(200)
    desk = pg.evaluate(
        """() => {
            const steps = [...document.querySelectorAll('#sessionCoach .session-coach-step')].map(s => {
                const r = s.getBoundingClientRect();
                return {top: Math.round(r.top), left: Math.round(r.left), w: Math.round(r.width), h: Math.round(r.height)};
            });
            const timer = document.getElementById('ueTimer').getBoundingClientRect();
            const tabs = [...document.querySelectorAll('#sessionTabs .practice-tab')].map(b => Math.round(b.getBoundingClientRect().height));
            return {
                steps,
                timerH: Math.round(timer.height),
                tabs,
                sw: document.documentElement.scrollWidth,
                cw: document.documentElement.clientWidth,
            };
        }"""
    )
    assert desk["sw"] <= desk["cw"], f"Desktop 1280 overflow: {desk['sw']} > {desk['cw']}"
    assert len(desk["steps"]) == 3
    assert len({s["top"] for s in desk["steps"]}) == 1, f"Desktop coach not 3 columns on one row: {desk['steps']}"
    assert desk["steps"][0]["left"] < desk["steps"][1]["left"] < desk["steps"][2]["left"], desk["steps"]
    assert desk["timerH"] > 0 and all(h >= 44 for h in desk["tabs"]), desk
    pg.evaluate("if(document.activeElement)document.activeElement.blur(); window.scrollTo(0, 0)")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "session_coach_1280_light.png"))
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(150)

    # Verify coach does not appear in Practice or Exam
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('sessionCoach').hidden"), "Coach visible in Practice"
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(150)
    assert pg.evaluate("document.getElementById('sessionCoach').hidden"), "Coach visible in Exam"

    assert page_errors == [], f"Page errors: {page_errors}"
    assert console_errors == [], f"Console errors: {console_errors}"
    out["writing_390"] = {"t_before": wt_before, "t_after": wt_after, "p3": w_p3}
    out["desktop_1280"] = desk
    out["en_coach"] = en_coach
    out["errors"] = {"page": page_errors, "console": console_errors}
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
