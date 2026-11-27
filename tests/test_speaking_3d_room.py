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
    "partner": [-0.80, 0.46, 0.64],
    "examiner": [0.18, 0.46, -0.86],
    "assessor": [-0.72, 0.46, -1.46],
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


def enter_part(pg, part_num, test_id="01"):
    pg.evaluate("openSpeakingExam()")
    pg.wait_for_selector("#speakingOverlay.is-open")
    pg.wait_for_selector("#speakingCatalogGrid .spk3-exam-card")
    if part_num == 3:
        pg.evaluate("() => { SPEAKING._prepStepMs = 35; }")
    pg.click(f'.spk3-exam-card[data-test-id="{test_id}"] .spk3-chip[data-part="{part_num}"]')
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


def check_material_hud_clearance(pg):
    """Assert visible 3D card/photo projected boxes never intersect mic, timer or role pills."""
    return pg.evaluate(
        """() => {
            const bounds = window.SPK3D.__debug.materialBounds();
            const rects = [];
            if (bounds && Array.isArray(bounds.photos)) {
                bounds.photos.forEach((b, i) => { if (b) rects.push({ name: 'photo' + (i + 1), rect: b }); });
            }
            if (bounds && bounds.card) {
                rects.push({ name: 'card', rect: bounds.card });
            }
            const hudEls = [
                { id: 'speakingMicBtn', el: document.getElementById('speakingMicBtn') },
                { id: 'speakingTimer', el: document.getElementById('speakingTimer') },
                { id: 'speakingRoles', el: document.getElementById('speakingRoles') },
            ];
            document.querySelectorAll('#speakingRoles .spk3-role').forEach((el, idx) => {
                hudEls.push({ id: 'role_' + idx, el });
            });
            const intersects = (a, b) =>
                a.width > 1 && a.height > 1 && b.width > 1 && b.height > 1 &&
                a.left < b.right && a.right > b.left &&
                a.top < b.bottom && a.bottom > b.top;
            const overlaps = [];
            for (const m of rects) {
                for (const h of hudEls) {
                    if (!h.el || h.el.hidden) continue;
                    const cs = getComputedStyle(h.el);
                    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                    const hr = h.el.getBoundingClientRect();
                    if (intersects(m.rect, hr)) {
                        overlaps.push({
                            material: m.name,
                            materialRect: m.rect,
                            hud: h.id,
                            hudRect: {
                                left: Math.round(hr.left),
                                top: Math.round(hr.top),
                                right: Math.round(hr.right),
                                bottom: Math.round(hr.bottom),
                            },
                        });
                    }
                }
            }
            return { materials: rects, overlaps };
        }"""
    )


