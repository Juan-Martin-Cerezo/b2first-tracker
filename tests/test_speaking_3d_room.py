#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playwright tests for Speaking 3D exam room (Phase SPK3D-1, SPK3D-2 & SPK3D-3).

Run: cd tests && uv run --with playwright python test_speaking_3d_room.py
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
OUT_DIR = os.path.join(TESTS_DIR, "out")
os.makedirs(OUT_DIR, exist_ok=True)

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

from helpers import isolated_server, login_owner, OWNER_NAME  # noqa: E402

EXPECTED_SEATS = {
    "you": [0.18, 0.46, 0.82],
    "partner": [-0.62, 0.46, 0.82],
    "examiner": [0.18, 0.46, -0.86],
    "assessor": [-0.52, 0.46, -1.72],
}


def wait_for_mic_ready(pg, timeout=15000):
    pg.wait_for_function(
        """() => {
            const b = document.getElementById('speakingMicBtn');
            return b && !b.disabled && b.getAttribute('data-mic-state') === 'ready';
        }""",
        timeout=timeout,
    )
    pg.wait_for_timeout(140)


def hold_to_speak(pg, transcript_text, hold_ms=100):
    pg.evaluate(
        """(tx) => {
            window.__SPK_TEST_AUDIO_STUB__ = true;
            window.__SPK_TEST_TRANSCRIPT_FN__ = () => tx;
        }""",
        transcript_text,
    )
    box = pg.locator("#speakingMicBtn").bounding_box()
    assert box and box["height"] >= 56, f"Mic button too small: {box}"
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    pg.mouse.move(cx, cy)
    pg.mouse.down()
    pg.wait_for_timeout(hold_ms)
    pg.mouse.up()


def enter_part(pg, part_num):
    pg.evaluate("openSpeakingExam()")
    pg.wait_for_selector("#speakingOverlay.is-open")
    pg.wait_for_selector("#speakingCatalogGrid .spk3-exam-card")
    pg.click(f'.spk3-exam-card[data-test-id="01"] .spk3-chip[data-part="{part_num}"]')
    pg.wait_for_selector("#speakingViewExam.is-active")
    wait_for_mic_ready(pg)
    hold_to_speak(pg, "My name is Juan")
    wait_for_mic_ready(pg)
    hold_to_speak(pg, "I live in Buenos Aires")
    wait_for_mic_ready(pg)
    assert pg.evaluate("() => SPEAKING.phase") == f"part{part_num}"


def probe_canvas_variance(pg):
    """Read a 40x40 patch at the centre of the 3D canvas and compute pixel variance."""
    return pg.evaluate(
        """() => new Promise((resolve, reject) => {
            const c = document.querySelector('#speaking3dStage canvas');
            if (!c) return resolve({ ok: false, reason: 'no_canvas' });
            const url = c.toDataURL('image/png');
            const img = new Image();
            img.onload = () => {
                const off = document.createElement('canvas');
                off.width = img.width;
                off.height = img.height;
                const ctx = off.getContext('2d');
                ctx.drawImage(img, 0, 0);
                const size = 40;
                const sx = Math.max(0, Math.floor((off.width - size) / 2));
                const sy = Math.max(0, Math.floor((off.height - size) / 2));
                const sw = Math.min(size, off.width);
                const sh = Math.min(size, off.height);
                const data = ctx.getImageData(sx, sy, sw, sh).data;
                let sum = 0;
                let sumSq = 0;
                let n = 0;
                const uniq = new Set();
                for (let i = 0; i < data.length; i += 4) {
                    const lum = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
                    sum += lum;
                    sumSq += lum * lum;
                    n++;
                    uniq.add((data[i] << 16) | (data[i + 1] << 8) | data[i + 2]);
                }
                const mean = n ? sum / n : 0;
                const variance = n ? Math.max(0, (sumSq / n) - mean * mean) : 0;
                resolve({
                    ok: true,
                    width: c.width,
                    height: c.height,
                    patch: [sw, sh],
                    uniqueColors: uniq.size,
                    mean: Math.round(mean * 100) / 100,
                    variance: Math.round(variance * 100) / 100,
                });
            };
            img.onerror = () => reject(new Error('canvas_decode_failed'));
            img.src = url;
        })"""
    )


