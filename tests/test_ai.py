import io
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# 1. Mock Gemini Provider on a local port (no network, no real keys)
# ---------------------------------------------------------------------------
MOCK_PORT = 8123
APP_PORT = 8097
os.environ["B2_AI_BASE"] = f"http://127.0.0.1:{MOCK_PORT}/v1beta"
os.environ["B2_AI_MODEL"] = "gemini-2.0-flash"
os.environ.pop("B2_AI_KEY", None)

MOCK_STATE = {"mode": "ok"}

VALID_MODEL_JSON = {
    "bands": {
        "content": 4,
        "communicative_achievement": 3,
        "organisation": 4,
        "language": 2,
    },
    "feedback": {
        "content": "Cumpliste bien con los puntos de la consigna, aunque faltó desarrollar el tercer argumento.",
        "communicative_achievement": "El registro es apropiado para un Essay, sostenés la atención del lector.",
        "organisation": "Muy buen uso de conectores y división en párrafos claros.",
        "language": "Tenés errores gramaticales frecuentes que debés pulir para asegurar nivel B2.",
    },
    "quotes": {
        "content": "pollution and damage to the environment is the most serious problem",
        "communicative_achievement": "First of all, it is widely believed that transport plays a major role",
        "organisation": "In addition to this, our rivers and seas are in danger",
        "language": "Doing a little steps for protection our environment every day",
    },
    "weaknesses": {
        "content": [
            "Faltó desarrollar el tercer punto propio pedido en la consigna.",
            "El cierre repite la introducción sin aportar una conclusión concreta.",
        ],
        "communicative_achievement": [
            "Predominan ideas simples sin matices ni argumentación compleja.",
            "Tono por momentos demasiado general para sostener el interés de principio a fin.",
        ],
        "organisation": [
            "Conectores básicos de enumeración ('First of all', 'In addition to this').",
            "Párrafos cortos de una sola oración sin desarrollo interno.",
        ],
        "language": [
            "Error de concordancia sujeto-verbo en 'pollution and damage... is'.",
            "Colocación y preposición incorrectas en 'Doing a little steps for protection'.",
        ],
    },
    "rewrite": [
        "Pollution and environmental damage are among the most pressing challenges worldwide.",
        "First of all, transport causes significant harm to the environment.",
        "Taking small steps to protect our environment every day will help us save the planet.",
    ],
}


class MockGeminiHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(length) if length > 0 else b""
        mode = MOCK_STATE["mode"]

        if mode == "down":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"internal upstream error")
            return

        payload_obj = json.loads(json.dumps(VALID_MODEL_JSON))
        if mode == "missing_key":
            del payload_obj["bands"]["language"]
        elif mode == "band_7":
            payload_obj["bands"]["content"] = 7
        elif mode == "rewrite_2":
            payload_obj["rewrite"] = payload_obj["rewrite"][:2]
        elif mode == "feedback_array":
            payload_obj["feedback"] = ["buen contenido", "buen logro", "buena org", "buen idioma"]
        elif mode == "no_weaknesses":
            del payload_obj["weaknesses"]
        elif mode == "weakness_1":
            payload_obj["weaknesses"]["language"] = ["Un solo error listado"]

        if self.path.endswith("/chat/completions"):
            envelope = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(payload_obj, ensure_ascii=False),
                        }
                    }
                ]
            }
        else:
            envelope = {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(payload_obj, ensure_ascii=False)}]
                        }
                    }
                ]
            }
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


mock_srv = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), MockGeminiHandler)
mock_th = threading.Thread(target=mock_srv.serve_forever, daemon=True)
mock_th.start()

# ---------------------------------------------------------------------------
# 2. B2First server on an alternative port with temporary DATA_DIR and captured log
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S
import store

_tmp = tempfile.mkdtemp(prefix="b2ai-")
server_log_path = os.path.join(_tmp, "server.log")
server_log_buf = io.StringIO()

S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.PORT = APP_PORT
S.B2_AI_BASE = f"http://127.0.0.1:{MOCK_PORT}/v1beta"
S.B2_AI_MODEL = "gemini-2.0-flash"

orig_log_message = S.H.log_message


def _capturing_log_message(self, fmt, *a):
    msg = "%s - - [%s] %s\n" % (
        self.address_string(),
        self.log_date_time_string(),
        fmt % a,
    )
    server_log_buf.write(msg)
    with open(server_log_path, "a", encoding="utf-8") as f:
        f.write(msg)
    orig_log_message(self, fmt, *a)


S.H.log_message = _capturing_log_message
S.migrate_legacy()

srv = S.ThreadingHTTPServer(("127.0.0.1", S.PORT), S.H)
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()

