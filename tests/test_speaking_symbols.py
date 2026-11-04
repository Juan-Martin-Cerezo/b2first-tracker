"""Backlog 31: after the dead-code sweep the speaking engine still has its symbols.

The sweep removed declarations no code path reaches. This test pins the other
side: every function and method the exam room and the server actually call must
still be declared, every `onclick="SP_EXAM.x()"` in the markup must resolve, and
the removed names must not sneak back in. Static: it parses index.html and
imports the two pure speaking modules; it starts no server and reads no data/.

Run: cd tests && python3 test_speaking_symbols.py
"""
import importlib
import os
import re
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)

INDEX = os.path.join(REPO, "index.html")
SERVER = os.path.join(REPO, "server.py")

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else "FAIL " + str(detail or name)
    if not cond:
        failed.append(name)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


index = read(INDEX)
server = read(SERVER)
script = max(re.findall(r"<script>(.*?)</script>", index, re.S), key=len)

# --- 1. The functions the exam room drives every frame/phase --------------
ENGINE_FUNCTIONS = [
    "spxLoadBank", "spxPlanSession", "spxPhases", "spxEnterPhase",
    "spxNextPhase", "spxEnterSessionPart", "spxPartFinished", "spxTickLoop",
    "spxSpeechStart", "spxSpeechStop", "spxCandidateLine", "spxPartnerSay",
    "spxPartnerTurn", "spxFollowUpWanted", "spxCandidateContext",
    "spxTurnState", "spxRenderTurn", "spxRenderTx", "spxRenderTask",
    "spxPhotoFigure", "spxPreloadPhoto", "spxFinalizeReport",
    "spxRenderReportScreen", "spxSpeechCounts", "spxTranscriptText",
    "spxCopyPlain", "spxEndExam", "spxPart1Silence", "spxSilence",
    "spxProbePartnerAi",
]
missing = [n for n in ENGINE_FUNCTIONS
           if not re.search(r"(?:async\s+)?function\s+" + n + r"\s*\(", script)]
check("engine_functions_declared", not missing, missing)

# --- 2. The SP_EXAM methods the overlay calls ------------------------------
METHODS = ["open", "close", "start", "startFull", "ready", "back", "stopEarly",
           "saveReport", "retry", "copyTranscript", "repeatPart", "restart",
           "muteMic", "whoTurn"]
missing = [n for n in METHODS
           if not re.search(r"SP_EXAM\." + n + r"\s*=\s*(?:async\s+)?function", script)]
check("sp_exam_methods_declared", not missing, missing)

# Cross-check: every handler in the markup resolves to a declared method. This
# catches a rename on one side only, which is how this file could rot silently.
handlers = sorted(set(re.findall(r"onclick=\"SP_EXAM\.(\w+)\(", index)))
unresolved = [n for n in handlers
              if not re.search(r"SP_EXAM\." + n + r"\s*=\s*(?:async\s+)?function", script)]
check("markup_handlers_resolve", not unresolved, unresolved)

# --- 3. The state the engine keeps between phases -------------------------
for field in ["session", "full", "phases", "phase", "partner", "partnerSaid",
              "partnerAsked", "followUps", "micMuted", "rephraseQi", "saved"]:
    base = "SPK" if field == "followUps" else "SP_EXAM"
    check("state_" + field, re.search(r"\b" + base + r"\." + field + r"\b", script) is not None)

# --- 4. The server-side speaking API the endpoints import ------------------
speaking_prompts = importlib.import_module("speaking_prompts")
speaking_report = importlib.import_module("speaking_report")

PROMPT_API = ["clean_task", "examiner_instruction", "partner_instruction",
              "scripted_lines"]
REPORT_API = ["validate_payload", "candidate_text", "report_message",
              "dialogue_text", "system_prompt", "parse_model_output",
              "band_from_pa", "proxies", "score_to_band", "pronunciation_score"]
missing = [n for n in PROMPT_API if not callable(getattr(speaking_prompts, n, None))]
check("prompts_api_callable", not missing, missing)
missing = [n for n in REPORT_API if not callable(getattr(speaking_report, n, None))]
check("report_api_callable", not missing, missing)

# --- 5. The sweep removed only names with no caller ----------------------
check("no_sp_exam_report_data", "SP_EXAM.reportData" not in index)
check("no_sp_exam_started_at", "SP_EXAM.startedAt" not in index)
check("no_turn_sessions_clear", "_spk_turn_sessions_clear" not in server)
check("no_unused_prompt_aliases",
      all(not hasattr(speaking_prompts, n) for n in
          ["EXAMINER_SYSTEM", "PARTNER_SYSTEM", "PART2_TASK", "PART3_PROMPT",
           "PART4_QUESTIONS"]))
check("no_report_system", not hasattr(speaking_report, "REPORT_SYSTEM"))

for name, result in out.items():
    print("%-32s %s" % (name, result))
if failed:
    print("\nFAILED: " + ", ".join(failed))
    sys.exit(1)
print("\nOK: %d checks" % len(out))
