"""Listening own material (audio upload + written task/key/script).

Covers:
1. Paste written task + answer key + script, save via UI, reload: material
   persists and is listed; Check answers runs locally (no network call) and
   saveL records ref = material title without altering log shape.
2. Upload a small generated WAV (<1 s) via UI, save, fetch audio over HTTP:
   200, audio/wav Content-Type, Accept-Ranges: bytes, private/no-store
   Cache-Control, identical bytes, plus 206 Range seek support.
3. Delete via UI: removed from list and audio endpoint returns 404.
4. Limits: audio >20 MB -> 413; 11th material -> 429; invalid part -> 400.
5. Cross-user isolation: another user cannot fetch the owner's audio (404)
   and unauthenticated requests get 401.
6. Mobile UI 390x844 (light and dark, EN and ES, plus speechSynthesis absent):
   panel visible, controls >=44px, zero horizontal overflow, zero pageerrors.
"""
import base64
import io
import json
import math
import os
import struct
import tempfile
import wave

import httpx
from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
USER_A = ("listen-own-a", "listen-own-pass-9")
USER_B = ("listen-own-b", "listen-own-pass-9")


def make_tiny_wav(duration_s=0.15, sample_rate=8000, freq=440.0):
    """Generate a valid <1 s mono 16-bit PCM WAV in memory."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = int(12000 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return buf.getvalue()


def api_headers(token):
    return {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "X-Requested-With": "b2first",
    }


def open_listening_own(pg):
    pg.evaluate("openPlanUnit({skill:'l', value:2, min:10})")
    pg.wait_for_timeout(200)
    pg.select_option("#lFuente", "own")
    pg.wait_for_timeout(350)


def main():
    out = {}
    wav_bytes = make_tiny_wav()
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.write(wav_bytes)
    tmp_wav.close()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()

            # ------------------------------------------------------------------
            # 1, 2, 3: Desktop UI flows (task+key+script, WAV upload, delete)
            # ------------------------------------------------------------------
            pg = browser.new_page(viewport={"width": 1280, "height": 900})
            page_errors, console_errors = [], []
            pg.on("pageerror", lambda e: page_errors.append(str(e)))
            pg.on(
                "console",
                lambda m: console_errors.append(m.text)
                if m.type == "error" and "Failed to load resource" not in m.text
                else None,
            )

            pg.goto(URL + "app", wait_until="networkidle")
            u_a = login_user(pg, URL, USER_A[0], USER_A[1])
            tok_a = u_a["token"]
            pg.evaluate("setLang('en')")
            pg.wait_for_timeout(250)

            open_listening_own(pg)
            assert pg.is_visible("#lOwnPanel"), "#lOwnPanel did not open"

            # 1. Paste task + key + script, save, reload: persists and lists.
            pg.select_option("#lPart", "4")
            pg.fill("#lOwnTitle", "Podcast Interview Practice")
            pg.fill(
                "#lOwnTask",
                "Why did Mia move abroad? A) Work B) Study C) Family\n"
                "What surprised her most? A) Food B) Weather C) Transport",
            )
            pg.fill("#lOwnKey", "B\nC")
            pg.fill("#lOwnScript", "Hello everyone, today I am talking to Mia about her move.")
            pg.click("#lOwnSaveBtn")
            pg.wait_for_timeout(450)

            assert "Podcast Interview Practice" in pg.inner_text("#lOwnList"), (
                f"saved text material not in list: {pg.inner_text('#lOwnList')}"
            )
            assert "Material saved." in pg.inner_text("#lOwnStatus"), pg.inner_text("#lOwnStatus")

            # Reload and re-open own material: must still be listed.
            pg.reload(wait_until="networkidle")
            pg.wait_for_timeout(350)
            pg.evaluate("setLang('en')")
            pg.wait_for_timeout(200)
            open_listening_own(pg)
            assert "Podcast Interview Practice" in pg.inner_text("#lOwnList"), (
                "material disappeared after reload"
            )
            assert pg.inner_text("#lOwnSessionTitle").strip() == "Podcast Interview Practice"

            # Check answers runs strictly locally (zero network calls) and computes score.
            net_hits = []
            pg.on("request", lambda req: net_hits.append(req.url))
            ans_inputs = pg.locator("#lOwnQuestions .l-own-ans")
            assert ans_inputs.count() == 2, f"expected 2 answer inputs, got {ans_inputs.count()}"
            ans_inputs.nth(0).fill("b")
            ans_inputs.nth(1).fill("A")
            net_before = len(net_hits)
            pg.click("#lOwnCheckBtn")
            pg.wait_for_timeout(150)
            assert len(net_hits) == net_before, f"Check answers sent network requests: {net_hits[net_before:]}"
            assert "1/2" in pg.inner_text("#lOwnCheckResult"), pg.inner_text("#lOwnCheckResult")

            # saveL uses the own material title as ref and #lPart as part.
            assert pg.input_value("#lRef") == "Podcast Interview Practice"
            pg.click("button[data-action='saveL']")
            pg.wait_for_timeout(200)
            last_log = pg.evaluate("D.log[D.log.length - 1]")
            assert last_log["book"] == "own", f"unexpected book: {last_log}"
            assert last_log["ref"] == "Podcast Interview Practice", f"unexpected ref: {last_log}"
            assert last_log["part"] == 4, f"unexpected part: {last_log}"
            out["1_text_persist_and_check"] = {
                "score": pg.inner_text("#lOwnCheckResult"),
                "log_ref": last_log["ref"],
                "log_part": last_log["part"],
            }

            # 2. Upload tiny WAV via UI, save, fetch audio over HTTP.
            open_listening_own(pg)
            pg.select_option("#lPart", "2")
            pg.fill("#lOwnTitle", "My WAV Clip")
            pg.fill("#lOwnTask", "Listen and note the station name.")
            pg.set_input_files("#lOwnAudio", tmp_wav.name)
            pg.wait_for_timeout(150)
            pg.click("#lOwnSaveBtn")
            pg.wait_for_timeout(500)

            assert "My WAV Clip" in pg.inner_text("#lOwnList"), pg.inner_text("#lOwnList")
            audio_src = pg.get_attribute("#lOwnPlayer", "src") or ""
            assert audio_src.startswith("/api/listening/material/audio?id="), (
                f"unexpected <audio> src: {audio_src!r}"
            )
            wav_id = audio_src.split("id=", 1)[1]

            with httpx.Client(base_url=URL, timeout=15.0) as client:
                # Full GET with Bearer auth
                r_audio = client.get(
                    f"api/listening/material/audio?id={wav_id}",
                    headers={"Authorization": "Bearer " + tok_a},
                )
                assert r_audio.status_code == 200, f"audio GET status {r_audio.status_code}"
                assert r_audio.headers.get("content-type", "").startswith("audio/"), (
                    f"bad content-type: {r_audio.headers.get('content-type')}"
                )
                assert r_audio.headers.get("accept-ranges") == "bytes", (
                    f"missing Accept-Ranges: {dict(r_audio.headers)}"
                )
                cc = (r_audio.headers.get("cache-control") or "").lower()
                assert "private" in cc and "no-store" in cc, f"bad Cache-Control: {cc!r}"
                assert r_audio.content == wav_bytes, "audio bytes differ from uploaded WAV"

                # Range request (seek)
                r_rng = client.get(
                    f"api/listening/material/audio?id={wav_id}",
                    headers={"Authorization": "Bearer " + tok_a, "Range": "bytes=0-63"},
                )
                assert r_rng.status_code == 206, f"range status {r_rng.status_code}"
                assert r_rng.content == wav_bytes[:64], "range bytes mismatch"
                assert r_rng.headers.get("content-range") == f"bytes 0-63/{len(wav_bytes)}"

                # 5. Another user cannot access User A's audio (and anon gets 401)
                r_anon = client.get(f"api/listening/material/audio?id={wav_id}")
                assert r_anon.status_code == 401, f"anon audio status {r_anon.status_code}"

                r_reg = client.post(
                    "api/register",
                    json={"name": USER_B[0], "password": USER_B[1]},
                )
                assert r_reg.status_code in (200, 409)
                u_b = client.post(
                    "api/login",
                    json={"name": USER_B[0], "password": USER_B[1]},
                ).json()
                tok_b = u_b["token"]
                r_other = client.get(
                    f"api/listening/material/audio?id={wav_id}",
                    headers={"Authorization": "Bearer " + tok_b},
                )
                assert r_other.status_code in (403, 404), (
                    f"other user accessed audio: {r_other.status_code}"
                )
                out["2_wav_http"] = {
                    "id": wav_id,
                    "bytes": len(r_audio.content),
                    "content_type": r_audio.headers.get("content-type"),
                    "range_206": True,
                }
                out["5_isolation"] = {
                    "anon_status": r_anon.status_code,
                    "other_user_status": r_other.status_code,
                }

            # 3. Delete via UI: disappears from list and audio returns 404.
            pg.click("#lOwnDeleteBtn")
            pg.wait_for_timeout(450)
            assert "My WAV Clip" not in pg.inner_text("#lOwnList"), (
                f"deleted material still listed: {pg.inner_text('#lOwnList')}"
            )
            with httpx.Client(base_url=URL, timeout=15.0) as client:
                r_gone = client.get(
                    f"api/listening/material/audio?id={wav_id}",
                    headers={"Authorization": "Bearer " + tok_a},
                )
                assert r_gone.status_code == 404, f"deleted audio still returned {r_gone.status_code}"
                out["3_delete"] = {"audio_after_delete": r_gone.status_code}

            # 4. Limits + validation via HTTP API (using User B so User A stays clean)
            with httpx.Client(base_url=URL, timeout=30.0) as client:
                # Invalid part -> 400
                r_bad_part = client.post(
                    "api/listening/material",
                    headers=api_headers(tok_b),
                    json={"title": "Bad part", "part": "all", "task": ["Q1"]},
                )
                assert r_bad_part.status_code == 400, f"expected 400 for part=all, got {r_bad_part.status_code}"

                # HTML sanitization check
                r_html = client.post(
                    "api/listening/material",
                    headers=api_headers(tok_b),
                    json={
                        "title": "<b>Clean</b> Title",
                        "part": 1,
                        "task": ["<script>alert(1)</script>Question 1"],
                        "script": "<i>Hello</i> world",
                    },
                )
                assert r_html.status_code == 200, f"sanitized post failed: {r_html.status_code} {r_html.text}"
                created_1 = r_html.json()
                assert "<" not in created_1["title"] and ">" not in created_1["title"]
                assert "<script>" not in created_1["task"][0]
                assert "<i>" not in created_1["script"]

                # Audio >20 MB -> 413
                oversize_b64 = base64.b64encode(b"\x00" * (20 * 1024 * 1024 + 1024)).decode("ascii")
                r_big = client.post(
                    "api/listening/material",
                    headers=api_headers(tok_b),
                    json={
                        "title": "Too big",
                        "part": 1,
                        "audio_b64": oversize_b64,
                        "mime": "audio/wav",
                    },
                )
                assert r_big.status_code == 413, f"expected 413 for >20MB audio, got {r_big.status_code} {r_big.text}"

                # Fill up to 10 materials (1 already created above -> create 9 more)
                for idx in range(2, 11):
                    r_ok = client.post(
                        "api/listening/material",
                        headers=api_headers(tok_b),
                        json={"title": f"Item {idx}", "part": ((idx - 1) % 4) + 1, "task": [f"Q {idx}"]},
                    )
                    assert r_ok.status_code == 200, f"item {idx} failed: {r_ok.status_code} {r_ok.text}"

                # 11th material -> 429
                r_11 = client.post(
                    "api/listening/material",
                    headers=api_headers(tok_b),
                    json={"title": "Item 11", "part": 1, "task": ["Q 11"]},
                )
                assert r_11.status_code == 429, f"expected 429 for 11th material, got {r_11.status_code} {r_11.text}"
                out["4_limits"] = {
                    "over_20mb": r_big.status_code,
                    "item_11": r_11.status_code,
                    "bad_part": r_bad_part.status_code,
                }

            assert page_errors == [], f"desktop page errors: {page_errors}"
            assert console_errors == [], f"desktop console errors: {console_errors}"
            pg.close()

            # ------------------------------------------------------------------
            # 6. Mobile 390x844 (light & dark, ES & EN, no speechSynthesis)
            # ------------------------------------------------------------------
            m_ctx = browser.new_context(viewport={"width": 390, "height": 844})
            mpg = m_ctx.new_page()
            m_errors = []
            mpg.on("pageerror", lambda e: m_errors.append(str(e)))
            # Simulate a browser without speechSynthesis to verify graceful hide
            mpg.add_init_script("try { delete window.speechSynthesis; } catch (e) {} Object.defineProperty(window, 'speechSynthesis', { value: undefined, configurable: true });")

            mpg.goto(URL + "app", wait_until="networkidle")
            login_user(mpg, URL, USER_A[0], USER_A[1])
            open_listening_own(mpg)

            assert mpg.is_visible("#lOwnPanel"), "mobile #lOwnPanel not visible"
            # Play script button must be hidden when speechSynthesis is absent
            assert not mpg.is_visible("#lOwnPlayScriptBtn"), (
                "Play script button stayed visible without speechSynthesis"
            )

            for theme in ("light", "dark"):
                for lang in ("en", "es"):
                    mpg.evaluate(f"setThemeMode('{theme}'); setLang('{lang}')")
                    mpg.wait_for_timeout(150)
                    metrics = mpg.evaluate("""() => {
                        const doc = document.documentElement;
                        const panel = document.getElementById('lOwnPanel');
                        const rect = panel.getBoundingClientRect();
                        const btns = [...panel.querySelectorAll('button, input[type=text], input[type=file]')]
                          .filter(el => el.offsetParent !== null)
                          .map(el => ({id: el.id || el.className, h: Math.round(el.getBoundingClientRect().height)}));
                        return {
                            scrollWidth: doc.scrollWidth,
                            clientWidth: doc.clientWidth,
                            panelRight: Math.round(rect.right),
                            panelWidth: Math.round(rect.width),
                            controls: btns,
                        };
                    }""")
                    assert metrics["scrollWidth"] <= metrics["clientWidth"], (
                        f"horizontal overflow at 390x844 ({theme}/{lang}): {metrics}"
                    )
                    for ctl in metrics["controls"]:
                        assert ctl["h"] >= 44, (
                            f"control <44px on mobile ({theme}/{lang}): {ctl}"
                        )
            assert m_errors == [], f"mobile page errors: {m_errors}"
            out["6_mobile_390x844"] = {
                "overflow": False,
                "tts_hidden_when_unsupported": True,
                "page_errors": m_errors,
            }
            m_ctx.close()
            browser.close()
    finally:
        try:
            os.unlink(tmp_wav.name)
        except OSError:
            pass

    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