URL = f"http://127.0.0.1:{APP_PORT}"
SAMPLE_TEXT = (
    "Nowadays pollution and damage to the environment is the most serious and difficult problem "
    "for countries all over the world. First of all, transport causes huge damage to the environment "
    "because people cannot imagine living without cars and planes. In addition to this, our rivers "
    "and seas are in danger due to factories pouring waste. Every person must contribute to solving "
    "this problem by taking small steps every day."
)
FAKE_KEY = "AIzaSyFAKE_SECRET_TEST_KEY_99887766"


def post_ai(body, ip="127.0.0.1"):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        URL + "/api/ai/writing",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Forwarded-For": ip,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


out = {}

# Assert 1: 10-char text -> 400
st1, body1 = post_ai({"text": "1234567890", "kind": "Essay", "provider_key": FAKE_KEY})
assert st1 == 400, f"Expected 400 for 10 chars, got {st1}: {body1}"
out["1_short_text_400"] = st1

# Assert 2: invalid kind -> 400
st2, body2 = post_ai({"text": SAMPLE_TEXT, "kind": "Poem", "provider_key": FAKE_KEY})
assert st2 == 400, f"Expected 400 for invalid kind, got {st2}: {body2}"
out["2_invalid_kind_400"] = st2

# Assert 3: no key -> 502
st3, body3 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": ""})
assert st3 == 502, f"Expected 502 for missing key, got {st3}: {body3}"
out["3_no_key_502"] = st3

# Assert 4: mock responds correctly -> 200 with the 4 bands and total = sum
MOCK_STATE["mode"] = "ok"
st4, body4 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY})
assert st4 == 200, f"Expected 200 for valid response, got {st4}: {body4}"
res4 = json.loads(body4)
assert set(res4["bands"].keys()) == {
    "content",
    "communicative_achievement",
    "organisation",
    "language",
}
assert res4["total"] == sum(res4["bands"].values()) == 13
assert len(res4["rewrite"]) == 3
out["4_valid_200_total"] = res4["total"]

# Assert 5: mock returns JSON without a key -> 422
MOCK_STATE["mode"] = "missing_key"
st5, body5 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY})
assert st5 == 422, f"Expected 422 for missing key in schema, got {st5}: {body5}"
out["5_missing_schema_key_422"] = st5

# Assert 6: mock returns band 7 -> 422
MOCK_STATE["mode"] = "band_7"
st6, body6 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY})
assert st6 == 422, f"Expected 422 for band 7, got {st6}: {body6}"
out["6_band_7_422"] = st6

# Assert 7: mock returns rewrite with 2 strings -> 422
MOCK_STATE["mode"] = "rewrite_2"
st7, body7 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY})
assert st7 == 422, f"Expected 422 for rewrite len 2, got {st7}: {body7}"
out["7_rewrite_2_422"] = st7

# Assert 8: 11 requests in a row -> the 11th is 429
MOCK_STATE["mode"] = "ok"
S._AI_RATE.clear()
statuses_11 = []
for _ in range(11):
    st_i, _ = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY}, ip="10.9.8.7")
    statuses_11.append(st_i)
assert statuses_11[:10] == [200] * 10, f"Expected first 10 to be 200, got {statuses_11}"
assert statuses_11[10] == 429, f"Expected 11th request to be 429, got {statuses_11}"
out["8_rate_limit_11th"] = statuses_11[10]

# Assert 9: the sent key does NOT appear in the server log file nor in the error response
MOCK_STATE["mode"] = "down"
st_err, body_err = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY}, ip="10.9.8.99")
assert st_err == 502, f"Expected 502 when upstream down, got {st_err}"
log_contents = open(server_log_path, "r", encoding="utf-8").read() if os.path.exists(server_log_path) else ""
assert FAKE_KEY not in body_err, "API key leaked in error response body!"
assert FAKE_KEY not in body1 and FAKE_KEY not in body5 and FAKE_KEY not in body6 and FAKE_KEY not in body7
assert FAKE_KEY not in log_contents and FAKE_KEY not in server_log_buf.getvalue(), "API key leaked in server log!"
out["9_no_key_leak"] = True

