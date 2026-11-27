# -*- coding: utf-8 -*-
"""Pipeline integration tests for the two-call writing corrector (mock provider, no network)."""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import prompts  # noqa: E402

FAKE_KEY = "sk-pipeline-test-key-00112233"

GOOD_AUDIT = {
    "task_points": [
        {"point": "everyday habits at home", "status": "present", "quote": "recycle plastic and glass"},
        {"point": "laws and regulations", "status": "present", "quote": "governments should introduce strict laws"},
        {"point": "your own idea", "status": "present", "quote": "schools ought to teach conservation"},
    ],
    "word_count_echo": 150,
    "paragraph_count_echo": 4,
    "register": {"verdict": "neutral", "markers": ["However", "Furthermore", "In conclusion"]},
    "cohesion": {"devices": ["Firstly", "However", "Furthermore", "In conclusion"], "paragraph_breaks": True},
    "grammar_errors": [
        {"quote": "more better", "type": "word_form", "severity": "minor"},
    ],
    "complex_structures": ["If families recycled more, waste would decline."],
    "off_topic": False,
}


def make_score(c, ca, o, l, extra=None):
    obj = {
        "feedback": {
            "content": "Task points: habits present, laws present, education present.",
            "communicative_achievement": "Register is neutral and suits an essay.",
            "organisation": "Four clear paragraphs with varied cohesive devices.",
            "language": "Good range of vocabulary with one minor slip.",
        },
        "quotes": {
            "content": "recycle plastic and glass",
            "communicative_achievement": "governments should introduce strict laws",
            "organisation": "Furthermore, schools ought to teach conservation",
            "language": "If families recycled more, waste would decline",
        },
        "weaknesses": {
            "content": ["Own idea could be developed further.", "Conclusion summarises briefly."],
            "communicative_achievement": ["Some ideas remain straightforward.", "Opening is somewhat general."],
            "organisation": ["Transitions between body paragraphs are conventional.", "Linkers repeat."],
            "language": ["Minor comparative error in one clause.", "Limited idiomatic range."],
        },
        "bands": {
            "content": c,
            "communicative_achievement": ca,
            "organisation": o,
            "language": l,
        },
        "rewrite": [
            "Protecting the environment has become an urgent priority for modern societies.",
            "Strict legislation would compel corporations to curb industrial emissions.",
            "Educating young citizens fosters enduring environmentally responsible habits.",
        ],
    }
    if extra:
        obj.update(extra)
    return obj


MOCK = {"queue": [], "received": []}


class ScriptedProviderHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        req_body = json.loads(raw.decode("utf-8"))
        MOCK["received"].append(req_body)

        if not MOCK["queue"]:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"queue empty")
            return
        step = MOCK["queue"].pop(0)
        status = step.get("status", 200)
        if status != 200:
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"upstream error")
            return
        content = step["content"]
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        envelope = {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 200},
        }
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


mock_srv = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedProviderHandler)
MOCK_PORT = mock_srv.server_address[1]
threading.Thread(target=mock_srv.serve_forever, daemon=True).start()

os.environ["B2_AI_BASE"] = f"http://127.0.0.1:{MOCK_PORT}"
os.environ["B2_AI_MODEL"] = "deepseek-chat"
os.environ["B2_BYO_TRUSTED_BASES"] = f"http://127.0.0.1:{MOCK_PORT}"
os.environ.pop("B2_AI_KEY", None)

import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2pipe-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.B2_AI_BASE = f"http://127.0.0.1:{MOCK_PORT}"
S.B2_AI_MODEL = "deepseek-chat"
S.migrate_legacy()

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
APP_PORT = srv.server_address[1]
S.PORT = APP_PORT
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{APP_PORT}"

ESSAY_GOOD = "\n\n".join([
    "Protecting the environment has become one of the most urgent questions facing modern societies today, "
    "and citizens often debate whether individuals or governments bear greater responsibility for safeguarding nature.",
    "Firstly, everyday habits at home clearly help when people recycle plastic and glass, conserve electricity, "
    "reduce household food waste and choose public transport instead of private vehicles. If families recycled "
    "more consistently across every neighbourhood, household waste would decline significantly in major cities.",
    "However, governments should introduce strict laws and regulations because voluntary behaviour alone cannot "
    "stop industrial pollution from large factories. Furthermore, schools ought to teach conservation and climate "
    "science so younger generations understand why protecting natural ecosystems matters for their shared future.",
    "In conclusion, although ordinary citizens play a meaningful role at home through daily choices, strong "
    "national legislation from governments ultimately delivers much broader and faster environmental protection.",
])

ESSAY_ONE_PARA = ESSAY_GOOD.replace("\n\n", " ")