def measure_hud_and_stage(pg):
    """Inspect stage geometry, HUD boxes, materials-band clearance, hit targets, and overflow."""
    return pg.evaluate(
        """() => {
            const st = document.getElementById('speaking3dStage');
            const c = st ? st.querySelector('canvas') : null;
            const head = document.querySelector('#speakingViewExam .spk3-head');
            const panel = document.getElementById('speakingPanel');
            const mic = document.getElementById('speakingMicBtn');
            const sr = st.getBoundingClientRect();
            const cr = c ? c.getBoundingClientRect() : null;
            const hr = head.getBoundingClientRect();
            const pr = panel.getBoundingClientRect();
            const mr = mic.getBoundingClientRect();

            // Centre band (materials area): x 30%-70%, y 40%-70% of stage
            const band = {
                left: sr.left + sr.width * 0.30,
                right: sr.left + sr.width * 0.70,
                top: sr.top + sr.height * 0.40,
                bottom: sr.top + sr.height * 0.70,
            };
            const intersects = (r, b) =>
                r.width > 1 && r.height > 1 &&
                r.left < b.right && r.right > b.left &&
                r.top < b.bottom && r.bottom > b.top;

            const hudIds = [
                'speakingRoles', 'speakingPanelPart', 'speaking3dHint',
                'speakingMicBtn', 'speakingSkipBtn', 'speakingCheckingBox',
                'speakingTimer', 'speaking3dBtn', 'speakingCloseExamBtn'
            ];
            const hudOverlaps = [];
            for (const id of hudIds) {
                const el = document.getElementById(id);
                if (!el || el.hidden) continue;
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                const r = el.getBoundingClientRect();
                if (intersects(r, band)) {
                    hudOverlaps.push({
                        id,
                        rect: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)],
                        band: [Math.round(band.left), Math.round(band.top), Math.round(band.right), Math.round(band.bottom)],
                    });
                }
            }

            // Interactive button heights (>= 44px)
            const interactive = {};
            for (const id of ['speakingMicBtn', 'speaking3dBtn', 'speakingCloseExamBtn', 'speakingSkipBtn']) {
                const el = document.getElementById(id);
                if (!el) continue;
                const r = el.getBoundingClientRect();
                interactive[id] = {
                    exists: true,
                    hidden: el.hidden,
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                };
            }

            // Hit target at mic centre
            const mcx = mr.left + mr.width / 2;
            const mcy = mr.top + mr.height / 2;
            const hit = document.elementFromPoint(mcx, mcy);
            const micHitOk = Boolean(hit && (hit === mic || mic.contains(hit)));

            // Panel overlaps canvas (not a separate side column)
            const panelOverlapsCanvas = Boolean(
                cr &&
                pr.left < cr.right && pr.right > cr.left &&
                pr.top < cr.bottom && pr.bottom > cr.top
            );

            // Role pills geometry
            const roles = Array.from(document.querySelectorAll('#speakingRoles .spk3-role')).map(el => {
                const r = el.getBoundingClientRect();
                return {
                    role: el.dataset.role,
                    active: el.getAttribute('data-active') === 'true',
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                };
            });

            return {
                iw: window.innerWidth,
                ih: window.innerHeight,
                sw: document.documentElement.scrollWidth,
                headerH: Math.round(hr.height),
                stageW: Math.round(sr.width),
                stageH: Math.round(sr.height),
                canvasW: cr ? Math.round(cr.width) : 0,
                canvasH: cr ? Math.round(cr.height) : 0,
                canvasTouchAction: c ? c.style.touchAction : '',
                panelOverlapsCanvas,
                micW: Math.round(mr.width),
                micH: Math.round(mr.height),
                micInsideStage: (
                    mr.left >= sr.left - 1 && mr.right <= sr.right + 1 &&
                    mr.top >= sr.top - 1 && mr.bottom <= sr.bottom + 1
                ),
                micHitOk,
                hudOverlaps,
                interactive,
                roles,
                partGuideInDom: Boolean(document.getElementById('speakingPartGuide')),
            };
        }"""
    )