# Assert 10: E2E flow in the browser with Playwright (✨ AI tab, states, saved in D.log)
MOCK_STATE["mode"] = "ok"
S._AI_RATE.clear()
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    js_errs = []
    pg.on("pageerror", lambda e: js_errs.append(str(e)))
    pg.goto(URL + "/", wait_until="networkidle")
    pg.evaluate(
        """() => {
        syncPush = () => {};
        syncPull = async () => null;
        const u = {id: 'test_ai_user', name: 'TestAI', color: '#1e3a8a', token: ''};
        localStorage.setItem('b2first_user', JSON.stringify(u));
        localStorage.setItem('ob_test_ai_user', '1');
        USER = u;
        D = load();
        D.onboarded = true;
        D.settings.aiKey = '';
        hideAuthOverlay();
        hideOnboarding();
        refreshAll();
    }"""
    )
    pg.click("nav button[data-view='ia']")
    pg.wait_for_timeout(150)
    # No key: warning visible and button disabled
    btn_disabled = pg.evaluate("document.getElementById('iaSubmitBtn').disabled")
    warn_visible = pg.evaluate("getComputedStyle(document.getElementById('iaNoKeyWarn')).display !== 'none'")
    assert btn_disabled is True and warn_visible is True

    # Load key in PLAN -> D.settings.aiKey
    pg.click("nav button[data-view='plan']")
    pg.fill("#pAiKey", FAKE_KEY)
    pg.click("nav button[data-view='ia']")
    pg.wait_for_timeout(100)
    assert pg.evaluate("document.getElementById('iaSubmitBtn').disabled") is False

    # Fill in the text and correct it
    pg.select_option("#iaKind", "Article")
    pg.fill("#iaText", SAMPLE_TEXT)
    pg.click("#iaSubmitBtn")
    pg.wait_for_selector("#iaCard[data-state='ok']", timeout=5000)

    cards_count = pg.eval_on_selector_all("#iaBandsGrid .ia-band-card", "els => els.length")
    weak_items_count = pg.eval_on_selector_all("#iaBandsGrid .ia-band-weak li", "els => els.length")
    rewrites_count = pg.eval_on_selector_all("#iaRewriteList li", "els => els.length")
    last_log = pg.evaluate("D.log[0]")
    assert cards_count == 4
    assert weak_items_count == 8
    assert rewrites_count == 3
    assert last_log["type"] == "w" and last_log["kind"] == "Article" and last_log["note"] == "IA"
    assert last_log["total"] == 13 and last_log["kb"] == 4 and last_log["kc"] == 3 and last_log["ko"] == 4 and last_log["kl"] == 2
    assert js_errs == [], f"JS errors: {js_errs}"
    out["10_ui_e2e_ok"] = True
    b.close()

# Assert 11: Mock with DeepSeek wire (choices[0].message.content) and feedback as object -> 200
MOCK_STATE["mode"] = "ok"
S._AI_RATE.clear()
S.B2_AI_MODEL = ""
os.environ.pop("B2_AI_MODEL", None)
st11, body11 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider": "deepseek", "provider_key": FAKE_KEY}, ip="10.9.9.11")
assert st11 == 200, f"Expected 200 for deepseek valid object feedback, got {st11}: {body11}"
res11 = json.loads(body11)
assert isinstance(res11["feedback"], dict) and set(res11["feedback"].keys()) == {
    "content",
    "communicative_achievement",
    "organisation",
    "language",
}
assert res11["model"] == "deepseek-chat"
out["11_deepseek_valid_200"] = st11

# Assert 12: DeepSeek mock with feedback as array -> 422
MOCK_STATE["mode"] = "feedback_array"
st12, body12 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider": "deepseek", "provider_key": FAKE_KEY}, ip="10.9.9.12")
assert st12 == 422, f"Expected 422 for deepseek feedback array, got {st12}: {body12}"
out["12_deepseek_feedback_array_422"] = st12

# Assert 13: provider: "gemini" in the body still works with the Gemini mock -> 200
MOCK_STATE["mode"] = "ok"
st13, body13 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider": "gemini", "provider_key": FAKE_KEY}, ip="10.9.9.13")
assert st13 == 200, f"Expected 200 for provider gemini in body, got {st13}: {body13}"
res13 = json.loads(body13)
assert res13["total"] == 13 and res13["model"] == "gemini-2.0-flash"
out["13_gemini_provider_200"] = st13

# Assert 14: mock without weaknesses -> 422
MOCK_STATE["mode"] = "no_weaknesses"
st14, body14 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY}, ip="10.9.9.14")
assert st14 == 422, f"Expected 422 when weaknesses is missing, got {st14}: {body14}"
out["14_missing_weaknesses_422"] = st14

# Assert 15: mock with weaknesses.language as a single string -> 422
MOCK_STATE["mode"] = "weakness_1"
st15, body15 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY}, ip="10.9.9.15")
assert st15 == 422, f"Expected 422 when weaknesses.language has 1 item, got {st15}: {body15}"
out["15_weaknesses_len_1_422"] = st15

# Assert 16: complete mock with weaknesses -> 200 and the response includes the 8 weaknesses
MOCK_STATE["mode"] = "ok"
st16, body16 = post_ai({"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": FAKE_KEY}, ip="10.9.9.16")
assert st16 == 200, f"Expected 200 for full payload with weaknesses, got {st16}: {body16}"
res16 = json.loads(body16)
assert isinstance(res16.get("weaknesses"), dict) and set(res16["weaknesses"].keys()) == {
    "content",
    "communicative_achievement",
    "organisation",
    "language",
}
total_weaknesses = sum(len(v) for v in res16["weaknesses"].values())
assert total_weaknesses == 8, f"Expected 8 weaknesses, got {total_weaknesses}"
out["16_weaknesses_count"] = total_weaknesses

srv.shutdown()
mock_srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