ESSAY_110_WORDS = (
    "Protecting the environment is a major issue in the modern world and people debate who can achieve more "
    "when addressing climate change and pollution.\n\n"
    "Firstly, ordinary families can recycle plastic bottles, turn off lights and use public transport to reduce "
    "daily household waste and carbon emissions in busy cities.\n\n"
    "However, governments must also introduce strict laws and heavy fines so big factories stop polluting rivers "
    "and air. In addition, schools should teach young children about nature so they develop lasting green habits early.\n\n"
    "In conclusion, both citizens and governments play important roles, although strong national regulations create "
    "much larger change across the whole country."
)

ESSAY_INFORMAL = (
    "Hey guys! So yeah, I'm gonna talk about saving the planet, you know! It's super important and we've gotta "
    "do our bit right now because everyone keeps arguing about who should fix this mess!\n\n"
    "First up, recycling stuff at home is cool and actually helps loads! If you don't waste tons of water, "
    "carry reusable bags and turn off lights when leaving rooms, you're already doing awesome!\n\n"
    "At the same time, governments gotta make tough laws and rules because big companies won't stop dumping crap "
    "into rivers unless somebody forces them, don't you think?! They can't just ignore nature forever!\n\n"
    "Plus, schools should get kids excited about green projects because young folks totally love cool ideas! "
    "All in all, both regular people and tough rules really matter, guys!"
)

TASK_PROMPT = "Write an essay: 1. everyday habits at home 2. laws and regulations 3. your own idea."


def post_writing(body):
    S._AI_RATE.clear()
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        URL + "/api/ai/writing",
        data=data,
        headers={"Content-Type": "application/json", "X-Forwarded-For": "127.0.0.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


out = {}

# 1. Happy path: audit -> score (non-collapsed), audit fenced, server metadata cannot be spoofed.
MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": make_score(4, 3, 4, 4, extra={
        "audit_used": False,
        "guards_applied": ["spoofed_guard"],
        "collapsed": True,
        "facts": {"words": 9999},
        "audit": {"spoofed": True},
    })},
]
st, res = post_writing({
    "text": ESSAY_GOOD, "task": "essay", "prompt": TASK_PROMPT, "provider_key": FAKE_KEY,
})
assert st == 200, (st, res)
assert len(MOCK["received"]) == 2, f"expected 2 calls (audit + score), got {len(MOCK['received'])}"
assert res["audit_used"] is True
assert isinstance(res["audit"], dict) and len(res["audit"]["task_points"]) == 3
assert res["guards_applied"] == []
assert res["collapsed"] is False
assert res["facts"]["paragraphs"] == 4 and res["facts"]["words"] > 120
assert res["bands"] == {"content": 4, "communicative_achievement": 3, "organisation": 4, "language": 4}
assert res["total"] == 15
score_user_msg = MOCK["received"][1]["messages"][1]["content"]
assert "<<<AUDIT_" in score_user_msg and "<<<END_AUDIT_" in score_user_msg, "audit not fenced in score call"
out["1_happy_two_call"] = {"calls": len(MOCK["received"]), "total": res["total"], "audit_used": res["audit_used"]}

# 2. Collapsed triple with no guards -> triggers EXACTLY ONE re-score; un-collapses -> collapsed: False.
MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": make_score(3, 3, 3, 4)},
    {"content": make_score(4, 3, 4, 4)},
]
st, res = post_writing({"text": ESSAY_GOOD, "task": "essay", "prompt": TASK_PROMPT, "provider_key": FAKE_KEY})
assert st == 200, (st, res)
assert len(MOCK["received"]) == 3, f"expected 3 calls (audit + score + 1 rescore), got {len(MOCK['received'])}"
assert S.RESCORE_COLLAPSE_INSTRUCTION in MOCK["received"][2]["messages"][1]["content"]
assert res["collapsed"] is False
assert res["bands"] == {"content": 4, "communicative_achievement": 3, "organisation": 4, "language": 4}
out["2_collapse_rescore_resolved"] = {"calls": len(MOCK["received"]), "collapsed": res["collapsed"]}

# 3. Collapsed triple that collapses AGAIN on re-score -> keeps it, sets collapsed: True, stops at 3 calls.
MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": make_score(3, 3, 3, 3)},
    {"content": make_score(3, 3, 3, 3)},
]
st, res = post_writing({"text": ESSAY_GOOD, "task": "essay", "prompt": TASK_PROMPT, "provider_key": FAKE_KEY})
assert st == 200, (st, res)
assert len(MOCK["received"]) == 3, f"expected max 3 calls, got {len(MOCK['received'])}"
assert res["collapsed"] is True
assert res["bands"] == {"content": 3, "communicative_achievement": 3, "organisation": 3, "language": 3}
out["3_collapse_persists"] = {"calls": len(MOCK["received"]), "collapsed": res["collapsed"]}