def probe_material_color_buckets(pg):
    """Sample rendered pixels inside the projected 3D photo card boxes and count distinct colour buckets."""
    return pg.evaluate(
        """() => new Promise((resolve, reject) => {
            const c = document.querySelector('#speaking3dStage canvas');
            const bounds = window.SPK3D.__debug.materialBounds();
            if (!c || !bounds || !bounds.photos || bounds.photos.length < 2) {
                return resolve({ ok: false, reason: 'no_photos' });
            }
            const cr = c.getBoundingClientRect();
            const url = c.toDataURL('image/png');
            const img = new Image();
            img.onload = () => {
                const off = document.createElement('canvas');
                off.width = img.width;
                off.height = img.height;
                const ctx = off.getContext('2d');
                ctx.drawImage(img, 0, 0);
                const sx = img.width / cr.width;
                const sy = img.height / cr.height;
                const allBuckets = new Set();
                const perCard = [];
                let chromaticPixels = 0;
                let totalPixels = 0;
                for (const b of bounds.photos) {
                    const padX = b.width * 0.12;
                    const padY = b.height * 0.12;
                    const x0 = Math.max(0, Math.floor((b.left + padX - cr.left) * sx));
                    const y0 = Math.max(0, Math.floor((b.top + padY - cr.top) * sy));
                    const x1 = Math.min(off.width, Math.ceil((b.right - padX - cr.left) * sx));
                    const y1 = Math.min(off.height, Math.ceil((b.bottom - padY - cr.top) * sy));
                    const w = Math.max(1, x1 - x0);
                    const h = Math.max(1, y1 - y0);
                    const data = ctx.getImageData(x0, y0, w, h).data;
                    const cardBuckets = new Set();
                    for (let i = 0; i < data.length; i += 16) {
                        const r = data[i], g = data[i + 1], bl = data[i + 2];
                        const key = ((r >> 5) << 6) | ((g >> 5) << 3) | (bl >> 5);
                        cardBuckets.add(key);
                        allBuckets.add(key);
                        if (Math.max(r, g, bl) - Math.min(r, g, bl) >= 16) chromaticPixels++;
                        totalPixels++;
                    }
                    perCard.push({ buckets: cardBuckets.size, w, h });
                }
                resolve({
                    ok: true,
                    totalBuckets: allBuckets.size,
                    chromaticPixels,
                    totalPixels,
                    perCard,
                });
            };
            img.onerror = () => reject(new Error('decode_failed'));
            img.src = url;
        })"""
    )


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
                    a.setCast({partner:{sex:'invalid'}, examiner:{sex:'male'}});
                    a.setCast({partner:'male'});
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
                        'setSpeaking','setPart','showImages','showCard','setCast','setReducedMotion'
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

        # 2b. Look-around: asymmetric clamp [-1.25, +0.65], right drag, left drag (-260px toward partner), idle return
        stage_box = dpg.locator("#speaking3dStage").bounding_box()
        sx = stage_box["x"] + stage_box["width"] * 0.50
        sy = stage_box["y"] + stage_box["height"] * 0.50
        look_init = dpg.evaluate("() => window.SPK3D.__debug.look()")
        assert abs(look_init["yawMin"] - (-1.25)) < 1e-6 and abs(look_init["yawMax"] - 0.65) < 1e-6, look_init

        dpg.mouse.move(sx, sy)
        dpg.mouse.down()
        dpg.mouse.move(sx + 120, sy, steps=12)
        dpg.wait_for_timeout(80)
        look_120 = dpg.evaluate("() => window.SPK3D.__debug.look()")
        assert look_120["dragging"] is True, look_120
        assert abs(look_120["yaw"] - 0.50) <= 0.06, f"Expected yaw 0.50+-0.06 after 120px drag, got {look_120}"

        # Drag further right to verify upper clamp at +0.65
        dpg.mouse.move(sx + 260, sy, steps=10)
        dpg.wait_for_timeout(80)
        look_clamped = dpg.evaluate("() => window.SPK3D.__debug.look()")
        assert 0.64 <= look_clamped["yaw"] <= 0.651, f"Did not clamp at +0.65: {look_clamped}"
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

        # Synthetic drag -260 px (left, toward partner) -> yaw <= -1.20 rad, partner fully in view
        dpg.mouse.move(sx, sy)
        dpg.mouse.down()
        dpg.mouse.move(sx - 260, sy, steps=14)
        dpg.wait_for_timeout(120)
        look_partner = dpg.evaluate("() => window.SPK3D.__debug.look()")
        assert look_partner["yaw"] <= -1.20 and look_partner["yaw"] >= -1.251, f"Expected yaw <= -1.20 on -260px drag, got {look_partner}"
        look_partner_shot = os.path.join(OUT_DIR, "speaking3d_look_partner_1280.png")
        dpg.screenshot(path=look_partner_shot)
        look_left_shot = os.path.join(OUT_DIR, "speaking3d_look_left_1280.png")
        dpg.screenshot(path=look_left_shot)
        dpg.mouse.up()
        dpg.wait_for_function(
            "() => { const l = window.SPK3D.__debug.look(); return Math.abs(l.yaw) < 0.03 && !l.returning; }",
            timeout=6000,
        )

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

        # 2d. Gaze check: all four speaker transitions (>= 0.15 rad change, settle < 1 s),
        # setSpeaking authoritative over setActiveRole, assessor stays head-down.
        def wait_gaze(check_js, arg=None):
            t0 = dpg.evaluate("() => performance.now()")
            dpg.wait_for_function(check_js, arg=arg, timeout=1000)
            elapsed_ms = dpg.evaluate("(t) => performance.now() - t", arg=t0)
            assert elapsed_ms < 1000, f"Gaze transition took {elapsed_ms}ms (>= 1s)"
            return elapsed_ms

        # Baseline: candidate speaks ('you') -> examiner & partner both look at camera
        dpg.evaluate("() => { window.SPK3D.setSpeaking(null, null); window.SPK3D.setActiveRole('you'); }")
        dpg.wait_for_function(
            "() => Math.abs(window.SPK3D.__debug.state('examiner').headYaw) < 0.12 && window.SPK3D.__debug.state('partner').headYaw < -0.90",
            timeout=2000,
        )
        g_you_e = dpg.evaluate("() => window.SPK3D.__debug.state('examiner')")
        g_you_p = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        g_you_a = dpg.evaluate("() => window.SPK3D.__debug.state('assessor')")
        assert abs(g_you_e["headYaw"]) < 0.12, g_you_e
        assert g_you_p["headYaw"] < -0.90, g_you_p

        # Transition 1: you -> examiner (partner turns from camera to examiner >= 0.15 rad, settles < 1 s)
        dpg.evaluate("() => window.SPK3D.setActiveRole('examiner')")
        t1_ms = wait_gaze(
            "(prev) => window.SPK3D.__debug.state('partner').headYaw > -0.25 && Math.abs(window.SPK3D.__debug.state('partner').headYaw - prev) >= 0.15",
            arg=g_you_p["headYaw"],
        )
        g_ex_p = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        g_ex_e = dpg.evaluate("() => window.SPK3D.__debug.state('examiner')")
        assert abs(g_ex_p["headYaw"] - g_you_p["headYaw"]) >= 0.15, (g_you_p, g_ex_p)
        assert abs(g_ex_e["headYaw"]) < 0.12, g_ex_e

        # Transition 2: examiner -> partner via setSpeaking (authoritative over activeRole='examiner')
        dpg.evaluate(
            """() => {
                const fake = { frequencyBinCount: 64, getByteFrequencyData(a) { a.fill(140); } };
                window.SPK3D.setSpeaking('partner', fake);
            }"""
        )
        t2_ms = wait_gaze(
            "([pe, pp]) => window.SPK3D.__debug.state('examiner').headYaw < -0.35 && window.SPK3D.__debug.state('partner').headYaw < -0.80 && Math.abs(window.SPK3D.__debug.state('examiner').headYaw - pe) >= 0.15 && Math.abs(window.SPK3D.__debug.state('partner').headYaw - pp) >= 0.15",
            arg=[g_ex_e["headYaw"], g_ex_p["headYaw"]],
        )
        g_pa_e = dpg.evaluate("() => window.SPK3D.__debug.state('examiner')")
        g_pa_p = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        assert abs(g_pa_e["headYaw"] - g_ex_e["headYaw"]) >= 0.15, (g_ex_e, g_pa_e)
        assert abs(g_pa_p["headYaw"] - g_ex_p["headYaw"]) >= 0.15, (g_ex_p, g_pa_p)

        # Transition 3: partner -> you (examiner turns back to camera >= 0.15 rad, settles < 1 s)
        dpg.evaluate("() => { window.SPK3D.setSpeaking(null, null); window.SPK3D.setActiveRole('you'); }")
        t3_ms = wait_gaze(
            "(prev) => Math.abs(window.SPK3D.__debug.state('examiner').headYaw) < 0.15 && Math.abs(window.SPK3D.__debug.state('examiner').headYaw - prev) >= 0.15",
            arg=g_pa_e["headYaw"],
        )
        g_you2_e = dpg.evaluate("() => window.SPK3D.__debug.state('examiner')")
        assert abs(g_you2_e["headYaw"] - g_pa_e["headYaw"]) >= 0.15, (g_pa_e, g_you2_e)

        # Transition 4: you -> examiner via setSpeaking overriding activeRole='you'
        dpg.evaluate(
            """() => {
                const fake = { frequencyBinCount: 64, getByteFrequencyData(a) { a.fill(140); } };
                window.SPK3D.setSpeaking('examiner', fake);
            }"""
        )
        t4_ms = wait_gaze(
            "(prev) => window.SPK3D.__debug.state('partner').headYaw > -0.25 && Math.abs(window.SPK3D.__debug.state('partner').headYaw - prev) >= 0.15",
            arg=g_pa_p["headYaw"],
        )
        g_ex2_p = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        g_ex2_a = dpg.evaluate("() => window.SPK3D.__debug.state('assessor')")
        assert abs(g_ex2_p["headYaw"] - g_pa_p["headYaw"]) >= 0.15, (g_pa_p, g_ex2_p)
        assert g_you_a["headPitch"] < 0 and g_ex2_a["headPitch"] < 0, (g_you_a, g_ex2_a)
        assert abs(g_ex2_a["headYaw"] - g_you_a["headYaw"]) <= 0.05, (g_you_a, g_ex2_a)
        dpg.evaluate("() => window.SPK3D.setSpeaking(null, null)")
        results["gaze_transitions_ms"] = [round(t1_ms, 1), round(t2_ms, 1), round(t3_ms, 1), round(t4_ms, 1)]

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

        # =====================================================================
        # 8. SPK3D-4: Part 2 photos, dolly, colour buckets, HUD clearance, lightbox & perf (1280x800)
        # =====================================================================
        p2ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        p2pg = p2ctx.new_page()
        p2_errors = []
        p2pg.on("pageerror", lambda e: p2_errors.append(str(e)))
        p2pg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        p2pg.goto(url + "app?spk3d=1", wait_until="networkidle")
        p2pg.wait_for_timeout(200)
        p2pg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        enter_part(p2pg, 2)

        p2pg.wait_for_function(
            """() => {
                const pr = window.SPK3D.__debug.props();
                return pr && pr.photos === 2 && pr.card === 0 && pr.texturesReady === true;
            }""",
            timeout=6000,
        )
        p2pg.wait_for_function(
            """() => {
                const c = window.SPK3D.__debug.camera();
                return c && c.moving === false && Math.abs(c.fov - 46) <= 1.0;
            }""",
            timeout=2500,
        )
        p2_props = p2pg.evaluate("() => window.SPK3D.__debug.props()")
        p2_cam = p2pg.evaluate("() => window.SPK3D.__debug.camera()")
        p2_dom_visible = p2pg.evaluate(
            """() => ({
                photosHidden: document.getElementById('speakingPhotos').hidden,
                hintHidden: document.getElementById('speaking3dHint').hidden,
                hintAriaLive: document.getElementById('speaking3dHint').getAttribute('aria-live'),
                hintText: document.getElementById('speaking3dHint').textContent.trim(),
            })"""
        )
        assert p2_props["photos"] == 2 and p2_props["card"] == 0 and p2_props["texturesReady"], p2_props
        assert p2_props["textureCount"] <= 4, p2_props
        assert abs(p2_cam["fov"] - 46.0) <= 1.0 and p2_cam["moving"] is False, p2_cam
        assert not p2_dom_visible["photosHidden"], f"2D photos DOM must stay unhidden under stage: {p2_dom_visible}"
        assert not p2_dom_visible["hintHidden"] and p2_dom_visible["hintAriaLive"] == "polite", p2_dom_visible

        p2_hud = check_material_hud_clearance(p2pg)
        assert p2_hud["overlaps"] == [], f"Part 2 HUD overlap at 1280x800: {p2_hud}"

        p2_colors = probe_material_color_buckets(p2pg)
        assert p2_colors["ok"] and p2_colors["totalBuckets"] >= 6, f"Photo area lacks real colour buckets: {p2_colors}"
        assert p2_colors["chromaticPixels"] > 20, f"Photo area looks grey: {p2_colors}"

        part2_shot = os.path.join(OUT_DIR, "speaking3d_part2_1280.png")
        p2pg.screenshot(path=part2_shot)

        # Performance with photo texture loaded (desktop)
        perf_desktop_photo = measure_render_120_frames(p2pg)
        assert perf_desktop_photo["medianMs"] <= 16.0, f"Desktop photo render too slow: {perf_desktop_photo}"

        # Tap first photo card -> lightbox opens, render loop pauses, backdrop click closes
        photo1_rect = p2_hud["materials"][0]["rect"]
        p2pg.mouse.click(
            photo1_rect["left"] + photo1_rect["width"] / 2,
            photo1_rect["top"] + photo1_rect["height"] / 2,
        )
        p2pg.wait_for_function("() => !document.getElementById('speaking3dLightbox').hidden", timeout=3000)
        lb_p2 = p2pg.evaluate(
            """() => ({
                hidden: document.getElementById('speaking3dLightbox').hidden,
                activeId: document.activeElement ? document.activeElement.id : '',
                closeH: Math.round(document.getElementById('speaking3dLightboxClose').getBoundingClientRect().height),
                dbg: window.SPK3D.__debug.lightbox(),
            })"""
        )
        assert not lb_p2["hidden"] and lb_p2["activeId"] == "speaking3dLightboxClose", lb_p2
        assert lb_p2["closeH"] >= 44 and lb_p2["dbg"]["open"] and lb_p2["dbg"]["paused"], lb_p2
        # Backdrop click closes and returns focus to canvas
        p2pg.mouse.click(12, 12)
        p2pg.wait_for_function("() => document.getElementById('speaking3dLightbox').hidden", timeout=3000)
        p2_after_close = p2pg.evaluate(
            "() => ({ activeTag: document.activeElement ? document.activeElement.tagName : '' })"
        )
        assert p2_after_close["activeTag"] == "CANVAS", p2_after_close

        assert p2_errors == [], f"Part 2 desktop errors: {p2_errors}"
        results["part2_1280"] = {
            "props": p2_props,
            "camera": p2_cam,
            "colors": p2_colors,
            "hudOverlaps": p2_hud["overlaps"],
            "perfWithPhoto": perf_desktop_photo,
        }
        p2ctx.close()

        # =====================================================================
        # 9. SPK3D-4: Part 3 task card, dolly, HUD clearance, tap centre -> lightbox -> Escape (1280x800)
        # =====================================================================
        p3ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        p3pg = p3ctx.new_page()
        p3_errors = []
        p3pg.on("pageerror", lambda e: p3_errors.append(str(e)))
        p3pg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        p3pg.goto(url + "app?spk3d=1", wait_until="networkidle")
        p3pg.wait_for_timeout(200)
        p3pg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        enter_part(p3pg, 3)

        p3pg.wait_for_function(
            """() => {
                const pr = window.SPK3D.__debug.props();
                return pr && pr.photos === 0 && pr.card === 1 && pr.texturesReady === true;
            }""",
            timeout=6000,
        )
        p3pg.wait_for_function(
            """() => {
                const c = window.SPK3D.__debug.camera();
                return c && c.moving === false && Math.abs(c.fov - 44) <= 1.0;
            }""",
            timeout=2500,
        )
        p3_props = p3pg.evaluate("() => window.SPK3D.__debug.props()")
        p3_cam = p3pg.evaluate("() => window.SPK3D.__debug.camera()")
        assert p3_props["photos"] == 0 and p3_props["card"] == 1 and p3_props["texturesReady"], p3_props
        assert abs(p3_cam["fov"] - 44.0) <= 1.0 and p3_cam["moving"] is False, p3_cam

        p3_hud = check_material_hud_clearance(p3pg)
        assert p3_hud["overlaps"] == [], f"Part 3 HUD overlap at 1280x800: {p3_hud}"

        part3_shot = os.path.join(OUT_DIR, "speaking3d_part3_1280.png")
        p3pg.screenshot(path=part3_shot)

        # Tap centre of canvas -> lightbox opens, mic state untouched, Escape closes
        mic_before = p3pg.evaluate(
            """() => {
                const b = document.getElementById('speakingMicBtn');
                return { disabled: b.disabled, state: b.getAttribute('data-mic-state') };
            }"""
        )
        cbox = p3pg.locator("#speaking3dStage canvas").bounding_box()
        p3pg.mouse.click(cbox["x"] + cbox["width"] / 2, cbox["y"] + cbox["height"] / 2)
        p3pg.wait_for_function("() => !document.getElementById('speaking3dLightbox').hidden", timeout=3000)
        mic_open = p3pg.evaluate(
            """() => {
                const b = document.getElementById('speakingMicBtn');
                const img = document.getElementById('speaking3dLightboxImg');
                return {
                    disabled: b.disabled,
                    state: b.getAttribute('data-mic-state'),
                    imgReady: Boolean(img && img.complete && img.naturalWidth > 0),
                    activeId: document.activeElement ? document.activeElement.id : '',
                    dbg: window.SPK3D.__debug.lightbox(),
                };
            }"""
        )
        assert mic_open["disabled"] == mic_before["disabled"] and mic_open["state"] == mic_before["state"], (mic_before, mic_open)
        assert mic_open["imgReady"] and mic_open["activeId"] == "speaking3dLightboxClose", mic_open
        assert mic_open["dbg"]["open"] and mic_open["dbg"]["paused"], mic_open

        p3pg.keyboard.press("Escape")
        p3pg.wait_for_function("() => document.getElementById('speaking3dLightbox').hidden", timeout=3000)
        mic_after = p3pg.evaluate(
            """() => {
                const b = document.getElementById('speakingMicBtn');
                return {
                    disabled: b.disabled,
                    state: b.getAttribute('data-mic-state'),
                    activeTag: document.activeElement ? document.activeElement.tagName : '',
                };
            }"""
        )
        assert mic_after["disabled"] == mic_before["disabled"] and mic_after["state"] == mic_before["state"], (mic_before, mic_after)
        assert mic_after["activeTag"] == "CANVAS", mic_after

        assert p3_errors == [], f"Part 3 desktop errors: {p3_errors}"
        results["part3_1280"] = {
            "props": p3_props,
            "camera": p3_cam,
            "hudOverlaps": p3_hud["overlaps"],
            "micUnchanged": True,
        }
        p3ctx.close()

        # =====================================================================
        # 10. SPK3D-4: Phone 390x844 Part 2 & Part 3 HUD safety, thumbs, lightbox & photo perf
        # =====================================================================
        mpctx = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        mppg = mpctx.new_page()
        mp_errors = []
        mppg.on("pageerror", lambda e: mp_errors.append(str(e)))
        mppg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        mppg.goto(url + "app?spk3d=1", wait_until="networkidle")
        mppg.wait_for_timeout(200)
        mppg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        enter_part(mppg, 2)

        mppg.wait_for_function(
            """() => {
                const pr = window.SPK3D.__debug.props();
                const c = window.SPK3D.__debug.camera();
                return pr && pr.photos === 2 && pr.texturesReady && c && !c.moving && Math.abs(c.fov - 46) <= 1.0;
            }""",
            timeout=5000,
        )
        mp2_hud = check_material_hud_clearance(mppg)
        assert mp2_hud["overlaps"] == [], f"Part 2 HUD overlap at 390x844: {mp2_hud}"
        mp2_thumbs = mppg.evaluate(
            """() => {
                const strip = document.querySelector('#speaking3dStage .spk3d-thumbs');
                const btns = Array.from(document.querySelectorAll('#speaking3dStage .spk3d-thumb-btn'));
                return {
                    stripHidden: !strip || strip.hidden,
                    stripH: strip ? Math.round(strip.getBoundingClientRect().height) : 0,
                    btnCount: btns.length,
                    btnHeights: btns.map(b => Math.round(b.getBoundingClientRect().height)),
                };
            }"""
        )
        assert not mp2_thumbs["stripHidden"] and mp2_thumbs["stripH"] == 64, mp2_thumbs
        assert mp2_thumbs["btnCount"] == 2 and all(h >= 44 for h in mp2_thumbs["btnHeights"]), mp2_thumbs

        perf_phone_photo = measure_render_120_frames(mppg)
        assert perf_phone_photo["medianMs"] <= 24.0, f"Phone photo render too slow: {perf_phone_photo}"
        mp2_props = mppg.evaluate("() => window.SPK3D.__debug.props()")

        # Now test Part 3 on phone 390x844 + readable lightbox screenshot
        mppg.click("#speakingCloseExamBtn")
        mppg.wait_for_timeout(150)
        enter_part(mppg, 3)
        mppg.wait_for_function(
            """() => {
                const pr = window.SPK3D.__debug.props();
                const c = window.SPK3D.__debug.camera();
                return pr && pr.card === 1 && pr.texturesReady && c && !c.moving && Math.abs(c.fov - 44) <= 1.0;
            }""",
            timeout=5000,
        )
        mp3_hud = check_material_hud_clearance(mppg)
        assert mp3_hud["overlaps"] == [], f"Part 3 HUD overlap at 390x844: {mp3_hud}"
        mp3_thumbs = mppg.evaluate(
            """() => {
                const btns = Array.from(document.querySelectorAll('#speaking3dStage .spk3d-thumb-btn'));
                return { count: btns.length, heights: btns.map(b => Math.round(b.getBoundingClientRect().height)) };
            }"""
        )
        assert mp3_thumbs["count"] == 1 and mp3_thumbs["heights"][0] >= 44, mp3_thumbs

        mic_m_before = mppg.evaluate(
            "() => ({ disabled: document.getElementById('speakingMicBtn').disabled, state: document.getElementById('speakingMicBtn').getAttribute('data-mic-state') })"
        )
        mcbox = mppg.locator("#speaking3dStage canvas").bounding_box()
        mppg.mouse.click(mcbox["x"] + mcbox["width"] / 2, mcbox["y"] + mcbox["height"] / 2)
        mppg.wait_for_function("() => !document.getElementById('speaking3dLightbox').hidden", timeout=3000)
        mppg.wait_for_timeout(150)
        lb_390 = mppg.evaluate(
            """() => {
                const img = document.getElementById('speaking3dLightboxImg');
                const cls = document.getElementById('speaking3dLightboxClose');
                const mic = document.getElementById('speakingMicBtn');
                const ir = img.getBoundingClientRect();
                const cr = cls.getBoundingClientRect();
                return {
                    imgW: Math.round(ir.width),
                    imgH: Math.round(ir.height),
                    naturalW: img.naturalWidth,
                    closeH: Math.round(cr.height),
                    micDisabled: mic.disabled,
                    micState: mic.getAttribute('data-mic-state'),
                };
            }"""
        )
        assert lb_390["naturalW"] > 0 and lb_390["imgW"] >= 300, f"Task card too small in 390px lightbox: {lb_390}"
        assert lb_390["closeH"] >= 44, lb_390
        assert lb_390["micDisabled"] == mic_m_before["disabled"] and lb_390["micState"] == mic_m_before["state"], lb_390

        lb_390_shot = os.path.join(OUT_DIR, "speaking3d_lightbox_390.png")
        mppg.screenshot(path=lb_390_shot)

        mppg.keyboard.press("Escape")
        mppg.wait_for_function("() => document.getElementById('speaking3dLightbox').hidden", timeout=3000)
        assert mp_errors == [], f"Phone Part 2/3 errors: {mp_errors}"
        results["phone_390_materials"] = {
            "part2Props": mp2_props,
            "part2HudOverlaps": mp2_hud["overlaps"],
            "part2Thumbs": mp2_thumbs,
            "perfWithPhoto": perf_phone_photo,
            "part3HudOverlaps": mp3_hud["overlaps"],
            "part3Thumbs": mp3_thumbs,
            "lightbox390": lb_390,
        }
        mpctx.close()

        # =====================================================================
        # 11. SPK3D-4: Reduced motion emulation -> dolly skipped, material lifted & visible
        # =====================================================================
        rmctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            reduced_motion="reduce",
        )
        rmpg = rmctx.new_page()
        rm_errors = []
        rmpg.on("pageerror", lambda e: rm_errors.append(str(e)))
        rmpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        rmpg.goto(url + "app?spk3d=1", wait_until="networkidle")
        rmpg.wait_for_timeout(200)
        rmpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        enter_part(rmpg, 2)

        rmpg.wait_for_function(
            """() => {
                const pr = window.SPK3D.__debug.props();
                return pr && pr.photos === 2 && pr.texturesReady === true;
            }""",
            timeout=6000,
        )
        # Wait past dolly wait+ease window to ensure dolly never triggers
        rmpg.wait_for_timeout(1200)
        rm_state = rmpg.evaluate(
            """() => ({
                cam: window.SPK3D.__debug.camera(),
                props: window.SPK3D.__debug.props(),
                bounds: window.SPK3D.__debug.materialBounds(),
            })"""
        )
        assert rm_state["cam"]["moving"] is False, rm_state
        assert abs(rm_state["cam"]["fov"] - 58.0) <= 0.5, f"Dolly should be skipped in reduced motion: {rm_state}"
        assert abs(rm_state["cam"]["z"] - 0.94) <= 0.02, f"Camera moved in reduced motion: {rm_state}"
        assert rm_state["props"]["liftM"] >= 0.08, f"Material did not lift 0.10m in reduced motion: {rm_state}"
        assert len(rm_state["bounds"]["photos"]) == 2 and rm_state["bounds"]["photos"][0]["width"] > 40, rm_state
        assert rm_errors == [], f"Reduced motion errors: {rm_errors}"
        results["reduced_motion"] = rm_state
        rmctx.close()

        # =====================================================================
        # 12. SPK3D-5: Gender-aware cast from paper data + synthetic setCast + screenshots
        # =====================================================================
        gctx = browser.new_context(viewport={"width": 1280, "height": 800})
        gpg = gctx.new_page()
        g_errors = []
        gpg.on("pageerror", lambda e: g_errors.append(str(e)))
        gpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        gpg.goto(url + "app?spk3d=1", wait_until="networkidle")
        gpg.wait_for_timeout(200)
        gpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")

        # Verify __debug.cast() matches all four papers (01/03 -> male, 02/04 -> female)
        cast_by_paper = {}
        expected_sex = {"01": "male", "02": "female", "03": "male", "04": "female"}
        for pid in ("01", "02", "03", "04"):
            enter_part(gpg, 1, test_id=pid)
            gpg.wait_for_timeout(150)
            c = gpg.evaluate("() => window.SPK3D.__debug.cast()")
            assert c["partner"]["sex"] == expected_sex[pid], (pid, c)
            assert c["examiner"]["sex"] == "male", (pid, c)
            if expected_sex[pid] == "female":
                assert c["visibleSexes"] == ["male", "female"], (pid, c)
            else:
                assert c["visibleSexes"] == ["male"], (pid, c)
            cast_by_paper[pid] = c

            if pid == "01":
                # Synthetic setCast({partner:{sex:'female'}}) flips only partner meshes
                before_m = gpg.evaluate("() => window.SPK3D.__debug.stats().meshes")
                gpg.evaluate("() => window.SPK3D.setCast({partner:{sex:'female'}})")
                gpg.wait_for_timeout(100)
                after_m = gpg.evaluate("() => window.SPK3D.__debug.stats().meshes")
                after_c = gpg.evaluate("() => window.SPK3D.__debug.cast()")
                assert after_c["partner"]["sex"] == "female" and after_c["examiner"]["sex"] == "male", after_c
                assert after_m["partner"] != before_m["partner"], (before_m, after_m)
                assert 0 < (after_m["partner"] - before_m["partner"]) <= 2, (before_m, after_m)
                assert after_m["examiner"] == before_m["examiner"], (before_m, after_m)
                assert after_m["assessor"] == before_m["assessor"], (before_m, after_m)
                assert after_m["you"] == before_m["you"], (before_m, after_m)
                # Invalid sex normalises to male without throwing
                gpg.evaluate("() => window.SPK3D.setCast({partner:{sex:'not_a_sex'}})")
                gpg.wait_for_timeout(80)
                reset_c = gpg.evaluate("() => window.SPK3D.__debug.cast()")
                assert reset_c["partner"]["sex"] == "male", reset_c
                results["cast_mesh_delta"] = {"before": before_m, "after": after_m}

            if pid == "02":
                # Drag left (-260 px) to frame female partner Sophie for screenshot
                gbox = gpg.locator("#speaking3dStage").bounding_box()
                gsx = gbox["x"] + gbox["width"] * 0.50
                gsy = gbox["y"] + gbox["height"] * 0.50
                gpg.evaluate("() => window.SPK3D.setActiveRole('you')")
                gpg.wait_for_timeout(350)
                gpg.mouse.move(gsx, gsy)
                gpg.mouse.down()
                gpg.mouse.move(gsx - 260, gsy, steps=14)
                gpg.wait_for_timeout(120)
                gpg.screenshot(path=os.path.join(OUT_DIR, "speaking3d_female_partner_1280.png"))
                gpg.mouse.up()
                gpg.wait_for_function(
                    "() => { const l = window.SPK3D.__debug.look(); return Math.abs(l.yaw) < 0.03 && !l.returning; }",
                    timeout=6000,
                )

                # Toggle 3D off and back on mid-exam -> remounts and preserves female partner cast
                gpg.click("#speaking3dBtn")
                gpg.wait_for_function("() => !window.SPK3D.isMounted()", timeout=4000)
                gpg.wait_for_timeout(350)
                gpg.click("#speaking3dBtn")
                gpg.wait_for_function("() => window.SPK3D.isMounted()", timeout=6000)
                c_remount = gpg.evaluate("() => window.SPK3D.__debug.cast()")
                assert c_remount["partner"]["sex"] == "female", c_remount

                # Force examiner female via setCast for screenshot
                gpg.evaluate("() => window.SPK3D.setCast({examiner:{name:'Ms Clarke', sex:'female'}})")
                gpg.wait_for_timeout(180)
                c_fem_ex = gpg.evaluate("() => window.SPK3D.__debug.cast()")
                assert c_fem_ex["examiner"]["sex"] == "female" and c_fem_ex["visibleSexes"] == ["female"], c_fem_ex
                gpg.screenshot(path=os.path.join(OUT_DIR, "speaking3d_female_examiner_1280.png"))

            gpg.click("#speakingCloseExamBtn")
            gpg.wait_for_timeout(120)

        assert g_errors == [], f"Gender cast test errors: {g_errors}"
        results["cast_by_paper"] = cast_by_paper
        gctx.close()

        browser.close()

    print(json.dumps(results, indent=2))
    print("PASS test_speaking_3d_room")
    return 0


if __name__ == "__main__":
    sys.exit(main())
