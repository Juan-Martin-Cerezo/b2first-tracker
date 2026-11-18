"""End-to-end Playwright tests for the Progression Matrix (Fase P2).

Covers:
1. Empty state -> stage 0, all gates fail, zero JS errors, CTA visible.
2. Pure deterministic calcGates() + getProgression() + buildWeeklyPlan() consistency.
3. Exact boundary conditions: just below threshold fails, at threshold passes.
4. Monotonic single-step stage transitions (never skips 0 -> 2 in one call, never regresses).
5. Idempotence & server persistence across page reloads (PUT /api/progress + reload).
6. Manual overrides: honest numbers unchanged, manual:true + date, undo reverts override.
7. Edge cases: total:0 (no NaN/ZeroDivision), future dates ignored, >60d (90d) diag rejected as stale.
8. Legacy migration without stageHistory -> preserves stage, creates entry with at:null.
9. Mobile 360px layout: single-column cards, no horizontal overflow, >=44px targets, focus visible.
"""

import asyncio
import datetime
import json
import uuid

from playwright.async_api import async_playwright

from helpers import isolated_server

URL = isolated_server() + "/"
PASSWORD = "TestPassword!2026"


def iso_days_ago(days: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def future_iso(days: int = 30) -> str:
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def fresh_diag_data(days_ago: int = 5) -> dict:
    return {
        "date": iso_days_ago(days_ago),
        "correct": 8,
        "total": 12,
        "byPart": {
            "1": {"ok": 2, "n": 2},
            "2": {"ok": 1, "n": 2},
            "3": {"ok": 1, "n": 2},
            "4": {"ok": 1, "n": 1},
            "5": {"ok": 1, "n": 2},
            "6": {"ok": 1, "n": 1},
            "7": {"ok": 1, "n": 2},
        },
        "weakest": [2, 3, 7],
    }


def stage0_logs(below_part4: bool = False, below_l2: bool = False, below_w: bool = False, below_sp: bool = False, d: str | None = None) -> list:
    date_str = d or iso_days_ago(2)
    logs = []
    # R&UE Parts 1..7 (need >= 60%)
    for p in range(1, 8):
        correct = 59 if (below_part4 and p == 4) else 60
        logs.append({"date": date_str, "type": "ue", "part": p, "correct": correct, "total": 100, "min": 10})
    # Listening Parts 1..4 (need >= 20/30 equivalent ~66.7%, P2 errors <= 3 => >= 7/10)
    for p in range(1, 5):
        if p == 2 and below_l2:
            logs.append({"date": date_str, "type": "lp", "part": p, "correct": 6, "total": 10, "min": 8})  # 4 errors > 3
        else:
            logs.append({"date": date_str, "type": "lp", "part": p, "correct": 7, "total": 10, "min": 8})  # 70% >= 20/30, 3 errors <= 3
    # Writing genres (5 genres >= 14)
    for g in ["Essay", "Article", "Email", "Review", "Report"]:
        score = 13.5 if (below_w and g == "Essay") else 14
        logs.append({"date": date_str, "type": "w", "kind": g, "score": score, "min": 40})
    # Speaking Parts 1..4 (need >= 3/5)
    for p in range(1, 5):
        score = 2 if (below_sp and p == 4) else 3
        logs.append({"date": date_str, "type": "sp", "part": p, "score": score, "min": 5})
    return logs


def stage1_logs(d: str | None = None) -> list:
    date_str = d or iso_days_ago(1)
    logs = []
    # R&UE Parts 1..7 >= 75%
    for p in range(1, 8):
        logs.append({"date": date_str, "type": "ue", "part": p, "correct": 75, "total": 100, "min": 10})
    # Listening Parts 1..4 >= 24/30 (80%)
    for p in range(1, 5):
        logs.append({"date": date_str, "type": "lp", "part": p, "correct": 8, "total": 10, "min": 8})
    # Writing 5 genres >= 16 in <= 45 min
    for g in ["Essay", "Article", "Email", "Review", "Report"]:
        logs.append({"date": date_str, "type": "w", "kind": g, "score": 16, "min": 45})
    # Speaking Parts 1..4 >= 4/5
    for p in range(1, 5):
        logs.append({"date": date_str, "type": "sp", "part": p, "score": 4, "min": 5})
    return logs


async def register_and_login(page, prefix: str = "prog") -> dict:
    uname = f"{prefix}_{uuid.uuid4().hex[:8]}"
    res = await page.request.post(
        URL + "api/register",
        data={"name": uname, "password": PASSWORD},
    )
    assert res.status == 200, f"register failed: {res.status} {await res.text()}"
    user = await res.json()
    await page.goto(URL + "app", wait_until="networkidle")
    await page.evaluate(
        """(u) => {
        localStorage.clear();
        const userObj = {id: u.id, name: u.name, color: u.color || '#1e3a8a', token: u.token};
        localStorage.setItem('b2first_user', JSON.stringify(userObj));
        localStorage.setItem('ob_' + u.id, '1');
        USER = userObj;
        D = load();
        D.onboarded = true;
        D.settings = Object.assign({}, D.settings || {}, {lang: 'en', schedule: [{day:1,time:'15:30'}]});
        hideAuthOverlay();
        hideOnboarding();
        refreshAll();
    }""",
        user,
    )
    return user


async def wait_next_put_ok(page, action_coro):
    async with page.expect_response(
        lambda r: "/api/progress" in r.url and r.request.method == "PUT"
    ) as resp_info:
        await action_coro()
    resp = await resp_info.value
    assert resp.status == 200, f"Expected PUT /api/progress 200, got {resp.status}"


async def open_progress_view(page):
    await page.evaluate("() => showView('prog')")
    await page.wait_for_selector("#v-prog.active #gates .gate-stages")


async def run_desktop_tests(browser) -> dict:
    out = {}
    context = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await context.new_page()
    page_errors = []
    console_errors = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

    user = await register_and_login(page, "prog_d")
    await open_progress_view(page)

    # 1. Empty state -> stage 0, all gates fail, CTA visible, zero errors
    empty_state = await page.evaluate(
        """() => {
        D.log = []; D.errs = []; D.diag = null; D.stage = 0; D.stageHistory = []; D.overrides = {};
        refreshAll();
        const p = getProgression(D);
        return {
            stage: p.stage,
            allFail: p.stages.every(s => s.gates.every(g => !g.pass)),
            gateCount: p.stages.reduce((n, s) => n + s.gates.length, 0),
            hasCta: !!document.getElementById('gateEmptyCta'),
            ctaBtns: document.querySelectorAll('#gateEmptyCta [data-gate-cta]').length,
            stageCards: document.querySelectorAll('#gates .gate-stage-card').length,
            weeklySourceProg: buildWeeklyPlan(D).source.progression
        };
    }"""
    )
    assert empty_state["stage"] == 0
    assert empty_state["allFail"] is True
    assert empty_state["gateCount"] == 15
    assert empty_state["hasCta"] is True
    assert empty_state["ctaBtns"] == 2
    assert empty_state["stageCards"] == 3
    assert empty_state["weeklySourceProg"]["stage"] == 0
    assert not page_errors and not console_errors
    out["1_empty_state"] = f"OK ({empty_state['gateCount']} gates all fail, CTA visible)"

    # 2. Pure deterministic calcGates()
    sample_doc = {
        "stage": 0,
        "overrides": {},
        "diag": fresh_diag_data(10),
        "log": stage0_logs(below_part4=True),
        "errs": [],
        "settings": {"lang": "en", "e0": {"w": 14, "u": 60, "l": 3}},
    }
    det = await page.evaluate(
        """({doc, todayKey}) => {
        const before = JSON.stringify(doc);
        const a = calcGates(doc, todayKey);
        const b = calcGates(doc, todayKey);
        const after = JSON.stringify(doc);
        return {
            sameOutput: JSON.stringify(a) === JSON.stringify(b),
            unchangedInput: before === after
        };
    }""",
        {"doc": sample_doc, "todayKey": datetime.date.today().isoformat()},
    )
    assert det["sameOutput"] is True and det["unchangedInput"] is True
    out["2_pure_deterministic"] = "OK (identical output, zero mutation)"

    # 3. Boundary checks: just below vs exactly at thresholds (Stage 0)
    below_res = await page.evaluate(
        """({diagStale, logs}) => {
        D.diag = diagStale; // 61 days old -> stale!
        D.log = logs;
        D.errs = [];
        D.stage = 0;
        D.stageHistory = [];
        D.overrides = {};
        const adv = advanceStageIfReady({save: false});
        const p = getProgression(D);
        return {
            stage: p.stage,
            advanced: adv.advanced,
            passes: p.stages[0].gates.map(g => ({id: g.id, pass: g.pass, have: g.have, need: g.need}))
        };
    }""",
        {
            "diagStale": fresh_diag_data(61),
            "logs": stage0_logs(below_part4=True, below_l2=True, below_w=True, below_sp=True),
        },
    )
    assert below_res["stage"] == 0
    assert below_res["advanced"] is False
    assert all(not g["pass"] for g in below_res["passes"]), f"Expected all S0 gates below threshold to fail: {below_res}"

    # Now right AT threshold (diag exactly 60 days old, UE P4 = 60, LP P2 = 7/10 [3 errors], Essay = 14, SP P4 = 3)
    async def save_stage0_pass():
        await page.evaluate(
            """({diagBoundary, logs}) => {
            D.diag = diagBoundary;
            D.log = logs;
            D.errs = [];
            const adv = advanceStageIfReady({save: false});
            save();
            refreshAll();
            window.__lastAdv = adv;
        }""",
            {"diagBoundary": fresh_diag_data(60), "logs": stage0_logs()},
        )

    await wait_next_put_ok(page, save_stage0_pass)
    at_res = await page.evaluate(
        """() => ({
        adv: window.__lastAdv,
        stage: D.stage,
        history: D.stageHistory,
        s0Pass: getProgression(D).stages[0].pass,
        ctaGone: !document.getElementById('gateEmptyCta')
    })"""
    )
    assert at_res["adv"]["advanced"] is True
    assert at_res["stage"] == 1
    assert len(at_res["history"]) == 1
    assert at_res["history"][0]["stage"] == 1
    assert at_res["history"][0]["at"] is not None
    assert at_res["s0Pass"] is True
    assert at_res["ctaGone"] is True
    out["3_boundary_and_advance"] = "OK (below fails 0, exact boundary passes -> stage 1 once)"

    # 4. Idempotence & persistence across reload
    idem = await page.evaluate(
        """() => {
        const a1 = advanceStageIfReady({save: false});
        refreshAll();
        const a2 = advanceStageIfReady({save: false});
        return {a1, a2, stage: D.stage, histLen: D.stageHistory.length, hist0: D.stageHistory[0]};
    }"""
    )
    assert idem["a1"]["advanced"] is False and idem["a2"]["advanced"] is False
    assert idem["stage"] == 1 and idem["histLen"] == 1

    # Reload from server (ensure pull completes before checking)
    async with page.expect_response(
        lambda r: "/api/progress" in r.url and r.request.method == "GET" and "download=1" in r.url
    ):
        await page.reload(wait_until="networkidle")
    await open_progress_view(page)
    after_reload = await page.evaluate(
        """() => ({
        stage: D.stage,
        hist: D.stageHistory,
        summaryText: (document.querySelector('#gates .gate-summary') || {}).textContent || ''
    })"""
    )
    assert after_reload["stage"] == 1
    assert len(after_reload["hist"]) == 1
    assert after_reload["hist"][0]["at"] == idem["hist0"]["at"]
    assert "Stage 1" in after_reload["summaryText"]
    out["4_idempotent_reload"] = "OK (stage 1 and single history entry survived reload)"

    # 5. Monotonicity (never regresses) & never jumps 2 stages at once
    mono = await page.evaluate(
        """() => {
        D.log = []; D.errs = []; D.diag = null;
        advanceStageIfReady({save: false});
        const stageAfterDelete = D.stage;

        // Also test fresh doc qualifying for both Stage 0 and Stage 1 simultaneously
        const both = {
            stage: 0,
            stageHistory: [],
            overrides: {},
            diag: freshDiag(5),
            log: stageBoth(),
            errs: [],
            settings: Object.assign({}, D.settings, {lang: 'en'})
        };
        return {stageAfterDelete, curStage: D.stage};
    }""".replace(
            "freshDiag(5)", json.dumps(fresh_diag_data(5))
        ).replace(
            "stageBoth()", json.dumps(stage0_logs() + stage1_logs())
        )
    )
    assert mono["stageAfterDelete"] == 1, f"Stage regressed when data deleted: {mono}"

    no_skip = await page.evaluate(
        """({diag, logs}) => {
        D.stage = 0; D.stageHistory = []; D.overrides = {};
        D.diag = diag; D.log = logs; D.errs = [];
        const r1 = advanceStageIfReady({save: false});
        const sAfter1 = D.stage;
        const r2 = advanceStageIfReady({save: false});
        const sAfter2 = D.stage;
        return {r1, sAfter1, r2, sAfter2, histLen: D.stageHistory.length};
    }""",
        {"diag": fresh_diag_data(5), "logs": stage0_logs() + stage1_logs()},
    )
    assert no_skip["r1"]["advanced"] is True and no_skip["sAfter1"] == 1
    assert no_skip["r2"]["advanced"] is True and no_skip["sAfter2"] == 2
    assert no_skip["histLen"] == 2
    out["5_monotonic_no_skip"] = "OK (no regression on delete; 0->1 then 1->2, never 0->2)"

    # 6. Manual overrides + honest numbers + undo + advance via override + non-regression on undo
    async def reset_to_stage1_empty():
        await page.evaluate(
            """() => {
            D.stage = 1;
            D.stageHistory = [{stage: 1, at: '2026-11-10T10:00:00.000Z', reason: 'Stage 0 gates completed'}];
            D.overrides = {};
            D.log = [];
            D.errs = [];
            D.diag = null;
            save();
            refreshAll();
        }"""
        )

    await wait_next_put_ok(page, reset_to_stage1_empty)

    # Override one Stage 1 gate via real button click
    btn_s1_err = page.locator('[data-gate-action="override"][data-gate-id="s1-err"]')
    await wait_next_put_ok(page, btn_s1_err.click)
    ov_one = await page.evaluate(
        """() => {
        const g = getProgression(D).stages[1].gates.find(x => x.id === 's1-err');
        const row = document.querySelector('[data-gate-id="s1-err"]');
        return {
            stage: D.stage,
            ovEntry: D.overrides['s1-err'],
            gate: {pass: g.pass, dataPass: g.dataPass, have: g.have, need: g.need, manual: g.manual},
            rowManual: row ? row.getAttribute('data-manual') : null,
            rowText: row ? row.textContent : '',
            hasManualClass: row ? row.classList.contains('manual') : false
        };
    }"""
    )
    assert ov_one["stage"] == 1
    assert ov_one["ovEntry"]["manual"] is True and isinstance(ov_one["ovEntry"]["at"], str)
    assert ov_one["gate"]["manual"] is True
    assert ov_one["gate"]["pass"] is True
    assert ov_one["gate"]["dataPass"] is False
    assert ov_one["gate"]["have"] == 0, f"Override modified numeric have: {ov_one}"
    assert ov_one["rowManual"] == "1" and ov_one["hasManualClass"] is True
    assert "Manual override" in ov_one["rowText"]

    # Undo while still Stage 1
    undo_s1_err = page.locator('[data-gate-action="undo"][data-gate-id="s1-err"]')
    await wait_next_put_ok(page, undo_s1_err.click)
    after_undo_mid = await page.evaluate(
        """() => {
        const g = getProgression(D).stages[1].gates.find(x => x.id === 's1-err');
        return {ov: D.overrides['s1-err'], pass: g.pass, manual: g.manual, have: g.have, stage: D.stage};
    }"""
    )
    assert after_undo_mid["ov"] is None
    assert after_undo_mid["manual"] is False and after_undo_mid["pass"] is False
    assert after_undo_mid["have"] == 0 and after_undo_mid["stage"] == 1

    # Now manually override all 5 Stage 1 gates via UI clicks -> advances 1 -> 2
    for gid in ["s1-rue", "s1-l", "s1-w", "s1-sp", "s1-err"]:
        await wait_next_put_ok(page, page.locator(f'[data-gate-action="override"][data-gate-id="{gid}"]').click)
    adv_via_ov = await page.evaluate("() => ({stage: D.stage, hist: D.stageHistory})")
    assert adv_via_ov["stage"] == 2
    assert adv_via_ov["hist"][-1]["stage"] == 2
    assert "override" in adv_via_ov["hist"][-1]["reason"].lower()

    # Undo an override AFTER advancement -> override reverts, numeric have stays 0, stage stays 2 (monotonic!)
    await wait_next_put_ok(page, page.locator('[data-gate-action="undo"][data-gate-id="s1-err"]').click)
    after_undo_adv = await page.evaluate(
        """() => {
        const g = getProgression(D).stages[1].gates.find(x => x.id === 's1-err');
        return {stage: D.stage, manual: g.manual, pass: g.pass, have: g.have};
    }"""
    )
    assert after_undo_adv["manual"] is False and after_undo_adv["pass"] is False
    assert after_undo_adv["have"] == 0
    assert after_undo_adv["stage"] == 2, f"Undo regressed stage: {after_undo_adv}"
    out["6_manual_overrides_undo"] = "OK (honest numbers, visual badge, advance via override, monotonic undo)"

    # 7. Edge cases: total:0, future dates, 90-day-old diag
    edge_res = await page.evaluate(
        """({pastDate, futDate, diag90}) => {
        D.stage = 0; D.stageHistory = []; D.overrides = {};
        D.diag = diag90;
        D.log = [
            {date: pastDate, type: 'ue', part: 1, correct: 0, total: 0, min: 10},
            {date: pastDate, type: 'l', correct: 0, total: 0, min: 40},
            {date: futDate, type: 'ue', part: 1, correct: 100, total: 100, min: 10},
            {date: futDate, type: 'w', kind: 'Essay', score: 20, min: 30}
        ];
        D.errs = [
            {date: futDate, code: 'T-LIM', part: 1, note: 'future'}
        ];
        advanceStageIfReady({save: false});
        renderGates();
        renderWeeklyPlan();
        const p = getProgression(D);
        const plan = buildWeeklyPlan(D);
        const s0Diag = p.stages[0].gates.find(g => g.id === 's0-diag');
        const allNumsValid = p.stages.every(s => s.gates.every(g =>
            Number.isFinite(g.have) && Number.isFinite(g.need) && Number.isFinite(g.pct) &&
            String(g.have) !== 'NaN' && !String(g.evidence).includes('NaN')
        ));
        return {
            stage: p.stage,
            diagFresh: p.diag.fresh,
            diagStale: p.diag.stale,
            s0DiagPass: s0Diag.pass,
            s0DiagEvidence: s0Diag.evidence,
            s0RueHave: p.stages[0].gates.find(g => g.id === 's0-rue').have,
            sessionsTotal: p.sessions.total,
            ignoredFuture: p.sessions.ignoredFuture,
            ignoredZero: p.sessions.ignoredZero,
            errsTotal: p.errors.total,
            allNumsValid: allNumsValid,
            planDiag: plan.source.diag,
            planProg: plan.source.progression,
            domText: (document.getElementById('gates') || {}).textContent || ''
        };
    }""",
        {"pastDate": iso_days_ago(5), "futDate": future_iso(30), "diag90": fresh_diag_data(90)},
    )
    assert edge_res["stage"] == 0
    assert edge_res["allNumsValid"] is True
    assert "NaN" not in edge_res["domText"]
    assert edge_res["diagFresh"] is False and edge_res["diagStale"] is True
    assert edge_res["s0DiagPass"] is False
    assert "60" in edge_res["s0DiagEvidence"] and "90" in edge_res["s0DiagEvidence"], edge_res["s0DiagEvidence"]
    assert edge_res["s0RueHave"] == 0, f"Future or total:0 log counted: {edge_res}"
    assert edge_res["sessionsTotal"] == 0
    assert edge_res["ignoredFuture"] == 2
    assert edge_res["ignoredZero"] == 2
    assert edge_res["errsTotal"] == 0
    assert edge_res["planProg"]["diagStale"] is True
    assert edge_res["planDiag"] is None
    out["7_edge_cases"] = "OK (total:0/future ignored, 90d diag flagged stale & rejected in gates+plan)"

    # 8. Legacy migration (doc without stageHistory, legacy overrides, stage:1)
    legacy_doc = {
        "log": [],
        "errs": [],
        "examDates": [],
        "stage": 1,
        "overrides": {"0-0": True, "s1-w": True},
        "settings": {"lang": "en", "schedule": [{"day": 1, "time": "15:30"}]},
        "onboarded": True,
    }
    put_res = await page.request.put(
        URL + f"api/progress?user={user['id']}",
        headers={"Authorization": f"Bearer {user['token']}"},
        data=json.dumps(legacy_doc),
    )
    assert put_res.status == 200, f"Legacy PUT failed: {put_res.status} {await put_res.text()}"

    # Clear per-user localStorage so reload pulls legacy doc fresh through load()+syncPull()
    await page.evaluate("(uid) => localStorage.removeItem('b2f_v1_' + uid)", user["id"])
    async with page.expect_response(
        lambda r: "/api/progress" in r.url and r.request.method == "GET" and "download=1" in r.url
    ):
        await page.reload(wait_until="networkidle")
    await open_progress_view(page)
    mig = await page.evaluate(
        """() => {
        const s1w = getProgression(D).stages[1].gates.find(g => g.id === 's1-w');
        return {
            stage: D.stage,
            hist: D.stageHistory,
            ovLegacy: D.overrides['0-0'],
            ovS1W: D.overrides['s1-w'],
            s1wManual: s1w.manual,
            s1wPass: s1w.pass,
            domText: (document.getElementById('gates') || {}).textContent || ''
        };
    }"""
    )
    assert mig["stage"] == 1
    assert isinstance(mig["hist"], list) and len(mig["hist"]) == 1
    assert mig["hist"][0]["stage"] == 1 and mig["hist"][0]["at"] is None
    assert mig["ovLegacy"] == {"manual": True, "at": None}
    assert mig["s1wManual"] is True and mig["s1wPass"] is True
    assert "date unknown (migrated)" in mig["domText"]
    assert "Unlocked (prior to history tracking)" in mig["domText"]
    out["8_legacy_migration"] = "OK (stage 1 kept, stageHistory[0].at === null, legacy overrides kept)"

    assert not page_errors, f"Desktop pageerror: {page_errors}"
    assert not console_errors, f"Desktop console error: {console_errors}"
    await context.close()
    return out


async def run_mobile_tests(browser) -> dict:
    context = await browser.new_context(
        viewport={"width": 360, "height": 740},
        is_mobile=True,
        has_touch=True,
    )
    page = await context.new_page()
    page_errors = []
    console_errors = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

    await register_and_login(page, "prog_m")
    # Put one manual override on Stage 0 so Undo button is also rendered and measured at 360px
    await page.evaluate(
        """() => {
        D.log = []; D.errs = []; D.diag = null; D.stage = 0; D.stageHistory = [];
        D.overrides = {'s0-diag': {manual: true, at: '2026-11-18'}};
        refreshAll();
    }"""
    )
    await open_progress_view(page)

    mob = await page.evaluate(
        """() => {
        const overflow = document.documentElement.scrollWidth > window.innerWidth + 1;
        const stagesEl = document.querySelector('#gates .gate-stages');
        const stageCards = [...document.querySelectorAll('#gates .gate-stage-card')].map(c => c.getBoundingClientRect());
        // Single-column stage cards: each card's bottom <= next card's top (allowing 1px rounding)
        const stagesSingleCol = stageCards.length === 3 &&
            stageCards[0].bottom <= stageCards[1].top + 2 &&
            stageCards[1].bottom <= stageCards[2].top + 2;

        // First stage card's gate rows and cells: cells stack vertically inside each gate card
        const rows = [...document.querySelectorAll('#gates .gate-stage-card[data-stage="0"] .gate-row')];
        const rowsStacked = rows.length === 5 && rows.every(r => {
            const cells = [...r.querySelectorAll('.gate-cell')].map(c => c.getBoundingClientRect());
            // Cells occupy full width vertically rather than 5 side-by-side table columns
            return cells.length === 5 && cells[0].bottom <= cells[1].top + 2 && cells[1].bottom <= cells[2].top + 2;
        });

        // All visible buttons in #gates must be >= 44x44
        const btns = [...document.querySelectorAll('#gates button')].filter(b => b.offsetParent !== null).map(b => {
            const r = b.getBoundingClientRect();
            return {text: b.textContent.trim(), w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10};
        });
        const badBtns = btns.filter(b => b.w < 43.9 || b.h < 43.9);
        return {
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
            overflow,
            stagesSingleCol,
            rowsStacked,
            btnCount: btns.length,
            badBtns,
            roles: {
                tables: document.querySelectorAll('#gates [role="table"]').length,
                headers: document.querySelectorAll('#gates [role="columnheader"]').length,
                rows: document.querySelectorAll('#gates [role="row"]').length
            }
        };
    }"""
    )
    assert mob["overflow"] is False, f"Horizontal overflow at 360px: {mob}"
    assert mob["stagesSingleCol"] is True, f"Stage cards not stacked vertically: {mob}"
    assert mob["rowsStacked"] is True, f"Mobile gate cards not single-column vertical cards: {mob}"
    assert mob["btnCount"] >= 5 and not mob["badBtns"], f"Tap target <44px: {mob['badBtns']}"
    assert mob["roles"]["tables"] == 3 and mob["roles"]["headers"] == 15

    # Keyboard focus visibility check on first matrix button
    first_btn = page.locator("#gates button").first
    await first_btn.focus()
    # Tab back/forward with keyboard so :focus-visible matches Chromium's keyboard modality
    await page.keyboard.press("Tab")
    await page.keyboard.press("Shift+Tab")
    focus_style = await first_btn.evaluate(
        """(el) => {
        const s = getComputedStyle(el);
        return {
            isFocused: document.activeElement === el,
            outlineStyle: s.outlineStyle,
            outlineWidth: parseFloat(s.outlineWidth) || 0,
            boxShadow: s.boxShadow
        };
    }"""
    )
    assert focus_style["isFocused"] is True
    assert (focus_style["outlineStyle"] != "none" and focus_style["outlineWidth"] > 0) or focus_style["boxShadow"] != "none", (
        f"No visible focus indicator on #gates button: {focus_style}"
    )

    assert not page_errors, f"Mobile pageerror: {page_errors}"
    assert not console_errors, f"Mobile console error: {console_errors}"
    await context.close()
    return {
        "9_mobile_360px": f"OK (no overflow {mob['scrollWidth']}/{mob['innerWidth']}, {mob['btnCount']} buttons >=44px, focus ring {focus_style['outlineWidth']}px)"
    }


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        out = {}
        out.update(await run_desktop_tests(browser))
        out.update(await run_mobile_tests(browser))
        await browser.close()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