def assert_seats_and_figures(pg):
    stats = pg.evaluate("() => window.SPK3D.__debug.stats()")
    seats = pg.evaluate("() => window.SPK3D.__debug.seats()")
    assert stats and stats["figuresVisible"] == 4, f"Expected 4 visible figures: {stats}"
    assert seats and set(seats.keys()) == set(EXPECTED_SEATS.keys()), seats
    for role, exp in EXPECTED_SEATS.items():
        got = seats[role]
        for axis in range(3):
            assert abs(got[axis] - exp[axis]) <= 0.02, f"Seat {role} axis {axis}: got {got}, expected {exp}"
    assert abs(seats["assessor"][2] - seats["examiner"][2]) >= 0.55, seats
    return stats, seats


def measure_render_120_frames(pg):
    return pg.evaluate("() => window.SPK3D.__debug.bench(120)")


def main():
    base = isolated_server(extra_env={
        "B2_SPK_TEST_MODE": "1",
        "B2_OWNER_UIDS": OWNER_NAME,
    })
    url = base + "/"
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )

        # =====================================================================
        # 1. Classic mode (default) + WebGL support & pre-mount API check
        # =====================================================================
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        page_errors = []
        pg.on("pageerror", lambda e: page_errors.append(str(e)))

        pg.goto(url + "app", wait_until="networkidle")
        user = login_owner(pg, url)
        pg.evaluate("setLang('en')")
        pg.wait_for_timeout(200)

        api_check = pg.evaluate(
            """() => {
                const a = window.SPK3D;
                if (!a) return { present: false };
                const supported = !!a.supported();
                let threw = false;
                try {
                    a.setActiveRole('examiner');
                    a.setActiveRole('invalid_role');
                    a.setSpeaking('partner', null);
                    a.setPart(2);
                    a.setPart(99);
                    a.showImages(['a', 'b']);
                    a.showImages(null);
                    a.showCard('c');
                    a.showCard(null);
                    a.setReducedMotion(false);
                    a.unmount();
                } catch (e) {
                    threw = String(e);
                }
                return {
                    present: true,
                    supported,
                    version: a.version,
                    isMounted: a.isMounted(),
                    threw,
                    methods: [
                        'supported','mount','unmount','isMounted','setActiveRole',
                        'setSpeaking','setPart','showImages','showCard','setReducedMotion'
                    ].every(k => typeof a[k] === 'function'),
                };
            }"""
        )
        if not api_check.get("present") or not api_check.get("supported"):
            print("SKIP: no webgl")
            browser.close()
            return 0
        assert api_check["methods"] and api_check["version"] == "1" and not api_check["threw"], api_check
        assert not api_check["isMounted"], api_check

        enter_part(pg, 2)
        classic_state = pg.evaluate(
            """() => {
                const dk = document.getElementById('speakingDesk').getBoundingClientRect();
                const pn = document.getElementById('speakingPanel').getBoundingClientRect();
                return {
                    stageHidden: document.getElementById('speaking3dStage').hidden,
                    canvases: document.querySelectorAll('#speaking3dStage canvas').length,
                    photosHidden: document.getElementById('speakingPhotos').hidden,
                    btnHidden: document.getElementById('speaking3dBtn').hidden,
                    btnPressed: document.getElementById('speaking3dBtn').getAttribute('aria-pressed'),
                    btnLabel: document.getElementById('speaking3dBtn').textContent.trim(),
                    isMounted: window.SPK3D.isMounted(),
                    sideBySide: dk.right <= pn.left + 8 && Math.abs(dk.top - pn.top) < 120,
                    deskW: Math.round(dk.width),
                    panelW: Math.round(pn.width),
                };
            }"""
        )
        assert classic_state["stageHidden"] and classic_state["canvases"] == 0, classic_state
        assert not classic_state["photosHidden"], classic_state
        assert not classic_state["btnHidden"], classic_state
        assert classic_state["btnPressed"] == "false" and classic_state["btnLabel"] == "3D room", classic_state
        assert not classic_state["isMounted"], classic_state
        assert classic_state["sideBySide"], f"Classic mode not side-by-side: {classic_state}"
        assert page_errors == [], f"Classic page errors: {page_errors}"
        results["classic"] = classic_state
        ctx.close()

        # =====================================================================
        # 2. Desktop 1280x800, 3D on, Part 1: full-width, HUD, seats, look, mouth, gaze, perf
        # =====================================================================
        dctx = browser.new_context(viewport={"width": 1280, "height": 800})
        dpg = dctx.new_page()
        d_errors = []
        dpg.on("pageerror", lambda e: d_errors.append(str(e)))
        dpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        dpg.goto(url + "app?spk3d=1", wait_until="networkidle")
        dpg.wait_for_timeout(250)
        dpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        dpg.wait_for_timeout(150)

        enter_part(dpg, 1)
        dpg.wait_for_timeout(300)

        m1280 = measure_hud_and_stage(dpg)
        assert m1280["canvasW"] >= 0.96 * m1280["iw"], f"Canvas not full width: {m1280}"
        assert m1280["panelOverlapsCanvas"], f".spk3-panel still a separate column: {m1280}"
        assert m1280["micHitOk"], f"#speakingMicBtn is not hit target at its centre: {m1280}"
        assert m1280["sw"] <= m1280["iw"] + 1, f"Horizontal overflow at 1280: {m1280}"
        assert m1280["micH"] >= 56 and m1280["micInsideStage"], m1280
        assert m1280["hudOverlaps"] == [], f"HUD overlaps materials band at 1280: {m1280['hudOverlaps']}"
        assert m1280["canvasTouchAction"] == "none", m1280
        assert abs(m1280["stageH"] - max(420, m1280["ih"] - m1280["headerH"])) <= 5, m1280
        for bid in ("speakingMicBtn", "speaking3dBtn", "speakingCloseExamBtn"):
            assert m1280["interactive"][bid]["h"] >= 44, m1280["interactive"]

        stats1280, seats1280 = assert_seats_and_figures(dpg)
        probe = probe_canvas_variance(dpg)
        assert probe["ok"] and probe["variance"] > 0 and probe["uniqueColors"] > 1, probe

        # Keyboard Tab order: mic -> skip -> toggle -> close
        tab_info = dpg.evaluate(
            """() => {
                const ids = ['speakingMicBtn', 'speakingSkipBtn', 'speaking3dBtn', 'speakingCloseExamBtn'];
                return ids.map(id => {
                    const el = document.getElementById(id);
                    return { id, tabIndex: el ? el.tabIndex : null };
                });
            }"""
        )
        assert [x["tabIndex"] for x in tab_info] == [1, 2, 3, 4], tab_info

        full_1280_shot = os.path.join(OUT_DIR, "speaking3d_fullwidth_1280.png")
        dpg.screenshot(path=full_1280_shot)

        # 2b. Look-around: synthetic drag 120 px -> yaw 0.50 +- 0.06, clamp at 0.55, idle return
        stage_box = dpg.locator("#speaking3dStage").bounding_box()
        sx = stage_box["x"] + stage_box["width"] * 0.50
        sy = stage_box["y"] + stage_box["height"] * 0.50
        dpg.mouse.move(sx, sy)
        dpg.mouse.down()
        dpg.mouse.move(sx + 120, sy, steps=12)
        dpg.wait_for_timeout(80)
        look_120 = dpg.evaluate("() => window.SPK3D.__debug.look()")
        assert look_120["dragging"] is True, look_120
        assert abs(look_120["yaw"] - 0.50) <= 0.06, f"Expected yaw 0.50+-0.06 after 120px drag, got {look_120}"

        look_left_shot = os.path.join(OUT_DIR, "speaking3d_look_left_1280.png")
        dpg.screenshot(path=look_left_shot)

        # Drag further to verify clamp at 0.55
        dpg.mouse.move(sx + 260, sy, steps=10)
        dpg.wait_for_timeout(80)
        look_clamped = dpg.evaluate("() => window.SPK3D.__debug.look()")
        assert 0.54 <= look_clamped["yaw"] <= 0.551, f"Did not clamp at 0.55: {look_clamped}"
        dpg.mouse.up()
        was_drag = dpg.evaluate("() => document.querySelector('#speaking3dStage canvas').dataset.wasDrag")
        assert was_drag == "1", f"Drag >10px did not mark wasDrag: {was_drag}"

        # Wait idle 2.6 s -> return starts, then finish 600 ms return -> |yaw| < 0.03
        dpg.wait_for_timeout(2650)
        dpg.evaluate("() => new Promise(r => requestAnimationFrame(() => r()))")
        look_mid_return = dpg.evaluate("() => window.SPK3D.__debug.look()")
        assert look_mid_return["returning"] or abs(look_mid_return["yaw"]) < 0.03, look_mid_return
        dpg.wait_for_function(
            "() => { const l = window.SPK3D.__debug.look(); return Math.abs(l.yaw) < 0.03 && !l.returning; }",
            timeout=6000,
        )
        look_returned = dpg.evaluate("() => window.SPK3D.__debug.look()")
        assert abs(look_returned["yaw"]) < 0.03 and not look_returned["returning"], look_returned

        # 2c. Mouth-sync check with fake analyser
        dpg.evaluate(
            """() => {
                const fake = {
                    frequencyBinCount: 128,
                    getByteFrequencyData(a) { a.fill(180); }
                };
                window.SPK3D.setSpeaking('examiner', fake);
            }"""
        )
        dpg.wait_for_function(
            "() => window.SPK3D.__debug.state('examiner').mouthOpen > 1.0",
            timeout=8000,
        )
        mouth_open = dpg.evaluate("() => window.SPK3D.__debug.state('examiner')")
        assert mouth_open["mouthOpen"] > 1.0, mouth_open
        dpg.evaluate("() => window.SPK3D.setSpeaking(null, null)")
        dpg.wait_for_function(
            "() => window.SPK3D.__debug.state('examiner').mouthOpen < 0.6",
            timeout=8000,
        )
        mouth_closed = dpg.evaluate("() => window.SPK3D.__debug.state('examiner')")
        assert mouth_closed["mouthOpen"] < 0.6, mouth_closed

        # 2d. Gaze check (partner turns, assessor stays head-down)
        dpg.evaluate("() => window.SPK3D.setActiveRole('partner')")
        dpg.wait_for_function(
            "() => window.SPK3D.__debug.state('partner').headYaw < -0.95",
            timeout=8000,
        )
        p_on_p = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        a_on_p = dpg.evaluate("() => window.SPK3D.__debug.state('assessor')")
        dpg.evaluate("() => window.SPK3D.setActiveRole('examiner')")
        dpg.wait_for_function(
            "(prevYaw) => Math.abs(window.SPK3D.__debug.state('partner').headYaw - prevYaw) > 0.3",
            arg=p_on_p["headYaw"],
            timeout=8000,
        )
        p_on_e = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        a_on_e = dpg.evaluate("() => window.SPK3D.__debug.state('assessor')")
        dpg.wait_for_timeout(150)
        p_settled = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        assert abs(p_on_e["headYaw"] - p_on_p["headYaw"]) > 0.3, (p_on_p, p_on_e)
        assert abs(p_settled["headYaw"] - p_on_e["headYaw"]) < 0.08, (p_on_e, p_settled)
        assert a_on_p["headPitch"] < 0 and a_on_e["headPitch"] < 0, (a_on_p, a_on_e)
        assert abs(a_on_e["headYaw"] - a_on_p["headYaw"]) <= 0.05, (a_on_p, a_on_e)

        # 2e. 120-frame render performance benchmark (desktop tier)
        perf_desktop = measure_render_120_frames(dpg)
        assert perf_desktop["medianMs"] <= 12.0, f"Desktop render over 12ms budget: {perf_desktop}"

        # 2f. Toggle back to classic mid-session -> restores side-by-side layout, no canvas
        dpg.click("#speaking3dBtn")
        dpg.wait_for_timeout(200)
        after_toggle = dpg.evaluate(
            """() => {
                const dk = document.getElementById('speakingDesk').getBoundingClientRect();
                const pn = document.getElementById('speakingPanel').getBoundingClientRect();
                return {
                    stageHidden: document.getElementById('speaking3dStage').hidden,
                    canvasCount: document.querySelectorAll('#speaking3dStage canvas').length,
                    isMounted: window.SPK3D.isMounted(),
                    phase: SPEAKING.phase,
                    sideBySide: dk.right <= pn.left + 8 && Math.abs(dk.top - pn.top) < 120,
                    btnLabel: document.getElementById('speaking3dBtn').textContent.trim(),
                };
            }"""
        )
        assert after_toggle["stageHidden"] and after_toggle["canvasCount"] == 0, after_toggle
        assert not after_toggle["isMounted"] and after_toggle["phase"] == "part1", after_toggle
        assert after_toggle["sideBySide"] and after_toggle["btnLabel"] == "3D room", after_toggle
        assert d_errors == [], f"Desktop 1280 errors: {d_errors}"
        results["desktop_1280"] = {
            "hud": m1280,
            "stats": stats1280,
            "seats": seats1280,
            "look": {
                "after_120px": look_120,
                "clamped": look_clamped,
                "mid_return": look_mid_return,
                "returned": look_returned,
            },
            "perf": perf_desktop,
            "after_toggle": after_toggle,
        }
        dctx.close()

        # =====================================================================
        # 3. Desktop 1920x1080 full width
        # =====================================================================
        wctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        wpg = wctx.new_page()
        w_errors = []
        wpg.on("pageerror", lambda e: w_errors.append(str(e)))
        wpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        wpg.goto(url + "app?spk3d=1", wait_until="networkidle")
        wpg.wait_for_timeout(200)
        wpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        enter_part(wpg, 1)
        wpg.wait_for_timeout(250)
        m1920 = measure_hud_and_stage(wpg)
        stats1920, _ = assert_seats_and_figures(wpg)
        assert m1920["canvasW"] >= 0.96 * m1920["iw"], m1920
        assert m1920["sw"] <= m1920["iw"] + 1, m1920
        assert m1920["hudOverlaps"] == [], m1920["hudOverlaps"]
        assert m1920["micHitOk"] and m1920["micInsideStage"], m1920
        wpg.screenshot(path=os.path.join(OUT_DIR, "speaking3d_fullwidth_1920.png"))
        assert w_errors == [], f"Desktop 1920 errors: {w_errors}"
        results["desktop_1920"] = {"hud": m1920, "stats": stats1920}
        wctx.close()

        # 3b. Phone quality tier benchmark at 1280x800 full width (is_mobile + has_touch -> low tier)
        ptctx = browser.new_context(viewport={"width": 1280, "height": 800}, is_mobile=True, has_touch=True)
        ptpg = ptctx.new_page()
        ptpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        ptpg.goto(url + "app?spk3d=1", wait_until="networkidle")
        ptpg.wait_for_timeout(150)
        ptpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        enter_part(ptpg, 1)
        ptpg.wait_for_timeout(150)
        perf_phone_1280 = measure_render_120_frames(ptpg)
        assert perf_phone_1280["mobile"] and not perf_phone_1280["shadows"] and perf_phone_1280["dpr"] <= 1.5, perf_phone_1280
        assert perf_phone_1280["medianMs"] <= 22.0, f"Phone tier 1280 render over 22ms budget: {perf_phone_1280}"
        results["perf_phone_tier_1280"] = perf_phone_1280
        ptctx.close()

        # =====================================================================
        # 4. Phone portrait 390x844 (mobile tier + HUD + perf + screenshot)
        # =====================================================================
        mctx = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        mpg = mctx.new_page()
        m_errors = []
        mpg.on("pageerror", lambda e: m_errors.append(str(e)))
        mpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        mpg.goto(url + "app?spk3d=1", wait_until="networkidle")
        mpg.wait_for_timeout(200)
        mpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        enter_part(mpg, 1)
        mpg.wait_for_timeout(250)

        m390 = measure_hud_and_stage(mpg)
        stats390, _ = assert_seats_and_figures(mpg)
        expected_h_390 = min(m390["ih"] - m390["headerH"], m390["iw"] * 0.75)
        assert abs(m390["stageH"] - expected_h_390) <= 5, (m390["stageH"], expected_h_390)
        assert m390["micH"] >= 68 and m390["micInsideStage"] and m390["micHitOk"], m390
        assert m390["sw"] <= m390["iw"] + 1, m390
        assert m390["hudOverlaps"] == [], f"HUD overlaps materials band at 390x844: {m390['hudOverlaps']}"
        for bid in ("speakingMicBtn", "speaking3dBtn", "speakingCloseExamBtn"):
            assert m390["interactive"][bid]["h"] >= 44, m390["interactive"]
        assert m390["partGuideInDom"] and m390["interactive"]["speakingSkipBtn"]["exists"], m390
        assert stats390["mobile"] and not stats390["shadows"] and stats390["dpr"] <= 1.5, stats390

        perf_phone = measure_render_120_frames(mpg)
        assert perf_phone["medianMs"] <= 22.0, f"Phone render over 22ms budget: {perf_phone}"
        mpg.screenshot(path=os.path.join(OUT_DIR, "speaking3d_hud_phone_390.png"))
        assert m_errors == [], f"Phone 390 errors: {m_errors}"
        results["phone_390"] = {"hud": m390, "stats": stats390, "perf": perf_phone}
        mctx.close()

        # =====================================================================
        # 5. Phone landscape 844x390 (collapsed roles, full height - header)
        # =====================================================================
        lctx = browser.new_context(
            viewport={"width": 844, "height": 390},
            is_mobile=True,
            has_touch=True,
        )
        lpg = lctx.new_page()
        l_errors = []
        lpg.on("pageerror", lambda e: l_errors.append(str(e)))
        lpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        lpg.goto(url + "app?spk3d=1", wait_until="networkidle")
        lpg.wait_for_timeout(200)
        lpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        enter_part(lpg, 1)
        lpg.wait_for_timeout(250)

        m844 = measure_hud_and_stage(lpg)
        stats844, _ = assert_seats_and_figures(lpg)
        expected_h_844 = m844["ih"] - m844["headerH"]
        assert abs(m844["stageH"] - expected_h_844) <= 5, (m844["stageH"], expected_h_844)
        assert m844["micH"] >= 68 and m844["micInsideStage"] and m844["micHitOk"], m844
        assert m844["sw"] <= m844["iw"] + 1, m844
        assert m844["hudOverlaps"] == [], f"HUD overlaps materials band at 844x390: {m844['hudOverlaps']}"
        for bid in ("speakingMicBtn", "speaking3dBtn", "speakingCloseExamBtn"):
            assert m844["interactive"][bid]["h"] >= 44, m844["interactive"]
        # Landscape < 520px height collapses inactive role pills to dots
        inactive_roles = [r for r in m844["roles"] if not r["active"]]
        active_roles = [r for r in m844["roles"] if r["active"]]
        assert len(inactive_roles) == 2 and all(r["w"] <= 36 for r in inactive_roles), m844["roles"]
        assert len(active_roles) == 1 and active_roles[0]["w"] > 44, m844["roles"]

        lpg.screenshot(path=os.path.join(OUT_DIR, "speaking3d_hud_landscape_844.png"))
        assert l_errors == [], f"Landscape 844 errors: {l_errors}"
        results["phone_844_landscape"] = {"hud": m844, "stats": stats844}
        lctx.close()

        # =====================================================================
        # 6. Extra viewports: 360x640 phone & 768x1024 tablet
        # =====================================================================
        for label, vw, vh, is_mob in [("phone_360", 360, 640, True), ("tablet_768", 768, 1024, True)]:
            vctx = browser.new_context(
                viewport={"width": vw, "height": vh},
                is_mobile=is_mob,
                has_touch=is_mob,
            )
            vpg = vctx.new_page()
            v_errors = []
            vpg.on("pageerror", lambda e: v_errors.append(str(e)))
            vpg.add_init_script(
                "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
            )
            vpg.goto(url + "app?spk3d=1", wait_until="networkidle")
            vpg.wait_for_timeout(200)
            vpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
            enter_part(vpg, 1)
            vpg.wait_for_timeout(200)
            mv = measure_hud_and_stage(vpg)
            sv, _ = assert_seats_and_figures(vpg)
            exp_h = min(mv["ih"] - mv["headerH"], mv["iw"] * 0.75)
            assert abs(mv["stageH"] - exp_h) <= 5, (label, mv["stageH"], exp_h)
            assert mv["sw"] <= mv["iw"] + 1, (label, mv)
            assert mv["micH"] >= 68 and mv["micInsideStage"] and mv["micHitOk"], (label, mv)
            assert mv["hudOverlaps"] == [], (label, mv["hudOverlaps"])
            for bid in ("speakingMicBtn", "speaking3dBtn", "speakingCloseExamBtn"):
                assert mv["interactive"][bid]["h"] >= 44, (label, mv["interactive"])
            assert v_errors == [], f"{label} errors: {v_errors}"
            results[label] = {"hud": mv, "stats": sv}
            vctx.close()

        # =====================================================================
        # 7. ?spk3d=0 never mounts even if D.settings.spk3d is true
        # =====================================================================
        zctx = browser.new_context(viewport={"width": 1280, "height": 800})
        zpg = zctx.new_page()
        z_errors = []
        zpg.on("pageerror", lambda e: z_errors.append(str(e)))
        zpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        zpg.goto(url + "app?spk3d=0", wait_until="networkidle")
        zpg.wait_for_timeout(250)
        zpg.evaluate(
            """() => {
                if (typeof hideOnboarding === 'function') hideOnboarding();
                setLang('en');
                if (window.D && D.settings) D.settings.spk3d = true;
            }"""
        )
        enter_part(zpg, 2)
        z_state = zpg.evaluate(
            """() => ({
                stageHidden: document.getElementById('speaking3dStage').hidden,
                canvasCount: document.querySelectorAll('#speaking3dStage canvas').length,
                photosHidden: document.getElementById('speakingPhotos').hidden,
                isMounted: window.SPK3D.isMounted(),
            })"""
        )
        assert z_state["stageHidden"] and z_state["canvasCount"] == 0 and not z_state["isMounted"], z_state
        assert not z_state["photosHidden"], z_state
        assert z_errors == [], f"?spk3d=0 page errors: {z_errors}"
        results["force_off"] = z_state
        zctx.close()

        browser.close()

    print(json.dumps(results, indent=2))
    print("PASS test_speaking_3d_room")
    return 0


if __name__ == "__main__":
    sys.exit(main())
