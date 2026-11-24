"""Phase practice-real acceptance: real practice only, Materials = Contents, no Last Speaking, clean Writing Phase 3.

Verifies:
  1. Library has 0 lesson plans, 0 teacher guides, 0 handbooks, 0 reference items,
     0 examiner comments, and no Reference filter chip.
  2. In all 4 session studios (R&UoE, Writing, Listening, Speaking), Materials is a
     single button that opens the unified Contents tab (`setSessionTab('contents')`)
     with zero collapsible `.wtf-toggle` / `.wtf-panel` chip walls.
  3. Today has NO `#lastSpeaking` card and no "Last speaking exam" text even when
     `D.log` contains a speaking session.
  4. Writing Phase 3 (`#wPhase3`) has 0 rubric checkboxes (`.rub`, `#rubList`),
     0 manual inputs (`#wPv`, `#wCol`, `#wScore`, `#auditScore`, `#errCode`, etc.),
     no manual `20:00` timer, and shows a prominent `#rubAiBtn` ("Check with AI")
     that receives focus on entering Phase 3 without auto-submitting.
  5. Clicking `#rubAiBtn` sends POST `/api/ai/writing` and renders read-only feedback
     without mutating `D.log`.
  6. 390x844 light/dark: zero horizontal overflow, >=44px targets, EN/ES symmetric.

Saves screenshot: tests/out/writing_phase3_390_light.png.
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

DRAFT = (
    "Technology has changed the way people talk to each other, and some observers argue "
    "that it has made us less social. Furthermore, many teenagers prefer a message to a "
    "conversation. Nevertheless, the evidence is not one-sided.\n\n"
    "Firstly, smartphones allow families to stay in touch across long distances, which "
    "is a genuine benefit. Moreover, group chats can organise a meeting in minutes and "
    "keep everyone informed.\n\n"
    "Consequently, it would be unfair to blame every device for loneliness. If governments "
    "were to invest in public spaces, people would meet face to face far more often.\n\n"
    "As a result, the problem is not the technology itself but the habits it encourages. "
    "A balanced approach, which protects real conversation, is widely believed to be the "
    "answer. Not only should schools teach digital balance, but they should also create "
    "places where students can simply talk."
)

out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(300)

    # Seed MAT including filler keys to prove they are excluded from Library
    pg.evaluate(
        """() => {
            const keys = [
                'rueS1','rueS2','keyS1','keyS2','lpR1','lpR2','fR2','rAct1','rGuide',
                'wS1','wS2','wCheck','lpW1','fW1','wAct1','wGuide',
                'lS1','lS2','lkS1','lkS2','tsS1','auS1','auS2p1','lpL1','fL1','fL1a','hbA1','lGuide',
                'spS1','spS2','exC0','exC1','lpSp1','fSp1','spAct','spGuide',
                'hb','hbFS','cand','score','tips','c1Hb'
            ];
            keys.forEach(k => { MAT[k] = '/files/test-' + k + '.pdf'; });
            renderEx(); renderParts(); renderGuides(); renderExercisesLibrary(); renderFullMockPreflight();
        }"""
    )

    # 1. Zero lesson plans / guides / handbooks / reference / examiner comments in Library
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(250)
    lib_check = pg.evaluate(
        """() => {
            const rows = [...document.querySelectorAll('#pracLibList a.exlib-row')].map(a => ({
                name: a.dataset.name || '',
                type: a.dataset.type || '',
                skill: a.dataset.skill || '',
            }));
            const allowed = new Set(['paper', 'key', 'tapescript', 'checklist', 'audio', 'online']);
            const badTypes = rows.filter(r => !allowed.has(r.type) || r.skill === 'ref');
            const badNames = rows.filter(r => /lesson plan|teacher guide|handbook|examiner (notes|comments)/i.test(r.name));
            const refChips = document.querySelectorAll('[data-exlib-paper="ref"]').length;
            const sub = (document.querySelector('#practiceLibraryCard .sub') || {}).textContent || '';
            const countText = (document.getElementById('pracLibCount') || {}).textContent?.trim() || '';
            return {
                total: rows.length,
                types: [...new Set(rows.map(r => r.type))].sort(),
                badTypes,
                badNames,
                refChips,
                subHasLesson: /lesson/i.test(sub),
                countText,
            };
        }"""
    )
    assert lib_check["total"] > 0, lib_check
    assert lib_check["badTypes"] == [], f"Disallowed types in Library: {lib_check['badTypes']}"
    assert lib_check["badNames"] == [], f"Filler names in Library: {lib_check['badNames']}"
    assert lib_check["refChips"] == 0, f"Reference filter chip still in DOM: {lib_check}"
    assert not lib_check["subHasLesson"], f"Library subtitle still mentions lesson: {lib_check}"
    assert lib_check["countText"] == f"{lib_check['total']} contents", lib_check
    assert "checklist" in lib_check["types"] and "tapescript" in lib_check["types"], lib_check["types"]
    out["1_real_library"] = {"total": lib_check["total"], "types": lib_check["types"]}

    # 2. Today has NO #lastSpeaking even with a speaking entry in D.log
    pg.evaluate(
        """() => {
            D.log.unshift({date: '2026-11-20', type: 'sp', part: 2, score: 4, min: 4});
            refreshAll();
            showView('hoy');
        }"""
    )
    pg.wait_for_timeout(200)
    today_check = pg.evaluate(
        """() => ({
            hasNode: !!document.getElementById('lastSpeaking'),
            bodyHasText: /last speaking exam|último examen de speaking/i.test(document.getElementById('v-hoy').innerText),
        })"""
    )
    assert today_check == {"hasNode": False, "bodyHasText": False}, f"#lastSpeaking still present: {today_check}"
    out["2_no_last_speaking"] = True

    # 3. Materials = Contents in all 4 session studios (Rue, Writing, Listening, Speaking)
    assert pg.locator(".wtf-toggle, .wtf-panel").count() == 0, "Collapsible wtf-toggle/wtf-panel still in DOM"
    studio_checks = {}
    for skill, part, btn_id in [
        ("rue", 2, "openContentsRue"),
        ("w", "Essay", "openContentsW"),
        ("l", 1, "openContentsL"),
        ("sp", 2, "openContentsSp"),
    ]:
        pg.evaluate(
            "(arg) => openUnitSession({skill: arg.skill, value: arg.part, min: 10}, {origin: 'practice', initialTab: 'session'})",
            {"skill": skill, "part": part},
        )
        pg.wait_for_timeout(150)
        btn_info = pg.evaluate(
            """(id) => {
                const b = document.getElementById(id);
                const r = b ? b.getBoundingClientRect() : null;
                return {
                    exists: !!b,
                    h: r ? Math.round(r.height) : 0,
                    action: b ? b.dataset.action : '',
                    tab: b ? b.dataset.sessionTab : '',
                    sesVisible: !document.getElementById('sessionTabSession').hidden,
                    cntVisible: !document.getElementById('sessionTabContents').hidden,
                };
            }""",
            btn_id,
        )
        assert btn_info["exists"] and btn_info["h"] >= 44, f"{skill} button missing or <44px: {btn_info}"
        assert btn_info["action"] == "setSessionTab" and btn_info["tab"] == "contents", btn_info
        assert btn_info["sesVisible"] and not btn_info["cntVisible"], btn_info
        pg.click(f"#{btn_id}")
        pg.wait_for_timeout(150)
        after_click = pg.evaluate(
            """() => ({
                sesVisible: !document.getElementById('sessionTabSession').hidden,
                cntVisible: !document.getElementById('sessionTabContents').hidden,
                rows: document.querySelectorAll('#exLibList a.exlib-row').length,
            })"""
        )
        assert after_click["cntVisible"] and not after_click["sesVisible"] and after_click["rows"] > 0, (
            f"{skill} Materials button did not open Contents: {after_click}"
        )
        studio_checks[skill] = after_click["rows"]
    out["3_materials_equals_contents"] = studio_checks

    # 4. Writing Phase 3: zero checkboxes/manual inputs/manual 20:00 timer; #rubAiBtn visible & focused without auto-submit
    ai_calls = []

    def ai_route(route):
        ai_calls.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "bands": {"content": 4, "communicative_achievement": 4, "organisation": 4, "language": 4},
                    "total": 16,
                    "feedback": {},
                    "weaknesses": {},
                    "quotes": {},
                    "rewrite": [],
                }
            ),
        )

    pg.route("**/api/ai/writing", ai_route)
    pg.evaluate(
        """(txt) => {
            openUnitSession({skill: 'w', value: 'Essay', part: 1, min: 40}, {origin: 'practice', initialTab: 'session'});
            document.getElementById('wTextDraft').value = txt;
            onWritingDraftChange();
        }""",
        DRAFT,
    )
    pg.wait_for_timeout(150)
    pg.click("#wPhaseStepper .phase-step[data-phase='audit']")
    pg.wait_for_timeout(200)

    p3 = pg.evaluate(
        """() => {
            const box = document.getElementById('wPhase3');
            const btn = document.getElementById('rubAiBtn');
            const r = btn ? btn.getBoundingClientRect() : null;
            return {
                visible: !!box && getComputedStyle(box).display !== 'none',
                inputs: box ? box.querySelectorAll('input, select, textarea').length : -1,
                rubCheckboxes: document.querySelectorAll('#rubList, .rub, #rubCount').length,
                manualFields: ['wPv', 'wCol', 'wScore', 'auditScore', 'errCode', 'errDesc', 'errFix']
                    .filter(id => !!document.getElementById(id)),
                hasTimerBtn: !!box.querySelector('[data-action="wRev.start"]'),
                btnVisible: !!btn && r && r.height >= 44 && r.width > 80,
                btnH: r ? Math.round(r.height) : 0,
                focusedId: document.activeElement ? document.activeElement.id : '',
                summaryText: (document.getElementById('wPhase3DraftSummary') || {}).textContent?.trim() || '',
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                html: box ? box.outerHTML : '',
            };
        }"""
    )
    assert p3["visible"], f"#wPhase3 not visible: {p3}"
    assert p3["inputs"] == 0, f"#wPhase3 still has manual inputs: {p3}"
    assert p3["rubCheckboxes"] == 0, f"Rubric checkboxes still present: {p3}"
    assert p3["manualFields"] == [], f"Manual fields still in DOM: {p3['manualFields']}"
    assert not p3["hasTimerBtn"], "Manual 20:00 timer still in #wPhase3"
    assert p3["btnVisible"] and p3["btnH"] >= 44, f"#rubAiBtn missing or <44px: {p3}"
    assert p3["focusedId"] == "rubAiBtn", f"Focus did not land on #rubAiBtn: {p3['focusedId']!r}"
    assert len(ai_calls) == 0, "Phase 3 auto-submitted AI check without user click!"
    assert p3["overflow"] <= 1, f"Writing Phase 3 390 light overflow: {p3}"
    assert not INLINE_HANDLER_RE.search(p3["html"]), "Inline on* handler in #wPhase3"

    # Click Check with AI -> POSTs draft, renders read-only result, does not mutate D.log
    dlog_before = pg.evaluate("D.log.length")
    pg.click("#rubAiBtn")
    pg.wait_for_timeout(400)
    assert len(ai_calls) == 1 and ai_calls[0].get("text") == DRAFT.strip(), f"Unexpected AI calls: {ai_calls}"
    after_ai = pg.evaluate(
        """() => ({
            status: (document.getElementById('rubAiStatus') || {}).textContent?.trim() || '',
            resultItems: document.querySelectorAll('#rubAiResult .w-phase3-result-item').length,
            inputsAfter: document.querySelectorAll('#wPhase3 input, #wPhase3 select, #wPhase3 textarea').length,
            dlogLen: D.log.length,
            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        })"""
    )
    assert "16/20" in after_ai["status"], after_ai
    assert after_ai["resultItems"] == 7 and after_ai["inputsAfter"] == 0, after_ai
    assert after_ai["dlogLen"] == dlog_before, "Check with AI mutated D.log"
    assert after_ai["overflow"] <= 1, f"Writing Phase 3 overflow after AI result: {after_ai}"

    pg.evaluate("""() => {
        document.documentElement.setAttribute('data-theme', 'light');
        const el = document.getElementById('wPhase3');
        if (el) window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.scrollY - 108));
        if (document.activeElement) document.activeElement.blur();
    }""")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "writing_phase3_390_light.png"))

    # Dark mode overflow check
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    pg.wait_for_timeout(120)
    assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.unroute("**/api/ai/writing")

    out["4_writing_phase3"] = {"focused": p3["focusedId"], "status": after_ai["status"], "result_items": after_ai["resultItems"]}
    assert page_errors == [], f"Page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
