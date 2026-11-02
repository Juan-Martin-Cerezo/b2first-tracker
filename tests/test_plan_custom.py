"""Phase 42: exam date "I don't know yet" + fully custom weekly plan.

Runs standalone against an isolated server (helpers.isolated_server) and the
shared throwaway account, then asserts on buildWeeklyPlan() evaluated in the
page. No sleep is used to cross ISO weeks: the week is injected as the second
argument of buildWeeklyPlan(D, now).
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = Path(__file__).with_name("out")
OUT.mkdir(exist_ok=True)

BASE_PROFILE = """{
    examDate:null, examDateUnknown:true, targetGrade:'B',
    skills:{rue:3,w:2,l:3,sp:2}, hoursWeek:6,
    days:['mon','wed','sat'], struggles:[], strugglesDeclared:[],
    declaredAt:'2026-10-30T12:00:00Z'
}"""

DIAG = """{
    date:'2026-10-20', correct:4, total:12,
    byPart:{1:{ok:1,n:2},2:{ok:0,n:2},3:{ok:1,n:2},4:{ok:1,n:1},
            5:{ok:1,n:2},6:{ok:1,n:1},7:{ok:0,n:2}},
    weakest:[3,7,5]
}"""


def reset(pg, settings_js="{}"):
    pg.evaluate(
        """(settings) => {
        D.profile = %s;
        D.diag = null;
        D.log = [];
        D.errs = [];
        D.examDates = [];
        D.settings = Object.assign(JSON.parse(JSON.stringify(SETTINGS_DEFAULT)), settings);
        save();
        refreshAll();
    }"""
        % BASE_PROFILE,
        json.loads(settings_js),
    )


def main():
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL + "app", wait_until="networkidle")
        login_owner(pg, URL)
        pg.wait_for_timeout(300)

        # 1. No exam date: the plan still builds and the countdown is honest.
        reset(pg)
        res1 = pg.evaluate(
            """() => {
            const plan = buildWeeklyPlan(D);
            return {
                n: plan.slots.length,
                needDiag: !!plan.needDiag,
                cd: document.getElementById('examCountdown').textContent,
                daysLeftNull: examDaysLeft(null) === null,
                daysLeftEmpty: examDaysLeft('') === null
            };
        }"""
        )
        assert res1["n"] > 0, f"plan with no exam date has no slots: {res1}"
        assert res1["needDiag"] is False, f"unexpected needDiag: {res1}"
        assert "No exam date yet" in res1["cd"], f"missing no-date copy: {res1['cd']!r}"
        assert "NaN" not in res1["cd"], f"NaN in countdown: {res1['cd']!r}"
        assert not re.search(r"(?:^|\s)-\d", res1["cd"]), f"negative countdown: {res1['cd']!r}"
        assert not re.search(r"\b0 days\b", res1["cd"], re.I), f"fake zero countdown: {res1['cd']!r}"
        assert res1["daysLeftNull"] and res1["daysLeftEmpty"], f"null date not guarded: {res1}"
        out["1_sin_fecha"] = f"OK: {res1['n']} slots, no-date card, no NaN"

        # 2. Onboarding: "I don't know yet" advances to step 2 with examDate null.
        pg.evaluate(
            """() => {
            D.profile = null; D.onboardStep = 1; D.onboarded = false; D.diag = null;
            save(); showOnboarding();
        }"""
        )
        pg.wait_for_selector("#obDateUnknown", state="visible", timeout=5000)
        pg.screenshot(path=str(OUT / "plan_custom_onboarding.png"), full_page=True)
        pg.click("#obDateUnknown")
        toggled = pg.evaluate(
            """() => ({
            unknown: OB.draft.examDateUnknown,
            date: OB.draft.examDate,
            disabled: document.getElementById('obExamDate').disabled,
            pressed: document.getElementById('obDateUnknown').getAttribute('aria-pressed')
        })"""
        )
        assert toggled == {
            "unknown": True,
            "date": "",
            "disabled": True,
            "pressed": "true",
        }, f"chip did not switch the field: {toggled}"
        pg.click("#obNextBtn")
        res2 = pg.evaluate(
            """() => ({
            step: OB.step,
            count: document.getElementById('obStepCount').textContent.trim(),
            error: OB.error,
            date: D.profile ? D.profile.examDate : 'missing',
            unknown: D.profile ? D.profile.examDateUnknown : null
        })"""
        )
        assert res2["step"] == 2 and res2["count"].startswith("2/"), f"did not reach step 2: {res2}"
        assert res2["error"] == "", f"onboarding error: {res2}"
        assert res2["date"] is None, f"examDate was coerced: {res2}"
        assert res2["unknown"] is True, f"examDateUnknown lost: {res2}"
        out["2_onboarding_unknown"] = "OK: step 2, examDate=null, examDateUnknown=true"
        pg.evaluate(
            """() => {
            hideOnboarding(); OB.active = false; D.onboarded = true;
            D.onboardStep = 1; save();
        }"""
        )

        # 3. Custom plan is verbatim: same order, day, min, type, part and time.
        reset(pg)
        res3 = pg.evaluate(
            """() => {
            D.settings.planMode = 'custom';
            D.settings.customRotate = false;
            D.settings.customSlots = [
                {day:'tue', time:'18:30', min:45, type:'ue', part:3, kind:null, timed:false},
                {day:'thu', time:'', min:30, type:'l', part:2, kind:null, timed:true},
                {day:'sat', time:'10:00', min:60, type:'w', part:null, kind:'Essay', timed:false}
            ];
            return buildWeeklyPlan(D).slots.map(s => ({
                day:s.day, time:s.time, min:s.min, type:s.type,
                part:s.part, kind:s.kind, timed:s.timed
            }));
        }"""
        )
        expected = [
            {"day": "tue", "time": "18:30", "min": 45, "type": "ue", "part": 3, "kind": None, "timed": False},
            {"day": "thu", "time": None, "min": 30, "type": "l", "part": 2, "kind": None, "timed": True},
            {"day": "sat", "time": "10:00", "min": 60, "type": "w", "part": None, "kind": "Essay", "timed": False},
        ]
        assert res3 == expected, f"custom slots not verbatim:\n{res3}\n!=\n{expected}"
        out["3_plan_verbatim"] = f"OK: {len(res3)} slots in order"

        # 4. customRotate: the same slot rotates between two ISO weeks.
        res4 = pg.evaluate(
            """() => {
            D.settings = JSON.parse(JSON.stringify(SETTINGS_DEFAULT));
            D.settings.planMode = 'custom';
            D.settings.customRotate = true;
            D.settings.rueParts = [1,2,3,4,5,6,7];
            D.settings.customSlots = [
                {day:'mon', time:'', min:45, type:'ue', part:1, kind:null, timed:false}
            ];
            const a = buildWeeklyPlan(D, new Date('2026-01-05T12:00:00'));
            const b = buildWeeklyPlan(D, new Date('2026-01-12T12:00:00'));
            return {a:a.slots[0].part, b:b.slots[0].part, reason:a.slots[0].reason};
        }"""
        )
        assert res4["a"] != res4["b"], f"week rotation did not change the part: {res4}"
        assert "rotated" in res4["reason"], f"reason does not mention rotation: {res4}"
        out["4_rotacion_semanal"] = f"OK: part {res4['a']} -> {res4['b']}"

        # 4b. Summary wording, rotation marker and accessible row actions.
        res4b = pg.evaluate(
            """() => {
            LANG = 'en';
            D.settings = JSON.parse(JSON.stringify(SETTINGS_DEFAULT));
            D.settings.planMode = 'custom';
            D.settings.customRotate = false;
            D.settings.customSlots = [
                {day:'mon', time:'', min:30, type:'ue', part:1, kind:null, timed:false},
                {day:'wed', time:'', min:45, type:'l', part:2, kind:null, timed:false},
                {day:'sat', time:'', min:45, type:'w', part:null, kind:'Essay', timed:false}
            ];
            const summary = obPlanSummaryHtml(buildWeeklyPlan(D));
            D.settings.customRotate = true;
            D.settings.rueParts = [1,2,3,4,5,6,7];
            D.settings.customSlots = [
                {day:'mon', time:'', min:45, type:'ue', part:1, kind:null, timed:false}
            ];
            const rotated = buildWeeklyPlan(D, new Date('2026-01-12T12:00:00'));
            const rotatedRows = obPlanRowsHtml(rotated);
            D.settings.customRotate = false;
            const plainRows = obPlanRowsHtml(buildWeeklyPlan(D, new Date('2026-01-12T12:00:00')));
            const box = document.createElement('div');
            box.innerHTML = rotatedRows + plainRows;
            const rows = Array.from(box.querySelectorAll('.ob-preview-row'));
            return {
                summary: summary,
                rotatedHtml: rotatedRows,
                plainHtml: plainRows,
                rotatedLabel: rows[0].getAttribute('aria-label') || '',
                plainLabel: rows[1].getAttribute('aria-label') || '',
                rotWk: rotated.slots[0].rotatedWeek
            };
        }"""
        )
        assert (
            "3 sessions · 30–45 min each" in res4b["summary"]
            and "120 minutes this week" in res4b["summary"]
        ), f"summary wording wrong: {res4b['summary']}"
        assert (
            "· rot." in res4b["rotatedHtml"]
            and str(res4b["rotWk"]) in res4b["rotatedLabel"]
            and "· rot." not in res4b["plainHtml"]
            and "rotated for week" not in res4b["plainLabel"]
        ), f"rotation marker wrong: {res4b}"
        out["4b_vista_previa"] = "OK: range summary, rotated marker and week label"

        # 5. rueParts filters every UoE slot in automatic mode.
        res5 = pg.evaluate(
            """() => {
            D.settings = JSON.parse(JSON.stringify(SETTINGS_DEFAULT));
            D.settings.rueParts = [2,4];
            D.diag = %s;
            const parts = buildWeeklyPlan(D).slots.filter(s => s.type === 'ue').map(s => s.part);
            return {parts:parts, fallback:buildWeeklyPlan(D).source.fallback};
        }"""
            % DIAG
        )
        assert res5["parts"], f"no UoE slots: {res5}"
        assert all(x in (2, 4) for x in res5["parts"]), f"UoE outside rueParts: {res5}"
        out["5_rueParts"] = f"OK: UoE parts={res5['parts']}"

        # 6. wKinds restricts writing kinds.
        res6 = pg.evaluate(
            """() => {
            D.settings = JSON.parse(JSON.stringify(SETTINGS_DEFAULT));
            D.settings.wKinds = ['Email'];
            D.diag = null;
            D.profile = %s;
            const kinds = buildWeeklyPlan(D).slots.filter(s => s.type === 'w').map(s => s.kind);
            return kinds;
        }"""
            % BASE_PROFILE
        )
        assert res6 and all(k == "Email" for k in res6), f"writing kind outside wKinds: {res6}"
        out["6_wKinds"] = f"OK: writing kinds={res6}"

        # 7. An empty allowlist falls back to every part and records it.
        res7 = pg.evaluate(
            """() => {
            D.settings = JSON.parse(JSON.stringify(SETTINGS_DEFAULT));
            D.settings.rueParts = [];
            D.diag = %s;
            const plan = buildWeeklyPlan(D);
            return {
                fallback: plan.source.fallback,
                parts: plan.slots.filter(s => s.type === 'ue').map(s => s.part)
            };
        }"""
            % DIAG
        )
        assert "rueParts" in res7["fallback"], f"fallback not recorded: {res7}"
        assert res7["parts"] and all(1 <= x <= 7 for x in res7["parts"]), f"bad fallback parts: {res7}"
        out["7_fallback"] = f"OK: fallback={res7['fallback']}, parts={res7['parts']}"

        # 8. slotMin + ignoreIntakeHours + weekGoal drive an exact plan.
        res8 = pg.evaluate(
            """() => {
            D.settings = JSON.parse(JSON.stringify(SETTINGS_DEFAULT));
            D.settings.slotMin = 30;
            D.settings.ignoreIntakeHours = true;
            D.settings.weekGoal = 2;
            D.diag = null;
            D.profile = %s;
            const plan = buildWeeklyPlan(D);
            return {n:plan.slots.length, mins:plan.slots.map(s => s.min)};
        }"""
            % BASE_PROFILE
        )
        assert res8["n"] == 2, f"weekGoal ignored: {res8}"
        assert res8["mins"] == [30, 30], f"slotMin not exact: {res8}"
        out["8_minutos_exactos"] = f"OK: {res8['n']} slots x {res8['mins']} min"

        # 9. The editor persists through localStorage + the server sync.
        pg.evaluate(
            """() => {
            D.settings = JSON.parse(JSON.stringify(SETTINGS_DEFAULT));
            D.settings.planMode = 'auto';
            D.settings.customSlots = [];
            D.diag = null; D.profile = %s;
            save(); refreshAll(); showView('plan');
            document.getElementById('planCustom').open = true;
        }"""
            % BASE_PROFILE
        )
        pg.wait_for_timeout(200)
        pg.click('input[name="pcMode_plan"][value="custom"]')
        pg.wait_for_timeout(150)
        pg.click('#planCustomBody button[data-pc-action="add"]')
        pg.wait_for_timeout(120)
        pg.click('#planCustomBody button[data-pc-action="add"]')
        pg.wait_for_timeout(120)
        pg.click('#planCustomBody button[data-pc-action="add"]')
        pg.wait_for_timeout(120)
        # Three visible rows for the screenshot: UoE, Listening and Writing.
        pg.select_option('#planCustomBody tr[data-pc-row="1"] select[data-pc-field="type"]', "l")
        pg.wait_for_timeout(120)
        pg.select_option('#planCustomBody tr[data-pc-row="2"] select[data-pc-field="type"]', "w")
        pg.wait_for_timeout(150)
        pg.fill('#planCustomBody tr[data-pc-row="0"] input[data-pc-field="min"]', "30")
        pg.dispatch_event('#planCustomBody tr[data-pc-row="0"] input[data-pc-field="min"]', "change")
        pg.wait_for_timeout(150)
        pg.click('#planCustomBody button[data-pc-list="wKinds"][data-pc-value="Article"]')
        pg.wait_for_timeout(200)
        before = pg.evaluate(
            """() => ({
            mode: D.settings.planMode,
            n: D.settings.customSlots.length,
            min: D.settings.customSlots[0].min,
            kinds: D.settings.wKinds.slice(),
            types: D.settings.customSlots.map(s => s.type)
        })"""
        )
        assert before["mode"] == "custom", f"mode not saved: {before}"
        assert before["n"] == 3, f"rows not saved: {before}"
        assert before["min"] == 30, f"minutes not saved: {before}"
        assert "Article" not in before["kinds"], f"allowed kind not saved: {before}"
        assert before["types"] == ["ue", "l", "w"], f"types not saved: {before}"
        labels = pg.evaluate(
            """() => {
            const row = document.querySelector('#planCustomBody tr[data-pc-row="0"]');
            const out = {};
            ['up','down','dup','del'].forEach(a => {
                const b = row.querySelector('[data-pc-action="' + a + '"]');
                out[a] = {label:b.getAttribute('aria-label'), title:b.getAttribute('title')};
            });
            return out;
        }"""
        )
        assert labels == {
            "up": {"label": "Move up", "title": "Move up"},
            "down": {"label": "Move down", "title": "Move down"},
            "dup": {"label": "Duplicate session", "title": "Duplicate session"},
            "del": {"label": "Remove session", "title": "Remove session"},
        }, f"row action labels wrong: {labels}"
        out["9b_labels"] = labels
        pg.evaluate(
            "() => { const el=document.getElementById('planCustom');"
            " el.scrollIntoView({block:'start'}); window.scrollBy(0,-220); }"
        )
        pg.wait_for_timeout(150)
        pg.locator("#planCustom").screenshot(path=str(OUT / "plan_custom_editor.png"))

        pg.wait_for_timeout(900)
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(700)
        after = pg.evaluate(
            """() => ({
            mode: D.settings.planMode,
            n: D.settings.customSlots.length,
            min: D.settings.customSlots[0].min,
            kinds: D.settings.wKinds.slice(),
            types: D.settings.customSlots.map(s => s.type)
        })"""
        )
        assert after == before, f"settings did not survive reload:\nbefore={before}\nafter={after}"
        out["9_persistencia"] = f"OK: {after}"

        # Screenshot (c): Today reading the custom plan.
        pg.evaluate(
            """() => {
            D.settings.planMode = 'custom';
            D.settings.customRotate = true;
            D.settings.rueParts = [1,2,3,4,5,6,7];
            D.settings.customSlots = [
                {day:'mon', time:'18:30', min:45, type:'ue', part:2, kind:null, timed:false},
                {day:'wed', time:'19:00', min:40, type:'l', part:3, kind:null, timed:true},
                {day:'sat', time:'10:00', min:50, type:'w', part:null, kind:'Email', timed:false}
            ];
            D.settings.sessionTime = {mon:'18:30', wed:'19:00', sat:'10:00'};
            save(); refreshAll(); showView('hoy'); refreshAll();
        }"""
        )
        pg.wait_for_timeout(350)
        today = pg.evaluate(
            """() => {
            const el = document.getElementById('todayPlan');
            return {
                visible: el.style.display !== 'none',
                text: el.textContent,
                rows: el.querySelectorAll('.today-plan-row').length,
                rotated: el.textContent.indexOf('Rotated') >= 0
            };
        }"""
        )
        assert today["visible"], f"Today plan card hidden: {today}"
        assert today["rows"] == 3, f"custom sessions not rendered in Today: {today}"
        assert "18:30" in today["text"], f"planned time missing: {today['text']!r}"
        assert "Email" in today["text"], f"writing kind missing: {today['text']!r}"
        pg.locator("#todayPlan").screenshot(path=str(OUT / "plan_custom_today.png"))
        out["10_today"] = f"OK: {today['rows']} custom rows, time + kind shown"

        # ---------- Phase 44: three blocks, two of them collapsed ----------
        def reset_plan_tab():
            pg.evaluate(
                """() => {
                D.settings = JSON.parse(JSON.stringify(SETTINGS_DEFAULT));
                D.settings.weekGoal = 4;
                D.settings.ignoreIntakeHours = true;
                D.profile = %s;
                D.diag = null;
                D.log = []; D.errs = [];
                save(); refreshAll(); showView('plan'); refreshAll();
            }"""
                % BASE_PROFILE
            )
            pg.wait_for_timeout(250)

        reset_plan_tab()

        # 11. The editor is visible with no click; the two blocks start collapsed.
        pg.evaluate("window.scrollTo(0, 0)")
        state = pg.evaluate(
            """() => ({
            customVisible: document.getElementById('planCustom').getBoundingClientRect().height > 0,
            tuningOpen: document.getElementById('planTuning').open,
            accountOpen: document.getElementById('planAccount').open,
            order: Array.from(document.getElementById('v-plan').children)
                .map(el => el.id).filter(Boolean)
        })"""
        )
        assert state["customVisible"], f"editor is not visible without a click: {state}"
        assert state["tuningOpen"] is False, f"fine-tuning is open: {state}"
        assert state["accountOpen"] is False, f"account block is open: {state}"
        assert state["order"][:3] == ["examCountdown", "weeklyPlanCard", "planCustom"], (
            f"PLAN blocks out of order: {state['order']}"
        )
        pg.screenshot(path=str(OUT / "plan44_top.png"))
        out["11_editor_visible"] = f"OK: order={state['order']}, both blocks collapsed"

        # 12. Regenerate rebuilds the plan (and stores the snapshot).
        pg.click("#wpRegenBtn")
        pg.wait_for_function(
            "document.getElementById('wpRegenStatus').textContent.indexOf('Plan rebuilt') >= 0",
            timeout=5000,
        )
        regen = pg.evaluate(
            """() => ({
            status: document.getElementById('wpRegenStatus').textContent,
            role: document.getElementById('wpRegenStatus').getAttribute('role'),
            slots: buildWeeklyPlan(D).slots.length,
            snapshot: D.profile && D.profile.plan ? D.profile.plan.slots.length : null,
            stored: D.profile && !!D.profile.plan
        })"""
        )
        assert "Plan rebuilt" in regen["status"], f"no rebuilt status: {regen}"
        assert str(regen["slots"]) in regen["status"], f"slot count missing: {regen}"
        assert regen["stored"] and regen["snapshot"] == regen["slots"], f"snapshot not stored: {regen}"
        assert regen["role"] == "status", f"status has no role: {regen}"
        out["12_regen"] = regen["status"]

        # 12b. In custom mode the message says the week rotation was re-applied.
        pg.evaluate(
            """() => {
            D.settings.planMode = 'custom';
            D.settings.customRotate = true;
            D.settings.rueParts = [1,2,3,4,5,6,7];
            D.settings.customSlots = [
                {day:'mon', time:'', min:45, type:'ue', part:1, kind:null, timed:false},
                {day:'wed', time:'', min:30, type:'l', part:2, kind:null, timed:false}
            ];
            save(); refreshAll();
        }"""
        )
        pg.click("#wpRegenBtn")
        pg.wait_for_function(
            "document.getElementById('wpRegenStatus').textContent.indexOf('rotated for week') >= 0",
            timeout=5000,
        )
        out["12b_regen_custom"] = pg.text_content("#wpRegenStatus")

        # 13. No dotted bubbles left inside the PLAN tab.
        bubbles = pg.evaluate(
            """() => ({
            dots: document.querySelectorAll('#v-plan .dot').length,
            chips: document.querySelectorAll('#v-plan .chip-plan').length,
            emptyDots: Array.from(document.querySelectorAll('#v-plan span.dot'))
                .filter(el => !el.textContent.trim()).length
        })"""
        )
        assert bubbles == {"dots": 0, "chips": 0, "emptyDots": 0}, f"bubbles remain: {bubbles}"
        out["13_sin_burbujas"] = "OK: no .dot / .chip-plan in #v-plan"

        # 14. One control sets the weekly session count, and the preview follows.
        reset_plan_tab()
        pg.click("#planTuning > summary")
        pg.wait_for_timeout(150)
        count_controls = pg.evaluate(
            """() => ({
            goal: document.querySelectorAll('#v-plan #pWeekGoal').length,
            editorGoal: !!document.getElementById('pcWeekGoal_plan')
        })"""
        )
        assert count_controls == {"goal": 1, "editorGoal": False}, f"duplicate week controls: {count_controls}"
        pg.fill("#pWeekGoal", "2")
        pg.dispatch_event("#pWeekGoal", "change")
        pg.wait_for_timeout(200)
        weekly = pg.evaluate(
            """() => ({
            goal: D.settings.weekGoal,
            value: document.getElementById('pWeekGoal').value,
            slots: buildWeeklyPlan(D).slots.length,
            preview: document.querySelectorAll('#pcPreviewBody_plan .ob-preview-row').length,
            label: (document.querySelector('label[for="pWeekGoal"]') || {}).textContent || ''
        })"""
        )
        assert weekly["goal"] == 2 and weekly["value"] == "2", f"weekGoal did not apply: {weekly}"
        assert weekly["slots"] == 2, f"preview did not follow weekGoal: {weekly}"
        assert weekly["preview"] == 2, f"editor preview did not follow weekGoal: {weekly}"
        assert "Sessions per week" in weekly["label"], f"wrong weekGoal label: {weekly['label']!r}"
        out["14_un_control_semana"] = f"OK: weekGoal={weekly['goal']}, slots={weekly['slots']}"
        pg.locator("#planTuning").screenshot(path=str(OUT / "plan44_tuning_open.png"))

        # 15. Every id the JS reads survived the re-parenting.
        ids = [
            "pUeMin", "pE0w", "pRueCycle", "pEven", "pOdd", "pADay", "pATime",
            "pBDay", "pBTime", "scheduleRowsContainer", "planCode", "byoKey",
            "langEnBtn", "langEsBtn", "pListenMin", "pPlanMin", "pWriteMin",
            "pRevMin", "pSp1Sec", "pSp2Sec", "pVoice", "pWMin", "pWMax",
            "pStreakFreeze", "pWeekGoal", "pE0u", "pE0l", "pE1w", "pE1wm",
            "pE1u", "pE1l", "pE2r", "pE2rm", "pE2w", "pE2l", "pE2ln",
            "byoProvider", "byoBase", "byoModel", "byoKeyToggle", "byoTestStatus",
            "planNameText", "planWriteText", "planSpeakText", "planRedeemBtn",
            "planSubscribeBtn", "planPortalBtn", "wpRegenBtn", "wpRegenStatus",
            "planCustomBody", "weeklyPlanCard", "examCountdown",
        ]
        missing = pg.evaluate("(ids) => ids.filter(id => !document.getElementById(id))", ids)
        assert missing == [], f"ids lost in the restructure: {missing}"
        out["15_ids"] = f"OK: {len(ids)} ids present"

        # Account block opens on demand; screenshot for the record.
        pg.click("#planAccount > summary")
        pg.wait_for_timeout(200)
        assert pg.evaluate("document.getElementById('planAccount').open") is True
        pg.locator("#planAccount").screenshot(path=str(OUT / "plan44_account_open.png"))
        out["16_account"] = "OK: account block opens and shows provider + restore"

        assert errs == [], f"JS errors: {errs}"
        out["errores_js"] = errs
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