# 4. Triple becomes equal ONLY because a guard fired -> NO re-score (2 calls), collapsed: False.
MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": make_score(4, 3, 3, 3)},
]
st, res = post_writing({"text": ESSAY_110_WORDS, "task": "essay", "provider_key": FAKE_KEY})
assert st == 200, (st, res)
assert len(MOCK["received"]) == 2, f"guard-induced triple must not trigger rescore, got {len(MOCK['received'])}"
assert res["guards_applied"] == ["content_short_120"]
assert res["bands"]["content"] == 3
assert res["collapsed"] is False
out["4_guard_prevents_rescore"] = {"calls": len(MOCK["received"]), "guards": res["guards_applied"]}

# 5. Audit HTTP 500 degrades gracefully -> audit_used: False, audit: None, 200 with bands.
MOCK["received"].clear()
MOCK["queue"] = [
    {"status": 500},
    {"status": 500},  # 1 retry on audit
    {"content": make_score(4, 3, 4, 3)},
]
st, res = post_writing({"text": ESSAY_GOOD, "task": "essay", "provider_key": FAKE_KEY})
assert st == 200, (st, res)
assert res["audit_used"] is False and res["audit"] is None
assert res["bands"] == {"content": 4, "communicative_achievement": 3, "organisation": 4, "language": 3}
out["5_audit_500_degrades"] = {"status": st, "audit_used": res["audit_used"]}

# 6. Audit invalid JSON degrades gracefully -> audit_used: False, audit: None, 200 with bands.
MOCK["received"].clear()
MOCK["queue"] = [
    {"content": "not valid json {{{"},
    {"content": make_score(4, 3, 4, 3)},
]
st, res = post_writing({"text": ESSAY_GOOD, "task": "essay", "provider_key": FAKE_KEY})
assert st == 200, (st, res)
assert res["audit_used"] is False and res["audit"] is None
assert res["total"] == 14
out["6_audit_bad_json_degrades"] = {"status": st, "audit_used": res["audit_used"]}

# 7. Guard independence end-to-end: single paragraph clamps organisation only, never language.
MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": make_score(4, 4, 5, 5)},
]
st, res = post_writing({"text": ESSAY_ONE_PARA, "task": "essay", "provider_key": FAKE_KEY})
assert st == 200, (st, res)
assert res["bands"]["organisation"] == 2
assert res["bands"]["language"] == 5
assert "organisation_no_paragraphs" in res["guards_applied"]
out["7_no_para_independence"] = {"bands": res["bands"], "guards": res["guards_applied"]}

# 8. Informal register clamped on essay, exempt on email.
MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": make_score(4, 4, 3, 3)},
]
st_e, res_e = post_writing({"text": ESSAY_INFORMAL, "task": "essay", "provider_key": FAKE_KEY})
assert st_e == 200 and res_e["bands"]["communicative_achievement"] == 2
assert "ca_informal_sustained" in res_e["guards_applied"]

MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": make_score(4, 4, 3, 3)},
]
st_m, res_m = post_writing({"text": ESSAY_INFORMAL, "task": "email", "provider_key": FAKE_KEY})
assert st_m == 200 and res_m["bands"]["communicative_achievement"] == 4
assert "ca_informal_sustained" not in res_m["guards_applied"]
out["8_email_exemption"] = {"essay_ca": res_e["bands"]["communicative_achievement"], "email_ca": res_m["bands"]["communicative_achievement"]}

# 9. Refusal, bad score schema, and prompt leak paths remain unchanged.
MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": {"refuse": True, "reason": "not_a_writing_task"}},
]
st_r, res_r = post_writing({"text": ESSAY_GOOD, "task": "essay", "provider_key": FAKE_KEY})
assert st_r == 200 and res_r == {"refused": True, "reason": "not_a_writing_task"}, (st_r, res_r)

MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": {"bands": {"content": 3}}},
]
st_bad, _ = post_writing({"text": ESSAY_GOOD, "task": "essay", "provider_key": FAKE_KEY})
assert st_bad == 422, st_bad

MOCK["received"].clear()
MOCK["queue"] = [
    {"content": GOOD_AUDIT},
    {"content": prompts.WRITING_SCORE_SYSTEM},
]
st_leak, res_leak = post_writing({"text": ESSAY_GOOD, "task": "essay", "provider_key": FAKE_KEY})
assert st_leak == 502 and res_leak.get("error") == "unsafe output", (st_leak, res_leak)
out["9_contracts_unchanged"] = {"refusal": st_r, "bad_schema": st_bad, "leak": st_leak}

srv.shutdown()
mock_srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
