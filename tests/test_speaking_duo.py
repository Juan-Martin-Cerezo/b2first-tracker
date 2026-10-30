"""S4 acceptance: examiner + partner live at the same time, one director.

Two simulated Live sessions hear the same candidate, the pure director decides
whose turn it is, and one AudioContext mixes two independent gain chains. No
Google key and no model: `?spk=sim` replaces both sockets with the fixed scripts,
so every assertion is on our side of the boundary.

    cd tests && uv run --with playwright python test_speaking_duo.py
"""
import json
import os
import sys
import tempfile
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server as S  # noqa: E402
import store  # noqa: E402
from helpers import OWNER_NAME, login_owner  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2spkduo-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.migrate_legacy()

BASE = {}


def start_server():
    srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    BASE["url"] = f"http://127.0.0.1:{port}"
    BASE["srv"] = srv
    return srv


def wait_until(pg, expression, timeout_s, step=100):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pg.evaluate(expression):
            return True
        pg.wait_for_timeout(step)
    return False


def main():
    os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "20"
    out = {}
    srv = start_server()
    S._RATE.clear()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright missing: cd tests && uv run --with playwright "
                         "python test_speaking_duo.py")

    page_errors, console_errors = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
        ])
        ctx = b.new_context()
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.on("console", lambda m: console_errors.append(m.text)
              if m.type == "error" else None)

        pg.goto(BASE["url"] + "/?spk=sim", wait_until="networkidle")
        login_owner(pg, BASE["url"] + "/")
        pg.evaluate("showView('hoy');selectSessionStudio('fri-b')")

        # 1. Part 3 opens both sessions (and only two).
        pg.evaluate("SPK.setPart(3)")
        assert pg.evaluate("SPK.part") == 3, "setPart did not stick"
        pg.click("#spkOpenBtn")
        assert wait_until(pg, "SPK.running===true && SPK.activeVoices===2", 20), \
            "the duo session did not start"
        assert pg.evaluate("!!SPK.voices.examiner.transport && "
                           "!!SPK.voices.partner.transport"), \
            "one of the two transports is missing"
        assert pg.evaluate("SPK.mode") == "sim", pg.evaluate("SPK.mode")
        out["1_two_sessions"] = pg.evaluate(
            "({voices: Object.keys(SPK.voices), active: SPK.activeVoices})")

        # 2. Both voices produce audio: examiner introduces, partner drives.
        assert wait_until(pg, "SPK.voices.examiner.speaking===true", 20), \
            "the examiner never spoke"
        assert wait_until(pg, "SPK.voices.partner.speaking===true", 25), \
            "the partner never spoke"
        assert wait_until(pg, "SPK.lines.some(l => l.who === 'partner')", 10), \
            "no partner transcript line"
        out["2_both_voices"] = pg.evaluate(
            "({ex: SPK.turns.filter(t=>t.who==='examiner').length, "
            "pa: SPK.turns.filter(t=>t.who==='partner').length})")

        # 3. The examiner's words reach the partner as text (sendText bridge).
        assert wait_until(pg, "SPK.voices.partner.transport.sent.some("
                              "s => s.indexOf('The examiner said:')===0)", 10), \
            "the partner never received the examiner transcript"
        out["3_text_bridge"] = pg.evaluate("SPK.voices.partner.transport.sent.length")

        # 4. Part 3 overlap is allowed and measured, and the panel shows it.
        #    NOTE: a forced 900 ms overlap cannot fully register — the director
        #    legitimately hands the floor to the partner ~180 ms after the
        #    examiner stops, which mutes the examiner. So we assert (a) overlap
        #    IS measured and painted, and (b) it STOPS growing while the
        #    examiner is muted. Asserting >= 300 ms would have been asserting
        #    the director does not do its job.
        pg.evaluate("SPK.simOverlap(900)")
        assert wait_until(pg, "SPK.overlapMs > 0", 15), \
            "overlap was not measured"
        # The panel is repainted once per director tick and renders one decimal,
        # so it can lag or legitimately read 0.0s for a sub-50 ms overlap. Assert
        # consistency with the measured value instead of a fixed string.
        assert wait_until(
            pg,
            "document.getElementById('spkOverlap').textContent === "
            "(SPK.overlapMs/1000).toFixed(1)+'s'", 10), \
            "the overlap panel does not match the measured overlap"
        pg.evaluate("SPK.simOverlap(900)")
        assert wait_until(pg, "SPK.overlapMs >= 120", 15), \
            f"overlap stayed tiny: {pg.evaluate('SPK.overlapMs')}"
        assert wait_until(pg, "SPK.dir.phase==='partner' && "
                              "SPK.voices.examiner.muted===true", 10), \
            "the examiner was never muted after the handoff"
        ov_a = pg.evaluate("SPK.overlapMs")
        pg.wait_for_timeout(700)
        ov_b = pg.evaluate("SPK.overlapMs")
        assert ov_b <= ov_a + 30, \
            f"overlap kept growing with the examiner muted: {ov_a} -> {ov_b}"
        out["4_overlap"] = pg.evaluate(
            "({ms: SPK.overlapMs, panel: document.getElementById('spkOverlap')"
            ".textContent})")

        # 5. One indicator per voice, with the documented states.
        states = pg.evaluate("({ex: document.getElementById('spkSpeaking').textContent,"
                             " pa: document.getElementById('spkPartnerVoice').textContent})")
        allowed = {"speaking", "muted", "offline", "live"}
        assert states["ex"] in allowed, states
        assert states["pa"] in allowed, states
        out["5_voice_panel"] = states

        # 6. Minutes bill both sessions: the ledger sums the two voices.
        elapsed = pg.evaluate("SPK.elapsed")
        pg.evaluate("spkStop()")
        assert wait_until(pg, "SPK.running===false && SPK.lastCtx.state==='closed'", 15), \
            "the duo session did not stop cleanly"
        billed = pg.evaluate("SPK.billedSeconds")
        assert billed >= max(1.0, elapsed * 1.8), \
            f"billed {billed}s for {elapsed}s of wall time: not both sessions"
        ledger = store.speaking_read(OWNER_NAME, S._spk_today())
        assert ledger["seconds"] > 0, ledger
        assert pg.evaluate("!SPK.voices.examiner.transport && "
                           "!SPK.voices.partner.transport"), \
            "a transport stayed open after stop"
        out["6_billing"] = {"wall_s": round(elapsed, 2), "billed_s": round(billed, 2),
                            "ledger_s": ledger["seconds"]}

        # 7. Killing the partner mid-session leaves the examiner running.
        pg.evaluate("spkDiscard()")
        pg.evaluate("spkStart()")
        assert wait_until(pg, "SPK.running===true && SPK.activeVoices===2", 20), \
            "the second session did not start"
        pg.evaluate("SPK.killVoice('partner')")
        assert wait_until(
            pg,
            "document.getElementById('spkPartnerVoice').textContent==='offline'", 10), \
            "the partner badge did not go offline"
        assert pg.evaluate("SPK.running===true"), "a dead partner killed the session"
        assert pg.evaluate("!!SPK.voices.examiner.transport"), \
            "the examiner transport died with the partner"
        pg.evaluate("SPK.simOverlap(600)")
        assert wait_until(pg, "SPK.voices.examiner.speaking===true", 10), \
            "the examiner stopped producing audio after the partner died"
        out["7_partner_offline"] = pg.evaluate(
            "({badge: document.getElementById('spkPartnerVoice').textContent, "
            "running: SPK.running})")
        pg.evaluate("spkStop()")
        assert wait_until(pg, "SPK.running===false && SPK.lastCtx.state==='closed'", 15), \
            "the degraded session did not close cleanly"

        # 8. Three open/close cycles: no AudioContext leak, one per session.
        pg.evaluate("spkDiscard()")
        opens = pg.evaluate("SPK.ctxOpens")
        for _ in range(3):
            pg.evaluate("spkStart()")
            assert wait_until(pg, "SPK.running===true", 15), "restart failed"
            pg.evaluate("spkStop()")
            assert wait_until(pg, "SPK.lastCtx!==null && SPK.lastCtx.state==='closed'",
                              10), "AudioContext stayed open across restarts"
        assert pg.evaluate("SPK.ctxOpens") == opens + 3, \
            f"expected 3 contexts, got {pg.evaluate('SPK.ctxOpens') - opens}"
        out["8_ctx_cycles"] = {"opens": pg.evaluate("SPK.ctxOpens") - opens,
                               "last": pg.evaluate("SPK.lastCtx.state")}

        # 9. Zero page or console errors in the whole run.
        assert not page_errors, f"page errors: {page_errors}"
        assert not console_errors, f"console errors: {console_errors}"
        out["9_no_console_errors"] = True

        b.close()

    srv.shutdown()
    srv.server_close()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("OK: S4 duo acceptance passed")


if __name__ == "__main__":
    main()
