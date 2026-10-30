"""S1 acceptance: microphone -> AudioWorklet VAD -> live HUD.

Runs the real index.html in Chromium with a fake microphone. The fixture is a
90 s WAV generated here with wave+math (no binary fixtures in the repo): band
noise + tone as "speech", separated by pauses of known duration (1.2 s, 2.5 s
and 4.4 s) plus 280 ms breaths that must NOT be recorded as silences.

    cd tests && uv run --with playwright python test_speaking_metrics.py
"""
import json
import math
import os
import random
import re
import tempfile
import time
import wave

from playwright.sync_api import sync_playwright

from helpers import login_owner

URL = "http://127.0.0.1:8088/"
RATE = 16000
DURATION = 90.0
KNOWN_PAUSES = [1.2, 2.5, 4.4]
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_segments():
    """Fixed timeline. The first 500 ms are pure silence (VAD calibration)."""
    segs = []

    def add(kind, dur):
        segs.append((kind, round(dur, 4)))

    add("sil", 0.6)            # 0.0-0.5 s calibrates noiseFloor; 0.5-0.6 is a sub-300 ms gap
    add("speech", 5.0)
    add("sil", 1.2)            # pause #1
    add("speech", 4.0)
    add("sil", 0.28)           # breath: must stay out of the silence list
    add("speech", 3.0)
    add("sil", 2.5)            # pause #2
    add("speech", 5.0)
    add("sil", 0.28)
    add("speech", 3.0)
    add("sil", 0.28)
    add("speech", 4.0)
    add("sil", 4.4)            # pause #3 (longest)
    add("speech", 5.0)

    used = sum(d for _, d in segs)
    n_gaps = 60
    block = (DURATION - used - n_gaps * 0.28) / (n_gaps + 1)
    for i in range(n_gaps + 1):
        add("speech", block)
        if i < n_gaps:
            add("sil", 0.28)
    assert abs(sum(d for _, d in segs) - DURATION) < 1e-2, sum(d for _, d in segs)
    return segs


def write_wav(path):
    rng = random.Random(7)
    segs = build_segments()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        offset = 0.0
        for kind, dur in segs:
            n = int(round(dur * RATE))
            buf = bytearray()
            for i in range(n):
                t = (offset + i) / RATE
                if kind == "speech":
                    v = (0.12 * math.sin(2 * math.pi * 220 * t)
                         + 0.06 * math.sin(2 * math.pi * 440 * t)
                         + 0.035 * math.sin(2 * math.pi * 880 * t)
                         + 0.02 * rng.uniform(-1.0, 1.0))
                else:
                    v = 0.0005 * rng.uniform(-1.0, 1.0)
                v = max(-1.0, min(1.0, v))
                buf += int(v * 32767).to_bytes(2, "little", signed=True)
            w.writeframes(bytes(buf))
            offset += dur
    return segs


def wait_until(pg, expression, timeout_s):
    """CSP forbids eval, so poll with evaluate() instead of wait_for_function()."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pg.evaluate(expression):
            return True
        pg.wait_for_timeout(100)
    return False


def main():
    out = {}
    wav_path = os.path.join(tempfile.mkdtemp(prefix="b2spk-"), "90s.wav")
    segs = write_wav(wav_path)
    out["fixture_seconds"] = round(sum(d for _, d in segs), 2)

    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--use-fake-device-for-media-stream",
            "--use-file-for-fake-audio-capture=%s%%noloop" % wav_path,
            "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
        ])
        ctx = b.new_context(permissions=["microphone"])
        pg = ctx.new_page()
        page_errors = []
        console_errors = []
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        pg.goto(URL, wait_until="networkidle")
        login_owner(pg, URL)

        # Open the speaking studio (Today view) and start the live panel.
        pg.evaluate("showView('hoy');selectSessionStudio('fri-b')")
        pg.click("#liveOpenBtn")
        out["panel_visible"] = pg.evaluate(
            "getComputedStyle(document.getElementById('livePanel')).display !== 'none'")
        assert wait_until(pg, "!!(window.LIVE && LIVE.running === true)", 20), "capture did not start"
        out["sample_rate"] = pg.evaluate("LIVE.sampleRate")
        out["status"] = pg.evaluate("document.getElementById('liveStatus').textContent")

        # The WAV runs in real time: wait for the full 90 s of frames.
        assert wait_until(pg, "LIVE.frames >= 4500", 130), "capture stalled before 90 s"

        # HUD paint cost over 60 frames (performance.now), while audio is live.
        out["hud_worst_ms"] = round(pg.evaluate(
            "() => { let worst = 0; for (let i = 0; i < 60; i++) {"
            " const t0 = performance.now(); LIVE.renderHud();"
            " const dt = performance.now() - t0; if (dt > worst) worst = dt; }"
            " return worst; }"), 3)

        pg.evaluate("liveStop()")
        pg.wait_for_timeout(300)

        state = pg.evaluate("""() => ({
            silences: LIVE.silences.map(s => ({start: s.start, dur: s.dur})),
            alerts: LIVE.alerts.map(a => a.kind),
            ratio: LIVE.ratio,
            longest: LIVE.longest,
            segments: LIVE.segments.length,
            timeline_divs: document.getElementById('liveTimeline').children.length,
            list_items: document.querySelectorAll('#liveList .live-pause').length,
            alert_text: document.getElementById('liveAlert').textContent,
            frozen: LIVE.frozen,
            saved_entries: D.log.length
        })""")
        out.update(state)
        out["page_errors"] = page_errors
        out["console_errors"] = console_errors
        b.close()

    # ---- assertions (S1 acceptance) --------------------------------------
    print(json.dumps(out, ensure_ascii=False, indent=1))
    durs = sorted(s["dur"] for s in out["silences"])

    assert out["panel_visible"], "live panel did not open"
    assert not out["page_errors"], "page errors: %s" % out["page_errors"]
    assert not out["console_errors"], "console errors: %s" % out["console_errors"]

    assert len(durs) == 3, "detected %d silences, expected 3: %s" % (len(durs), durs)
    for got, exp in zip(durs, KNOWN_PAUSES):
        assert abs(got - exp) <= 0.25, "pause %.2fs vs expected %.1fs" % (got, exp)
    assert abs(max(durs) - 4.4) <= 0.25, "longest pause %.2fs" % max(durs)
    assert all(d >= 0.3 for d in durs), "sub-300 ms silence leaked into the list: %s" % durs

    assert "long" in out["alerts"], "missing long-pause alert: %s" % out["alerts"]
    assert "frozen" in out["alerts"], "missing frozen alert: %s" % out["alerts"]
    assert "Long pause" in out["alert_text"] or "Frozen" in out["alert_text"], out["alert_text"]

    assert 45 <= out["ratio"] <= 85, "speech ratio %s%%" % out["ratio"]
    assert out["hud_worst_ms"] < 16.0, "HUD frame %.2f ms >= 16 ms" % out["hud_worst_ms"]
    assert out["timeline_divs"] >= 2, "timeline is empty"
    assert out["list_items"] == 3, "pause list has %d chips" % out["list_items"]
    assert out["frozen"] is True, "stop did not freeze the HUD"
    assert out["saved_entries"] == 0, "S1 must not save anything yet"

    html = open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
    assert not re.search(r"<script[^>]+src=", html), "external script added"
    assert "cdn." not in html and "unpkg" not in html, "external CDN reference found"
    assert not os.path.exists(os.path.join(REPO, "package.json")), "package.json appeared"

    print("OK: S1 acceptance passed")


if __name__ == "__main__":
    main()
