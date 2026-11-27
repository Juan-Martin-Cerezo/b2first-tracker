#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playwright tests for Speaking 3D exam room (Phase SPK3D-1 & SPK3D-2).

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


def enter_part2(pg):
    pg.evaluate("openSpeakingExam()")
    pg.wait_for_selector("#speakingOverlay.is-open")
    pg.wait_for_selector("#speakingCatalogGrid .spk3-exam-card")
    pg.click('.spk3-exam-card[data-test-id="01"] .spk3-chip[data-part="2"]')
    pg.wait_for_selector("#speakingViewExam.is-active")
    wait_for_mic_ready(pg)
    hold_to_speak(pg, "My name is Juan")
    wait_for_mic_ready(pg)
    hold_to_speak(pg, "I live in Buenos Aires")
    wait_for_mic_ready(pg)
    assert pg.evaluate("() => SPEAKING.phase") == "part2"


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


def probe_bottom_left_partner_cloth(pg):
    """Sample bottom-left 10% of the 3D canvas and compute fraction matching partner clothing 0x6b7350."""
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
                const sw = Math.max(1, Math.floor(off.width * 0.10));
                const sh = Math.max(1, Math.floor(off.height * 0.10));
                const sy = Math.max(0, off.height - sh);
                const data = ctx.getImageData(0, sy, sw, sh).data;
                // Partner cloth base 0x6b7350 = (107, 115, 80); olive green (g >= r - 2, g - b >= 18)
                let total = 0;
                let matched = 0;
                for (let i = 0; i < data.length; i += 4) {
                    const r = data[i], g = data[i + 1], b = data[i + 2];
                    total++;
                    const direct = Math.abs(r - 107) <= 18 && Math.abs(g - 115) <= 18 && Math.abs(b - 80) <= 18 && (g - b) >= 18;
                    const shadedOlive = g >= 35 && g <= 165 && g >= r - 2 && r >= b + 12 && (g - b) >= 18;
                    if (direct || shadedOlive) matched++;
                }
                resolve({
                    ok: true,
                    box: [0, sy, sw, sh],
                    total,
                    matched,
                    ratio: total ? Math.round((matched / total) * 10000) / 10000 : 0,
                });
            };
            img.onerror = () => reject(new Error('canvas_decode_failed'));
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

        # 1. Classic mode (default) + WebGL support & pre-mount API check
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

        enter_part2(pg)
        classic_state = pg.evaluate(
            """() => ({
                stageHidden: document.getElementById('speaking3dStage').hidden,
                canvases: document.querySelectorAll('#speaking3dStage canvas').length,
                photosHidden: document.getElementById('speakingPhotos').hidden,
                btnHidden: document.getElementById('speaking3dBtn').hidden,
                btnPressed: document.getElementById('speaking3dBtn').getAttribute('aria-pressed'),
                btnLabel: document.getElementById('speaking3dBtn').textContent.trim(),
                isMounted: window.SPK3D.isMounted(),
            })"""
        )
        assert classic_state["stageHidden"], classic_state
        assert classic_state["canvases"] == 0, classic_state
        assert not classic_state["photosHidden"], classic_state
        assert not classic_state["btnHidden"], classic_state
        assert classic_state["btnPressed"] == "false" and classic_state["btnLabel"] == "3D room", classic_state
        assert not classic_state["isMounted"], classic_state
        assert page_errors == [], f"Classic page errors: {page_errors}"
        results["classic"] = classic_state
        ctx.close()

        # 2. Desktop ?spk3d=1 + pixel probe + screenshot + toggle back to classic
        dctx = browser.new_context(viewport={"width": 1280, "height": 800})
        dpg = dctx.new_page()
        d_errors = []
        dpg.on("pageerror", lambda e: d_errors.append(str(e)))
        dpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        dpg.goto(url + "app?spk3d=1", wait_until="networkidle")
        dpg.wait_for_timeout(300)
        dpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        dpg.wait_for_timeout(150)

        enter_part2(dpg)
        dpg.wait_for_timeout(300)

        desk3d = dpg.evaluate(
            """() => {
                const st = document.getElementById('speaking3dStage');
                const canvases = st.querySelectorAll('canvas');
                const c = canvases[0] || null;
                const gl = c ? (c.getContext('webgl2') || c.getContext('webgl')) : null;
                return {
                    stageHidden: st.hidden,
                    canvasCount: canvases.length,
                    canvasW: c ? c.width : 0,
                    canvasH: c ? c.height : 0,
                    hasGl: !!gl,
                    photosHidden: document.getElementById('speakingPhotos').hidden,
                    cardHidden: document.getElementById('speakingCardWrap').hidden,
                    convHidden: document.getElementById('speakingConvStage').hidden,
                    btnPressed: document.getElementById('speaking3dBtn').getAttribute('aria-pressed'),
                    btnLabel: document.getElementById('speaking3dBtn').textContent.trim(),
                    settingPersisted: !!(D && D.settings && D.settings.spk3d),
                    isMounted: window.SPK3D.isMounted(),
                };
            }"""
        )
        assert not desk3d["stageHidden"], desk3d
        assert desk3d["canvasCount"] == 1 and desk3d["canvasW"] > 0 and desk3d["canvasH"] > 0, desk3d
        assert desk3d["hasGl"] and desk3d["isMounted"], desk3d
        assert desk3d["photosHidden"] and desk3d["cardHidden"] and desk3d["convHidden"], desk3d
        assert desk3d["btnPressed"] == "true" and desk3d["btnLabel"] == "Classic view", desk3d
        assert not desk3d["settingPersisted"], f"?spk3d=1 must not persist to D.settings: {desk3d}"

        probe = probe_canvas_variance(dpg)
        assert probe["ok"] and probe["variance"] > 0 and probe["uniqueColors"] > 1, probe

        bl_probe = probe_bottom_left_partner_cloth(dpg)
        assert bl_probe["ok"] and bl_probe["ratio"] <= 0.08, f"Partner clipping bottom-left: {bl_probe}"

        desktop_shot = os.path.join(OUT_DIR, "speaking3d_desktop_1280.png")
        dpg.screenshot(path=desktop_shot)

        # 2b. Deterministic mouth-sync check with fake analyser (no real audio)
        dpg.evaluate(
            """() => {
                const fake = {
                    frequencyBinCount: 128,
                    getByteFrequencyData(a) { a.fill(180); }
                };
                window.SPK3D.setSpeaking('examiner', fake);
            }"""
        )
        dpg.wait_for_timeout(350)
        mouth_open_state = dpg.evaluate("() => window.SPK3D.__debug.state('examiner')")
        assert isinstance(mouth_open_state, dict), mouth_open_state
        assert all(isinstance(mouth_open_state[k], (int, float)) for k in ("mouthOpen", "headYaw", "headPitch")), mouth_open_state
        assert mouth_open_state["mouthOpen"] > 1.0, f"Examiner mouth did not open: {mouth_open_state}"

        mouth_shot = os.path.join(OUT_DIR, "speaking3d_mouth_open_1280.png")
        dpg.screenshot(path=mouth_shot)

        dpg.evaluate("() => window.SPK3D.setSpeaking(null, null)")
        dpg.wait_for_timeout(300)
        mouth_closed_state = dpg.evaluate("() => window.SPK3D.__debug.state('examiner')")
        assert mouth_closed_state["mouthOpen"] < 0.6, f"Examiner mouth did not close: {mouth_closed_state}"

        # 2c. Deterministic gaze & head turn check (partner turns, assessor stays head-down)
        dpg.evaluate("() => window.SPK3D.setActiveRole('partner')")
        dpg.wait_for_timeout(900)
        partner_on_partner = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        assessor_on_partner = dpg.evaluate("() => window.SPK3D.__debug.state('assessor')")
        gaze_shot = os.path.join(OUT_DIR, "speaking3d_gaze_partner_1280.png")
        dpg.screenshot(path=gaze_shot)

        dpg.evaluate("() => window.SPK3D.setActiveRole('examiner')")
        dpg.wait_for_timeout(900)
        partner_on_examiner = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")
        assessor_on_examiner = dpg.evaluate("() => window.SPK3D.__debug.state('assessor')")
        dpg.wait_for_timeout(150)
        partner_settled = dpg.evaluate("() => window.SPK3D.__debug.state('partner')")

        partner_yaw_delta = abs(partner_on_examiner["headYaw"] - partner_on_partner["headYaw"])
        partner_settle_drift = abs(partner_settled["headYaw"] - partner_on_examiner["headYaw"])
        assessor_yaw_delta = abs(assessor_on_examiner["headYaw"] - assessor_on_partner["headYaw"])
        assert partner_yaw_delta > 0.3, {
            "partner_on_partner": partner_on_partner,
            "partner_on_examiner": partner_on_examiner,
        }
        assert partner_settle_drift < 0.06, {
            "partner_on_examiner": partner_on_examiner,
            "partner_settled": partner_settled,
        }
        assert assessor_on_partner["headPitch"] < 0 and assessor_on_examiner["headPitch"] < 0, {
            "assessor_on_partner": assessor_on_partner,
            "assessor_on_examiner": assessor_on_examiner,
        }
        assert assessor_yaw_delta <= 0.05, {
            "assessor_on_partner": assessor_on_partner,
            "assessor_on_examiner": assessor_on_examiner,
        }

        # Toggle back to classic mid-session -> canvas removed, #speakingPhotos restored, exam preserved
        dpg.click("#speaking3dBtn")
        dpg.wait_for_timeout(200)
        after_toggle = dpg.evaluate(
            """() => ({
                stageHidden: document.getElementById('speaking3dStage').hidden,
                canvasCount: document.querySelectorAll('#speaking3dStage canvas').length,
                photosHidden: document.getElementById('speakingPhotos').hidden,
                phase: SPEAKING.phase,
                btnPressed: document.getElementById('speaking3dBtn').getAttribute('aria-pressed'),
                btnLabel: document.getElementById('speaking3dBtn').textContent.trim(),
                isMounted: window.SPK3D.isMounted(),
            })"""
        )
        assert after_toggle["stageHidden"] and after_toggle["canvasCount"] == 0, after_toggle
        assert not after_toggle["isMounted"], after_toggle
        assert not after_toggle["photosHidden"], after_toggle
        assert after_toggle["phase"] == "part2", after_toggle
        assert after_toggle["btnPressed"] == "false" and after_toggle["btnLabel"] == "3D room", after_toggle
        assert d_errors == [], f"Desktop 3D page errors: {d_errors}"
        results["desktop_3d"] = {
            "state": desk3d,
            "probe": probe,
            "bottom_left": bl_probe,
            "mouth_open": mouth_open_state,
            "mouth_closed": mouth_closed_state,
            "gaze": {
                "partner_on_partner": partner_on_partner,
                "partner_on_examiner": partner_on_examiner,
                "partner_settled": partner_settled,
                "assessor_on_partner": assessor_on_partner,
                "assessor_on_examiner": assessor_on_examiner,
            },
            "after_toggle": after_toggle,
        }
        dctx.close()

        # 3. Mobile 390x844 ?spk3d=1 + no horizontal overflow + screenshot
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
        mpg.wait_for_timeout(300)
        mpg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding(); setLang('en');")
        mpg.wait_for_timeout(150)

        enter_part2(mpg)
        mpg.wait_for_timeout(300)

        mob3d = mpg.evaluate(
            """() => {
                const st = document.getElementById('speaking3dStage');
                const c = st.querySelector('canvas');
                const sr = st.getBoundingClientRect();
                const dr = document.querySelector('#speakingViewExam .spk3-dock').getBoundingClientRect();
                return {
                    stageHidden: st.hidden,
                    canvasCount: st.querySelectorAll('canvas').length,
                    canvasW: c ? c.width : 0,
                    canvasH: c ? c.height : 0,
                    sw: document.documentElement.scrollWidth,
                    iw: window.innerWidth,
                    stageW: Math.round(sr.width),
                    stageH: Math.round(sr.height),
                    aspect: sr.height ? Math.round((sr.width / sr.height) * 100) / 100 : 0,
                    stageBottom: Math.round(sr.bottom),
                    dockTop: Math.round(dr.top),
                };
            }"""
        )
        assert not mob3d["stageHidden"] and mob3d["canvasCount"] == 1 and mob3d["canvasW"] > 0, mob3d
        assert mob3d["sw"] <= mob3d["iw"] + 1, f"Mobile horizontal overflow: {mob3d}"
        assert mob3d["stageBottom"] <= mob3d["dockTop"] + 2, f"Stage overlaps dock: {mob3d}"
        assert 1.2 <= mob3d["aspect"] <= 1.7, f"Unexpected mobile aspect: {mob3d}"

        m_probe = probe_canvas_variance(mpg)
        assert m_probe["ok"] and m_probe["variance"] > 0, m_probe

        mobile_shot = os.path.join(OUT_DIR, "speaking3d_mobile_390.png")
        mpg.screenshot(path=mobile_shot)
        assert m_errors == [], f"Mobile 3D page errors: {m_errors}"
        results["mobile_3d"] = {"state": mob3d, "probe": m_probe}
        mctx.close()

        # 4. ?spk3d=0 never mounts even if D.settings.spk3d is true
        zctx = browser.new_context(viewport={"width": 1280, "height": 800})
        zpg = zctx.new_page()
        z_errors = []
        zpg.on("pageerror", lambda e: z_errors.append(str(e)))
        zpg.add_init_script(
            "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
        )
        zpg.goto(url + "app?spk3d=0", wait_until="networkidle")
        zpg.wait_for_timeout(300)
        zpg.evaluate(
            """() => {
                if (typeof hideOnboarding === 'function') hideOnboarding();
                setLang('en');
                if (window.D && D.settings) D.settings.spk3d = true;
            }"""
        )
        enter_part2(zpg)
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
