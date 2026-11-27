#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speaking v3 exam state machine, session storage, and report generator.

Privacy contract:
- Session files (`data/speaking_v3/sessions/<id>.json`, mode 0600) store ONLY
  exam state, counters, boolean flags, and numeric micro-scores.
- NEVER persist audio or candidate transcripts to disk.
- NEVER return candidate transcripts in HTTP responses.
- Sessions expire automatically after 24 hours.
- Report returns bands `{grammar_vocabulary, discourse, interactive}` (0-5)
  plus comments — NEVER pronunciation.
"""
import base64
import concurrent.futures
import os
import re
import secrets
import threading
import time
from datetime import date

import store
from speaking_v3 import catalog, tone, validation, voice

SESSION_TTL_S = 24 * 3600
MAX_RETRIES = 2
_SAFE_SID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_SESS_LOCK = threading.RLock()


# ---------------------------------------------------------------------------
# Session persistence (24 h expiry, zero audio/transcript on disk)
# ---------------------------------------------------------------------------
def _sessions_dir():
    return os.path.join(store.data_dir(), "speaking_v3", "sessions")


def _session_path(session_id):
    sid = str(session_id or "").strip()
    if not _SAFE_SID_RE.fullmatch(sid):
        return None
    root = _sessions_dir()
    cand = os.path.realpath(os.path.join(root, f"{sid}.json"))
    if not cand.startswith(os.path.realpath(root) + os.sep):
        return None
    return cand


def prune_expired_sessions(now=None):
    """Remove session files older than 24 hours."""
    ts = time.time() if now is None else float(now)
    d = _sessions_dir()
    if not os.path.isdir(d):
        return 0
    removed = 0
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        p = os.path.join(d, name)
        rec = store.read_json_private(p, None)
        expired = False
        if not isinstance(rec, dict):
            expired = True
        else:
            created = float(rec.get("updated_at") or rec.get("created_at") or 0)
            if ts - created > SESSION_TTL_S:
                expired = True
        if expired:
            try:
                os.remove(p)
                removed += 1
            except OSError:
                pass
    return removed


def _save_session(sess):
    sess["updated_at"] = time.time()
    d = _sessions_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    path = _session_path(sess["session_id"])
    # Defence in depth: strip any forbidden keys before writing
    for forbidden in ("transcript", "transcripts", "audio", "audio_b64", "candidate_text"):
        sess.pop(forbidden, None)
    store.write_json_private(path, sess)


def load_session(uid, session_id, now=None):
    """Load an active, unexpired session owned by `uid`, or return (None, err)."""
    ts = time.time() if now is None else float(now)
    path = _session_path(session_id)
    if not path or not os.path.isfile(path):
        return None, "session_not_found"
    sess = store.read_json_private(path, None)
    if not isinstance(sess, dict) or sess.get("uid") != uid:
        return None, "session_not_found"
    stamp = float(sess.get("updated_at") or sess.get("created_at") or 0)
    if ts - stamp > SESSION_TTL_S:
        try:
            os.remove(path)
        except OSError:
            pass
        return None, "session_expired"
    return sess, None


def delete_session(uid, session_id):
    with _SESS_LOCK:
        sess, err = load_session(uid, session_id)
        if err:
            return False
        path = _session_path(session_id)
        try:
            os.remove(path)
            return True
        except OSError:
            return False


def forget_user_sessions(uid):
    """GDPR cleanup: remove every Speaking v3 session file belonging to `uid`."""
    with _SESS_LOCK:
        d = _sessions_dir()
        if not os.path.isdir(d):
            return
        for name in os.listdir(d):
            if not name.endswith(".json"):
                continue
            p = os.path.join(d, name)
            rec = store.read_json_private(p, None)
            if isinstance(rec, dict) and rec.get("uid") == uid:
                try:
                    os.remove(p)
                except OSError:
                    pass


def _lc_first(q):
    s = str(q or "").strip()
    if not s:
        return s
    if s[0].isupper() and not re.match(r"^I(?:'|\b)", s) and not s.startswith("TV"):
        return s[0].lower() + s[1:]
    return s


# ---------------------------------------------------------------------------
# Helpers: resolve test, pick Part 1/4 questions, build UI & audio clips
# ---------------------------------------------------------------------------
def _resolve_test(uid, sess):
    if sess.get("own_task_id"):
        return catalog.get_own_task_as_test(uid, sess["own_task_id"])
    return catalog.get_test(sess.get("test_id"))


def _select_part1_questions(test):
    """Select 4 questions from the PDF's Part 1 categories (at least 1 per category)."""
    cats = test["parts"]["1"]["categories"]
    picked = []
    for cat in cats:
        qs = cat.get("questions") or []
        if qs:
            picked.append(qs[0])
    # Add a second question from the first category that has >=2 questions
    for cat in cats:
        qs = cat.get("questions") or []
        if len(qs) >= 2 and len(picked) < 4:
            picked.append(qs[1])
            break
    # Ensure at least 3 questions even for small own tasks
    if len(picked) < 3 and cats and cats[0].get("questions"):
        for q in cats[0]["questions"]:
            if q not in picked:
                picked.append(q)
            if len(picked) >= 3:
                break
    return picked[:4]


def _select_part4_questions(test):
    qs = test["parts"]["4"].get("questions") or []
    return qs[:4] if len(qs) >= 4 else qs


def _part_duration(test, part_num):
    if part_num not in (1, 2, 3, 4):
        return 0
    return int(test["parts"][str(part_num)].get("duration_seconds") or (120 if part_num == 1 else 240))


def _build_ui(test, phase, step, target_part):
    if phase == "intro":
        return {
            "part": target_part,
            "timer_seconds": 0,
            "images": [],
            "card": None,
        }
    if phase == "finished":
        return {
            "part": target_part,
            "timer_seconds": 0,
            "images": [],
            "card": None,
        }
    if phase == "part1":
        return {
            "part": 1,
            "timer_seconds": _part_duration(test, 1),
            "images": [],
            "card": None,
        }
    if phase == "part2":
        p2 = test["parts"]["2"]
        if step in ("user_long_turn", "user_compare_followup", "partner_followup"):
            imgs = list(p2["task1"].get("images") or [])
            sub = 60 if step == "user_long_turn" else 30
        else:
            imgs = list(p2["task2"].get("images") or [])
            sub = 60 if step == "partner_long_turn" else 30
        return {
            "part": 2,
            "timer_seconds": _part_duration(test, 2),
            "turn_seconds": sub,
            "images": imgs,
            "card": None,
        }
    if phase == "part3":
        p3 = test["parts"]["3"]
        sub = (
            int(p3.get("prep_seconds", 15)) if step == "prep"
            else int(p3.get("discussion_seconds", 120)) if step.startswith("discussion")
            else int(p3.get("decision_seconds", 60))
        )
        return {
            "part": 3,
            "timer_seconds": _part_duration(test, 3),
            "subtimer_seconds": sub,
            "images": [],
            "card": p3.get("card_image"),
        }
    if phase == "part4":
        return {
            "part": 4,
            "timer_seconds": _part_duration(test, 4),
            "images": [],
            "card": None,
        }
    return {"part": target_part, "timer_seconds": 0, "images": [], "card": None}


def _synth_one_clip(clip, partner_voice):
    wav, err = voice.synthesize_speech(
        clip["text"],
        role=clip["speaker"],
        partner_voice=partner_voice,
        cacheable=bool(clip.get("cacheable", False)),
    )
    if err:
        return None, err
    return {
        "speaker": clip["speaker"],
        "audio_b64": base64.b64encode(wav).decode("ascii"),
        "mime": "audio/wav",
        "step": clip.get("step", ""),
        "ui": clip.get("ui"),
    }, None


def _synth_sequence(clips, partner_voice):
    """Synthesise an ordered list of `{speaker, text, step, ui, cacheable}` clips.

    Synthesises multi-clip turns concurrently with ThreadPoolExecutor while
    strictly preserving clip order. Strips `text` completely from the output
    so no spoken transcript/script ever leaks in HTTP responses.
    """
    if not clips:
        return [], None
    if len(clips) == 1:
        item, err = _synth_one_clip(clips[0], partner_voice)
        return ([item], None) if not err else (None, err)

    workers = min(len(clips), 4)
    results = [None] * len(clips)
    first_err = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(_synth_one_clip, clip, partner_voice): idx
            for idx, clip in enumerate(clips)
        }
        for fut in concurrent.futures.as_completed(future_map):
            idx = future_map[fut]
            item, err = fut.result()
            if err and first_err is None:
                first_err = err
            results[idx] = item
    if first_err:
        return None, first_err
    return results, None


def _cast_from_test(test):
    """Extract explicit partner_sex and examiner name/sex with safe defaults."""
    partner = test.get("partner") if isinstance(test, dict) and isinstance(test.get("partner"), dict) else {}
    examiner = test.get("examiner") if isinstance(test, dict) and isinstance(test.get("examiner"), dict) else {}
    partner_sex = catalog.normalize_sex(partner.get("sex"))
    examiner_name = tone.resolve_examiner_name(examiner.get("name"))
    examiner_sex = catalog.normalize_sex(examiner.get("sex"))
    return partner_sex, examiner_name, examiner_sex


def _public_state(sess):
    st = {
        "phase": sess["phase"],
        "step": sess["step"],
        "part": sess["current_part"],
        "target_part": sess["target_part"],
        "question_index": sess.get("q_idx", 0),
        "retries": sess.get("step_retries", 0),
        "partner_sex": catalog.normalize_sex(sess.get("partner_sex")),
        "examiner_name": tone.resolve_examiner_name(sess.get("examiner_name")),
        "examiner_sex": catalog.normalize_sex(sess.get("examiner_sex")),
    }
    if sess.get("phase") == "part3":
        st["covered_count"] = len(sess.get("covered_options") or [])
    return st


def _enter_part(sess, test, part_num, with_transition=False):
    """Transition `sess` into `part_num` (1..4) and return examiner clips."""
    clips = []
    partner_name = test["partner"]["name"]
    cand_name = sess.get("candidate_name") or "Candidate"
    sess["current_part"] = part_num
    sess["part_started_at"] = time.time()
    sess["q_idx"] = 0
    sess["step_retries"] = 0

    if part_num == 1:
        sess["phase"] = "part1"
        sess["step"] = "q_0"
        qs = _select_part1_questions(test)
        p1_open = test["parts"]["1"]["opening"]
        q0 = qs[0]["text"]
        ui = _build_ui(test, "part1", "q_0", sess["target_part"])
        prefix = f"{tone.part_transition(1)} " if with_transition else "Thank you. "
        clips.append({
            "speaker": "examiner",
            "text": f"{prefix}{p1_open} {cand_name}, {_lc_first(q0)}",
            "step": "part1_q_0",
            "ui": ui,
            "cacheable": False,
        })
        return clips

    if part_num == 2:
        sess["phase"] = "part2"
        sess["step"] = "user_long_turn"
        p2 = test["parts"]["2"]
        t1 = p2["task1"]
        ui = _build_ui(test, "part2", "user_long_turn", sess["target_part"])
        prefix = f"{tone.part_transition(2)} " if with_transition else "Thank you. "
        intro_t1 = t1["intro"].format(candidate=cand_name, partner=partner_name)
        text = f"{prefix}{p2['opening']} {intro_t1} {t1['prompt']} {t1['check']}"
        clips.append({
            "speaker": "examiner",
            "text": text,
            "step": "part2_user_long_turn",
            "ui": ui,
            "cacheable": False,
        })
        return clips

    if part_num == 3:
        sess["phase"] = "part3"
        sess["step"] = "prep"
        sess["covered_options"] = []
        sess["focus_option"] = ""
        sess["part3_meta_used"] = False
        sess["part3_dec_started_at_elapsed"] = 0.0
        p3 = test["parts"]["3"]
        ui = _build_ui(test, "part3", "prep", sess["target_part"])
        prefix = f"{tone.part_transition(3)} " if with_transition else "Thank you. "
        clips.append({
            "speaker": "examiner",
            "text": f"{prefix}{p3['opening']}",
            "step": "part3_prep",
            "ui": ui,
            "cacheable": True,
        })
        return clips

    # Part 4 (Round 0 = odd 1-based: examiner asks user first)
    sess["phase"] = "part4"
    sess["step"] = "q_0_user"
    qs = _select_part4_questions(test)
    q0 = qs[0]["text"]
    ui = _build_ui(test, "part4", "q_0_user", sess["target_part"])
    prefix = f"{tone.part_transition(4)} " if with_transition else "Thank you. "
    clips.append({
        "speaker": "examiner",
        "text": f"{prefix}{cand_name}, {_lc_first(q0)}",
        "step": "part4_q_0",
        "ui": ui,
        "cacheable": False,
    })
    return clips


def _finish_current_part(sess, test):
    """Close current part and either advance to next part (full) or end exam."""
    cur = sess["current_part"]
    target = sess["target_part"]
    clips = []

    if target == 0 and cur < 4:
        ui_end = _build_ui(test, sess["phase"], sess["step"], target)
        clips.append({
            "speaker": "examiner",
            "text": tone.CANONICAL["part_end"],
            "step": f"part{cur}_end",
            "ui": ui_end,
            "cacheable": True,
        })
        clips.extend(_enter_part(sess, test, cur + 1, with_transition=True))
        return clips, False

    sess["phase"] = "finished"
    sess["step"] = "done"
    sess["done"] = True
    ui_done = _build_ui(test, "finished", "done", target)
    end_text = (
        f"{tone.CANONICAL['part_end']} {tone.CANONICAL['test_end']}"
        if target == 0 or cur == 4
        else tone.CANONICAL["part_end"]
    )
    clips.append({
        "speaker": "examiner",
        "text": end_text,
        "step": "done",
        "ui": ui_done,
        "cacheable": True,
    })
    return clips, True


# ---------------------------------------------------------------------------
# Public API: create_session
# ---------------------------------------------------------------------------
def create_session(uid, test_id=None, part=0, own_task_id=None,
                   tz_offset_minutes=None, hour=None):
    """Create a new Speaking v3 session starting in mandatory `intro` state.

    Returns ``(response_dict, http_status, error_str)``.
    """
    try:
        target_part = int(part) if part is not None else 0
    except (TypeError, ValueError):
        return None, 422, "invalid_part"
    if target_part not in (0, 1, 2, 3, 4):
        return None, 422, "invalid_part"

    if own_task_id:
        test = catalog.get_own_task_as_test(uid, own_task_id)
        if not test:
            return None, 404, "own_task_not_found"
        # If own task is single-part and user requested part=0, match its part unless full
        own_part = test.get("own_task_part", 0)
        if own_part in (1, 2, 3, 4) and target_part == 0:
            target_part = own_part
        elif own_part in (1, 2, 3, 4) and target_part != own_part:
            return None, 422, "part_mismatch_own_task"
        resolved_test_id = test["id"]
    else:
        test = catalog.get_test(test_id or "01")
        if not test:
            return None, 404, "test_not_found"
        resolved_test_id = test["id"]

    partner_sex, examiner_name, examiner_sex = _cast_from_test(test)

    greeting_text = tone.opening_greeting(
        hour=hour,
        tz_offset_minutes=tz_offset_minutes,
        examiner_name=examiner_name,
    )
    wav, tts_err = voice.synthesize_speech(
        greeting_text,
        role="examiner",
        partner_voice=voice.partner_voice_for(test["partner"].get("sex"), test["partner"].get("voice")),
        cacheable=True,
    )
    if tts_err:
        status = 503 if tts_err == "speech_not_configured" else 502
        return None, status, tts_err

    sid = "spk3_" + secrets.token_urlsafe(12)
    now = time.time()
    sess = {
        "session_id": sid,
        "uid": uid,
        "test_id": resolved_test_id,
        "own_task_id": own_task_id or None,
        "target_part": target_part,
        "current_part": 0,
        "phase": "intro",
        "step": "greeting",
        "q_idx": 0,
        "step_retries": 0,
        "candidate_name": "",
        "candidate_home": "",
        "partner_name": test["partner"]["name"],
        "partner_sex": partner_sex,
        "examiner_name": examiner_name,
        "examiner_sex": examiner_sex,
        "done": False,
        "created_at": now,
        "updated_at": now,
        "part_started_at": 0.0,
        "flags": {
            "name_ok": None,
            "home_ok": None,
            "off_topic_turns": 0,
            "non_english_turns": 0,
            "silence_turns": 0,
            "skipped_turns": 0,
            "part2_compared": None,
            "retries_total": 0,
        },
        "scores": [],
        "turn_count": 0,
    }
    with _SESS_LOCK:
        prune_expired_sessions(now)
        _save_session(sess)

    ui = _build_ui(test, "intro", "greeting", target_part)
    return {
        "session_id": sid,
        "speaker": "examiner",
        "audio_b64": base64.b64encode(wav).decode("ascii"),
        "mime": "audio/wav",
        "partner_sex": partner_sex,
        "examiner_name": examiner_name,
        "examiner_sex": examiner_sex,
        "state": {
            "phase": "intro",
            "step": "greeting",
            "part": 0,
            "target_part": target_part,
            "partner_sex": partner_sex,
            "examiner_name": examiner_name,
            "examiner_sex": examiner_sex,
        },
        "ui": ui,
    }, 200, None


# ---------------------------------------------------------------------------
# Public API: handle_turn
# ---------------------------------------------------------------------------
def _record_turn_score(sess, text, accepted, part, compared_photos=None):
    """Score the utterance in memory and store ONLY numeric scores."""
    ms = validation.micro_score_turn(
        text, accepted=accepted, part=part, compared_photos=compared_photos
    )
    sess["scores"].append(ms)
    sess["turn_count"] = int(sess.get("turn_count") or 0) + 1


def _handle_retry(sess, test, reason, canonical_text, cacheable=True):
    """Apply retry policy (silence never burns a semantic retry; max 2 semantic retries)."""
    partner_voice = voice.partner_voice_for(test["partner"].get("sex"), test["partner"].get("voice"))
    ui = _build_ui(test, sess["phase"], sess["step"], sess["target_part"])

    if reason == "silence":
        sess["flags"]["silence_turns"] += 1
        clips = [{
            "speaker": "examiner",
            "text": tone.CANONICAL["silence"],
            "step": sess["step"],
            "ui": ui,
            "cacheable": True,
        }]
        audio_clips, err = _synth_sequence(clips, partner_voice)
        if err:
            return None, (503 if err == "speech_not_configured" else 502), err
        _save_session(sess)
        return {
            "accepted": False,
            "retry": True,
            "reason": "silence",
            "speaker": "examiner",
            "audio_b64": audio_clips[0]["audio_b64"],
            "mime": "audio/wav",
            "sequence": audio_clips,
            "state": _public_state(sess),
            "ui": ui,
            "done": False,
        }, 200, None

    if reason == "non_english":
        sess["flags"]["non_english_turns"] += 1
    elif reason == "off_topic":
        sess["flags"]["off_topic_turns"] += 1

    sess["step_retries"] = int(sess.get("step_retries") or 0) + 1
    sess["flags"]["retries_total"] += 1

    if sess["step_retries"] <= MAX_RETRIES:
        text = tone.CANONICAL["non_english"] if reason == "non_english" else canonical_text
        clips = [{
            "speaker": "examiner",
            "text": text,
            "step": sess["step"],
            "ui": ui,
            "cacheable": cacheable and reason != "off_topic",
        }]
        audio_clips, err = _synth_sequence(clips, partner_voice)
        if err:
            return None, (503 if err == "speech_not_configured" else 502), err
        _save_session(sess)
        return {
            "accepted": False,
            "retry": True,
            "reason": reason,
            "speaker": "examiner",
            "audio_b64": audio_clips[0]["audio_b64"],
            "mime": "audio/wav",
            "sequence": audio_clips,
            "state": _public_state(sess),
            "ui": ui,
            "done": False,
        }, 200, None

    # Max retries exceeded -> caller will advance and mark flag!
    return None, 0, "max_retries"


def handle_turn(uid, session_id, audio_b64="", mime="audio/wav",
                action=None, time_up=False, elapsed_part_seconds=None,
                test_transcript=None):
    """Process one candidate turn (or Part 3 prep_done action).

    Returns ``(response_dict, http_status, error_str)``.
    NEVER returns or persists any candidate transcript.
    """
    with _SESS_LOCK:
        sess, load_err = load_session(uid, session_id)
        if load_err:
            code = 410 if load_err == "session_expired" else 404
            return None, code, load_err
        if sess.get("done"):
            return None, 409, "session_already_finished"

        test = _resolve_test(uid, sess)
        if not test:
            return None, 404, "test_not_found"

        partner_name = test["partner"]["name"]
        partner_voice = voice.partner_voice_for(test["partner"].get("sex"), test["partner"].get("voice"))

        # Special non-audio transition: Part 3 15-second prep timer completed
        if sess["phase"] == "part3" and sess["step"] == "prep" and action == "prep_done":
            p3 = test["parts"]["3"]
            opts = list(p3.get("options") or [])
            first_opt = opts[0] if opts else ""
            sess["step"] = "discussion_0"
            sess["q_idx"] = 0
            sess["step_retries"] = 0
            sess["focus_option"] = first_opt
            sess["covered_options"] = [first_opt] if first_opt else []
            sess["part3_meta_used"] = False
            sess["part3_dec_started_at_elapsed"] = 0.0
            ui = _build_ui(test, "part3", "discussion_0", sess["target_part"])
            partner_open = voice.generate_partner_line(
                "part3_open", test,
                question_text=p3.get("card_question", ""),
                focus_option=first_opt,
            )
            clips = [
                {
                    "speaker": "examiner",
                    "text": p3["start_discussion"],
                    "step": "part3_start_discussion",
                    "ui": ui,
                    "cacheable": True,
                },
                {
                    "speaker": "partner",
                    "text": partner_open,
                    "step": "part3_partner_open",
                    "ui": ui,
                    "cacheable": True,
                },
            ]
            audio_clips, err = _synth_sequence(clips, partner_voice)
            if err:
                return None, (503 if err == "speech_not_configured" else 502), err
            _save_session(sess)
            return {
                "accepted": True,
                "retry": False,
                "speaker": audio_clips[0]["speaker"],
                "audio_b64": audio_clips[0]["audio_b64"],
                "mime": "audio/wav",
                "sequence": audio_clips,
                "state": _public_state(sess),
                "ui": ui,
                "done": False,
            }, 200, None

        # Step 1: Transcribe audio strictly in memory (never persisted, never returned)
        transcript, stt_err = voice.transcribe_audio(
            audio_b64, mime, test_transcript=test_transcript
        )
        if stt_err:
            status = (
                503 if stt_err == "speech_not_configured"
                else 413 if stt_err == "audio_too_large"
                else 422 if stt_err == "invalid_audio"
                else 502
            )
            return None, status, stt_err

        # Check if part timer expired (only outside intro)
        part_expired = False
        if sess["phase"] in ("part1", "part2", "part3", "part4"):
            dur = _part_duration(test, sess["current_part"])
            if time_up:
                part_expired = True
            elif elapsed_part_seconds is not None:
                try:
                    if float(elapsed_part_seconds) >= dur:
                        part_expired = True
                except (TypeError, ValueError):
                    pass

        phase = sess["phase"]
        step = sess["step"]
        accepted = True
        clips = []
        done = False

        # ---------------------------------------------------------------
        # PHASE: INTRO (mandatory, outside exam timer)
        # ---------------------------------------------------------------
        if phase == "intro" and step == "greeting":
            ok, clean_name, reason = validation.validate_name(transcript)
            if not ok:
                resp, code, r_err = _handle_retry(
                    sess, test, reason, tone.CANONICAL["name_retry"], cacheable=True
                )
                if r_err != "max_retries":
                    return resp, code, r_err
                # Max 2 retries reached -> advance & flag name_ok = False
                accepted = False
                sess["flags"]["name_ok"] = False
                sess["candidate_name"] = "Candidate"
            else:
                sess["flags"]["name_ok"] = True
                sess["candidate_name"] = clean_name

            sess["step_retries"] = 0
            sess["step"] = "ask_home"
            ui_intro = _build_ui(test, "intro", "ask_home", sess["target_part"])
            # Partner responds AFTER user spoke!
            partner_line = voice.generate_partner_line("intro_name", test)
            examiner_line = tone.CANONICAL["ask_home_template"].format(
                candidate=sess["candidate_name"]
            )
            clips = [
                {"speaker": "partner", "text": partner_line, "step": "partner_name", "ui": ui_intro, "cacheable": True},
                {"speaker": "examiner", "text": examiner_line, "step": "ask_home", "ui": ui_intro, "cacheable": False},
            ]

        elif phase == "intro" and step == "ask_home":
            ok, clean_home, reason = validation.validate_home(transcript)
            if not ok:
                resp, code, r_err = _handle_retry(
                    sess, test, reason, tone.CANONICAL["home_retry"], cacheable=True
                )
                if r_err != "max_retries":
                    return resp, code, r_err
                accepted = False
                sess["flags"]["home_ok"] = False
                sess["candidate_home"] = ""
            else:
                sess["flags"]["home_ok"] = True
                sess["candidate_home"] = clean_home

            sess["step_retries"] = 0
            ui_intro = _build_ui(test, "intro", "partner_home", sess["target_part"])
            ex_ask_partner = tone.CANONICAL["ask_partner_home_template"].format(
                partner=partner_name
            )
            partner_home_line = voice.generate_partner_line("intro_home", test)
            clips = [
                {"speaker": "examiner", "text": ex_ask_partner, "step": "ask_partner_home", "ui": ui_intro, "cacheable": True},
                {"speaker": "partner", "text": partner_home_line, "step": "partner_home", "ui": ui_intro, "cacheable": True},
            ]
            # Jump straight to requested part (or Part 1 for full exam)
            first_part = 1 if sess["target_part"] == 0 else sess["target_part"]
            clips.extend(_enter_part(sess, test, first_part, with_transition=(first_part != 1)))

        # ---------------------------------------------------------------
        # PHASE: PART 1 (2 min, 3-4 questions from PDF, alternating user & partner)
        # ---------------------------------------------------------------
        elif phase == "part1":
            qs = _select_part1_questions(test)
            idx = min(int(sess.get("q_idx") or 0), len(qs) - 1)
            q_obj = qs[idx]
            ok, reason = validation.validate_topic_answer(
                transcript,
                question_text=q_obj["text"],
                topic=q_obj.get("topic", ""),
                keywords=q_obj.get("keywords"),
                part=1,
            )
            if not ok:
                resp, code, r_err = _handle_retry(
                    sess, test, reason,
                    tone.off_topic_prompt(q_obj.get("topic") or "that question"),
                    cacheable=False,
                )
                if r_err != "max_retries":
                    return resp, code, r_err
                accepted = False

            _record_turn_score(sess, transcript, accepted=accepted, part=1)
            sess["step_retries"] = 0
            ui_p1 = _build_ui(test, "part1", sess["step"], sess["target_part"])

            # Partner also gets examined on Part 1!
            partner_q = qs[(idx + 1) % len(qs)]["text"] if len(qs) > 1 else q_obj["text"]
            partner_ans = voice.generate_partner_line("part1", test, question_text=partner_q, turn_index=idx)
            clips.append({
                "speaker": "examiner",
                "text": f"Thank you. {partner_name}, {_lc_first(partner_q)}",
                "step": f"part1_partner_q_{idx}",
                "ui": ui_p1,
                "cacheable": True,
            })
            clips.append({
                "speaker": "partner",
                "text": partner_ans,
                "step": f"part1_partner_a_{idx}",
                "ui": ui_p1,
                "cacheable": True,
            })

            next_idx = idx + 1
            max_user_turns = min(3, len(qs))
            if part_expired or next_idx >= max_user_turns:
                end_clips, done = _finish_current_part(sess, test)
                clips.extend(end_clips)
            else:
                sess["q_idx"] = next_idx
                sess["step"] = f"q_{next_idx}"
                nq = qs[next_idx]["text"]
                cand_name = sess.get("candidate_name") or "Candidate"
                clips.append({
                    "speaker": "examiner",
                    "text": f"Thank you. {cand_name}, {_lc_first(nq)}",
                    "step": f"part1_q_{next_idx}",
                    "ui": ui_p1,
                    "cacheable": False,
                })

        # ---------------------------------------------------------------
        # PHASE: PART 2 (4 min: user 1m + partner 30s; partner 1m + user 30s)
        # ---------------------------------------------------------------
        elif phase == "part2":
            p2 = test["parts"]["2"]
            t1 = p2["task1"]
            t2 = p2["task2"]
            cand_name = sess.get("candidate_name") or "Candidate"

            if step == "user_long_turn":
                # Part 2 long turn: never interrupt for off-topic validity!
                # Only retry for complete silence or non-English.
                if not transcript:
                    resp, code, r_err = _handle_retry(
                        sess, test, "silence", tone.CANONICAL["silence"], cacheable=True
                    )
                    return resp, code, r_err
                if validation.is_non_english(transcript):
                    resp, code, r_err = _handle_retry(
                        sess, test, "non_english", tone.CANONICAL["non_english"], cacheable=True
                    )
                    if r_err != "max_retries":
                        return resp, code, r_err
                    accepted = False

                compared = validation.did_compare_photos(transcript)
                sess["flags"]["part2_compared"] = compared
                _record_turn_score(sess, transcript, accepted=accepted, part=2, compared_photos=compared)
                sess["step_retries"] = 0

                if not compared:
                    # Examiner asks a follow-up because the candidate didn't compare the photos
                    sess["step"] = "user_compare_followup"
                    ui_t1 = _build_ui(test, "part2", "user_compare_followup", sess["target_part"])
                    clips.append({
                        "speaker": "examiner",
                        "text": f"Thank you. {t1.get('compare_followup', 'Which photograph do you think shows a more challenging situation?')}",
                        "step": "part2_compare_followup",
                        "ui": ui_t1,
                        "cacheable": False,
                    })
                else:
                    clips.extend(_part2_partner_sequence(sess, test))

            elif step == "user_compare_followup":
                ok, reason = validation.validate_topic_answer(
                    transcript,
                    question_text=t1.get("compare_followup", ""),
                    topic=t1.get("topic", "the photographs"),
                    keywords=t1.get("keywords"),
                    part=2,
                )
                if not ok and reason in ("silence", "non_english"):
                    resp, code, r_err = _handle_retry(
                        sess, test, reason, tone.CANONICAL["non_english"], cacheable=True
                    )
                    if r_err != "max_retries":
                        return resp, code, r_err
                    accepted = False
                _record_turn_score(sess, transcript, accepted=accepted, part=2)
                sess["step_retries"] = 0
                clips.extend(_part2_partner_sequence(sess, test))

            elif step == "user_followup":
                ok, reason = validation.validate_topic_answer(
                    transcript,
                    question_text=t2.get("followup_to_user", ""),
                    topic=t2.get("topic", "your partner's photographs"),
                    keywords=t2.get("keywords"),
                    part=2,
                )
                if not ok:
                    resp, code, r_err = _handle_retry(
                        sess, test, reason,
                        tone.off_topic_prompt(t2.get("topic") or "the photographs"),
                        cacheable=False,
                    )
                    if r_err != "max_retries":
                        return resp, code, r_err
                    accepted = False

                _record_turn_score(sess, transcript, accepted=accepted, part=2)
                sess["step_retries"] = 0
                end_clips, done = _finish_current_part(sess, test)
                clips.extend(end_clips)

        # ---------------------------------------------------------------
        # PHASE: PART 3 (4 min: 15s prep + ~2 min discussion + ~1 min decision)
        # ---------------------------------------------------------------
        elif phase == "part3":
            p3 = test["parts"]["3"]
            opts = list(p3.get("options") or [])
            # If user spoke directly during prep, seamlessly treat as discussion_0
            if step == "prep":
                step = "discussion_0"
                sess["step"] = "discussion_0"
                sess["q_idx"] = 0
                if not sess.get("covered_options") and opts:
                    sess["focus_option"] = opts[0]
                    sess["covered_options"] = [opts[0]]

            elapsed_val = 0.0
            if elapsed_part_seconds is not None:
                try:
                    elapsed_val = float(elapsed_part_seconds)
                except (TypeError, ValueError):
                    elapsed_val = 0.0

            # Meta-turn at the start of discussion ("Can I start?" / "Shall I start?" / "I'll start"):
            # Partner replies "Yes, go ahead." and does NOT count as a content turn.
            if (
                step.startswith("discussion")
                and int(sess.get("q_idx") or 0) == 0
                and not sess.get("part3_meta_used")
                and validation.is_part3_meta_start(transcript)
            ):
                sess["part3_meta_used"] = True
                sess["step_retries"] = 0
                ui_disc = _build_ui(test, "part3", step, sess["target_part"])
                go_line = voice.generate_partner_line("part3_meta_go_ahead", test)
                clips = [{
                    "speaker": "partner",
                    "text": go_line,
                    "step": "part3_partner_meta_go",
                    "ui": ui_disc,
                    "cacheable": True,
                }]
                audio_clips, tts_err = _synth_sequence(clips, partner_voice)
                if tts_err:
                    return None, (503 if tts_err == "speech_not_configured" else 502), tts_err
                _save_session(sess)
                return {
                    "accepted": True,
                    "retry": False,
                    "meta_turn": True,
                    "speaker": audio_clips[0]["speaker"],
                    "audio_b64": audio_clips[0]["audio_b64"],
                    "mime": "audio/wav",
                    "sequence": audio_clips,
                    "state": _public_state(sess),
                    "ui": ui_disc,
                    "done": False,
                }, 200, None

            ok, reason = validation.validate_topic_answer(
                transcript,
                question_text=p3.get("card_question", ""),
                topic=p3.get("topic", "the task on the card"),
                keywords=p3.get("keywords"),
                part=3,
                allow_cooperative=True,
            )
            if not ok:
                resp, code, r_err = _handle_retry(
                    sess, test, reason,
                    tone.off_topic_prompt(p3.get("topic") or "the task"),
                    cacheable=False,
                )
                if r_err != "max_retries":
                    return resp, code, r_err
                accepted = False

            # Track covered card options strictly from the test's own option list (never candidate text)
            covered = list(sess.get("covered_options") or [])
            mentioned = validation.detect_mentioned_options(transcript, opts) if accepted else []
            for m_opt in mentioned:
                if m_opt in opts and m_opt not in covered:
                    covered.append(m_opt)
            cur_focus = mentioned[-1] if mentioned else (sess.get("focus_option") or (opts[0] if opts else ""))
            if cur_focus and cur_focus in opts and cur_focus not in covered:
                covered.append(cur_focus)

            _record_turn_score(sess, transcript, accepted=accepted, part=3)
            sess["step_retries"] = 0

            if step.startswith("discussion"):
                idx = int(sess.get("q_idx") or 0)
                prep_s = int(p3.get("prep_seconds", 15))
                disc_elapsed = max(0.0, elapsed_val - prep_s) if elapsed_part_seconds is not None else 0.0
                sess["covered_options"] = covered

                if part_expired:
                    end_clips, done = _finish_current_part(sess, test)
                    clips.extend(end_clips)
                elif idx >= 4 or disc_elapsed >= 110:
                    # ~110-120s of discussion or 5 user turns -> examiner decision_prompt + partner opens negotiation
                    sess["step"] = "decision_0"
                    sess["q_idx"] = 0
                    sess["part3_dec_started_at_elapsed"] = elapsed_val
                    prop_opt = covered[0] if covered else (opts[0] if opts else "")
                    sess["focus_option"] = prop_opt
                    ui_dec = _build_ui(test, "part3", "decision_0", sess["target_part"])
                    partner_dec_open = voice.generate_partner_line(
                        "part3_decision_open", test,
                        question_text=p3.get("decision_prompt", ""),
                        focus_option=prop_opt,
                        covered_options=covered,
                    )
                    clips.append({
                        "speaker": "examiner",
                        "text": p3["decision_prompt"],
                        "step": "part3_decision_prompt",
                        "ui": ui_dec,
                        "cacheable": True,
                    })
                    clips.append({
                        "speaker": "partner",
                        "text": partner_dec_open,
                        "step": "part3_partner_dec_open",
                        "ui": ui_dec,
                        "cacheable": True,
                    })
                else:
                    # Pure candidate-to-candidate discussion: NO examiner clip between turns!
                    uncovered = [o for o in opts if o not in covered]
                    if uncovered:
                        next_opt = uncovered[0]
                    elif opts:
                        others = [o for o in opts if o != cur_focus]
                        next_opt = others[idx % len(others)] if others else opts[0]
                    else:
                        next_opt = ""
                    if next_opt and next_opt not in covered:
                        covered.append(next_opt)
                    sess["covered_options"] = covered
                    sess["focus_option"] = next_opt or cur_focus

                    ui_disc = _build_ui(test, "part3", step, sess["target_part"])
                    partner_reply = voice.generate_partner_line(
                        "part3_discussion", test,
                        question_text=p3.get("card_question", ""),
                        turn_index=idx,
                        candidate_summary=transcript if accepted else "",
                        focus_option=cur_focus,
                        next_option=next_opt,
                        covered_options=covered,
                    )
                    clips.append({
                        "speaker": "partner",
                        "text": partner_reply,
                        "step": f"part3_partner_disc_{idx}",
                        "ui": ui_disc,
                        "cacheable": False,
                    })
                    sess["q_idx"] = idx + 1
                    sess["step"] = f"discussion_{idx + 1}"

            else:
                # Decision phase (~60 s or up to 3 user turns): real negotiation between candidates
                idx = int(sess.get("q_idx") or 0)
                sess["covered_options"] = covered
                dec_start = float(sess.get("part3_dec_started_at_elapsed") or 0.0)
                dec_elapsed = max(0.0, elapsed_val - dec_start) if elapsed_part_seconds is not None else 0.0

                if part_expired or idx >= 2 or dec_elapsed >= 58:
                    end_clips, done = _finish_current_part(sess, test)
                    clips.extend(end_clips)
                else:
                    ui_dec = _build_ui(test, "part3", step, sess["target_part"])
                    alt_candidates = [o for o in (covered or opts) if o != cur_focus]
                    alt_opt = alt_candidates[idx % len(alt_candidates)] if alt_candidates else (opts[-1] if opts else "")
                    partner_reply = voice.generate_partner_line(
                        "part3_decision", test,
                        question_text=p3.get("decision_prompt", ""),
                        turn_index=idx,
                        candidate_summary=transcript if accepted else "",
                        focus_option=cur_focus,
                        next_option=alt_opt,
                        covered_options=covered,
                    )
                    clips.append({
                        "speaker": "partner",
                        "text": partner_reply,
                        "step": f"part3_partner_dec_{idx}",
                        "ui": ui_dec,
                        "cacheable": False,
                    })
                    sess["q_idx"] = idx + 1
                    sess["step"] = f"decision_{idx + 1}"

        # ---------------------------------------------------------------
        # PHASE: PART 4 (4 min: alternating user-first & partner-first rounds)
        # ---------------------------------------------------------------
        elif phase == "part4":
            qs = _select_part4_questions(test)
            idx = min(int(sess.get("q_idx") or 0), len(qs) - 1)
            q_obj = qs[idx]
            cand_name = sess.get("candidate_name") or "Candidate"
            is_react = step.endswith("_react")

            ok, reason = validation.validate_topic_answer(
                transcript,
                question_text=q_obj["text"],
                topic=q_obj.get("topic", ""),
                keywords=q_obj.get("keywords"),
                part=4,
                allow_cooperative=True,
            )
            if not ok:
                resp, code, r_err = _handle_retry(
                    sess, test, reason,
                    tone.off_topic_prompt(q_obj.get("topic") or "that question"),
                    cacheable=False,
                )
                if r_err != "max_retries":
                    return resp, code, r_err
                accepted = False

            _record_turn_score(sess, transcript, accepted=accepted, part=4)
            sess["step_retries"] = 0
            ui_p4 = _build_ui(test, "part4", sess["step"], sess["target_part"])

            if idx % 2 == 0 and not is_react:
                # Odd round (1st, 3rd): user answered -> examiner asks partner same question ->
                # partner gives own opinion -> examiner invites user to react to partner!
                if part_expired:
                    end_clips, done = _finish_current_part(sess, test)
                    clips.extend(end_clips)
                else:
                    partner_ans = voice.generate_partner_line(
                        "part4_answer", test,
                        question_text=q_obj["text"],
                        turn_index=idx,
                        candidate_summary=transcript if accepted else "",
                    )
                    live_llm = bool(voice.google_api_key() and not voice.is_test_mode())
                    react_prompt = (
                        f"Thank you. {cand_name}, do you agree with {partner_name}?"
                        if idx == 0
                        else f"Thank you. {cand_name}, what do you think about what {partner_name} said?"
                    )
                    clips.append({
                        "speaker": "examiner",
                        "text": f"Thank you. And you, {partner_name}?",
                        "step": f"part4_partner_q_{idx}",
                        "ui": ui_p4,
                        "cacheable": True,
                    })
                    clips.append({
                        "speaker": "partner",
                        "text": partner_ans,
                        "step": f"part4_partner_a_{idx}",
                        "ui": ui_p4,
                        "cacheable": not live_llm,
                    })
                    clips.append({
                        "speaker": "examiner",
                        "text": react_prompt,
                        "step": f"part4_user_react_q_{idx}",
                        "ui": ui_p4,
                        "cacheable": False,
                    })
                    sess["step"] = f"q_{idx}_react"

            elif idx % 2 == 0 and is_react:
                # Odd round completed: advance to next round (even round -> partner goes FIRST!)
                next_idx = idx + 1
                if part_expired or next_idx >= len(qs):
                    end_clips, done = _finish_current_part(sess, test)
                    clips.extend(end_clips)
                else:
                    nq = qs[next_idx]
                    sess["q_idx"] = next_idx
                    sess["step"] = f"q_{next_idx}_user"
                    partner_own = voice.generate_partner_line(
                        "part4_answer", test,
                        question_text=nq["text"],
                        turn_index=next_idx,
                    )
                    in_bank = nq["text"] in voice._PART4_PARTNER_BANK
                    clips.append({
                        "speaker": "examiner",
                        "text": f"Thank you. {partner_name}, {_lc_first(nq['text'])}",
                        "step": f"part4_partner_first_q_{next_idx}",
                        "ui": ui_p4,
                        "cacheable": True,
                    })
                    clips.append({
                        "speaker": "partner",
                        "text": partner_own,
                        "step": f"part4_partner_first_a_{next_idx}",
                        "ui": ui_p4,
                        "cacheable": in_bank,
                    })
                    clips.append({
                        "speaker": "examiner",
                        "text": f"Thank you. And you, {cand_name}? {_lc_first(nq['text'])}",
                        "step": f"part4_q_{next_idx}",
                        "ui": ui_p4,
                        "cacheable": False,
                    })

            else:
                # Even round (2nd, 4th): partner went first, user just answered ->
                # examiner asks partner "Do you agree?" -> partner reacts -> next round (or finish)
                partner_react = voice.generate_partner_line(
                    "part4_react", test,
                    question_text=q_obj["text"],
                    turn_index=idx,
                    candidate_summary=transcript if accepted else "",
                )
                clips.append({
                    "speaker": "examiner",
                    "text": f"Thank you. {partner_name}, do you agree?",
                    "step": f"part4_partner_react_q_{idx}",
                    "ui": ui_p4,
                    "cacheable": True,
                })
                clips.append({
                    "speaker": "partner",
                    "text": partner_react,
                    "step": f"part4_partner_react_a_{idx}",
                    "ui": ui_p4,
                    "cacheable": False,
                })

                next_idx = idx + 1
                if part_expired or next_idx >= len(qs):
                    end_clips, done = _finish_current_part(sess, test)
                    clips.extend(end_clips)
                else:
                    nq = qs[next_idx]
                    sess["q_idx"] = next_idx
                    sess["step"] = f"q_{next_idx}_user"
                    clips.append({
                        "speaker": "examiner",
                        "text": f"Thank you. {cand_name}, {_lc_first(nq['text'])}",
                        "step": f"part4_q_{next_idx}",
                        "ui": ui_p4,
                        "cacheable": False,
                    })

        # Synthesise all audio clips for this turn
        audio_clips, tts_err = _synth_sequence(clips, partner_voice)
        if tts_err:
            return None, (503 if tts_err == "speech_not_configured" else 502), tts_err

        _save_session(sess)
        final_ui = _build_ui(test, sess["phase"], sess["step"], sess["target_part"])
        return {
            "accepted": accepted,
            "retry": False,
            "speaker": audio_clips[0]["speaker"],
            "audio_b64": audio_clips[0]["audio_b64"],
            "mime": "audio/wav",
            "sequence": audio_clips,
            "state": _public_state(sess),
            "ui": final_ui,
            "done": done,
        }, 200, None


def _part2_partner_sequence(sess, test):
    """Build the Part 2 sequence after user finishes Task 1:
    Examiner asks partner Task 1 follow-up -> Partner answers (30s) ->
    Examiner gives partner Task 2 photos -> Partner monologue (1m) ->
    Examiner asks user Task 2 follow-up (30s).
    """
    p2 = test["parts"]["2"]
    t1 = p2["task1"]
    t2 = p2["task2"]
    partner_name = test["partner"]["name"]
    cand_name = sess.get("candidate_name") or "Candidate"

    ui_t1 = _build_ui(test, "part2", "partner_followup", sess["target_part"])
    ui_t2_partner = _build_ui(test, "part2", "partner_long_turn", sess["target_part"])
    ui_t2_user = _build_ui(test, "part2", "user_followup", sess["target_part"])

    sess["step"] = "user_followup"

    partner_t1_ans = voice.generate_partner_line("part2_followup", test, question_text=t1["followup_to_partner"])
    partner_t2_mono = voice.generate_partner_line("part2_monologue", test)

    return [
        {
            "speaker": "examiner",
            "text": f"Thank you. {t1['followup_to_partner'].format(candidate=cand_name, partner=partner_name)}",
            "step": "part2_ask_partner_followup",
            "ui": ui_t1,
            "cacheable": "{candidate}" not in t1["followup_to_partner"],
        },
        {
            "speaker": "partner",
            "text": partner_t1_ans,
            "step": "part2_partner_followup",
            "ui": ui_t1,
            "cacheable": True,
        },
        {
            "speaker": "examiner",
            "text": (
                f"Thank you. {t2['intro'].format(candidate=cand_name, partner=partner_name)} "
                f"{t2['prompt']} {t2['check']}"
            ),
            "step": "part2_partner_prompt",
            "ui": ui_t2_partner,
            "cacheable": "{candidate}" not in t2["intro"],
        },
        {
            "speaker": "partner",
            "text": partner_t2_mono,
            "step": "part2_partner_long_turn",
            "ui": ui_t2_partner,
            "cacheable": True,
        },
        {
            "speaker": "examiner",
            "text": f"Thank you. {t2['followup_to_user'].format(candidate=cand_name, partner=partner_name)}",
            "step": "part2_ask_user_followup",
            "ui": ui_t2_user,
            "cacheable": False,
        },
    ]


# ---------------------------------------------------------------------------
# Public API: handle_skip (demo fallback when microphone unavailable)
# ---------------------------------------------------------------------------
def handle_skip(uid, session_id):
    """Advance past the current user step with a formal examiner phrase."""
    with _SESS_LOCK:
        sess, load_err = load_session(uid, session_id)
        if load_err:
            code = 410 if load_err == "session_expired" else 404
            return None, code, load_err
        if sess.get("done"):
            return None, 409, "session_already_finished"

        test = _resolve_test(uid, sess)
        if not test:
            return None, 404, "test_not_found"

        partner_name = test["partner"]["name"]
        partner_voice = voice.partner_voice_for(test["partner"].get("sex"), test["partner"].get("voice"))
        sess["flags"]["skipped_turns"] += 1
        sess["step_retries"] = 0

        phase = sess["phase"]
        step = sess["step"]
        clips = []
        done = False

        if phase == "intro" and step == "greeting":
            sess["flags"]["name_ok"] = False
            sess["candidate_name"] = "Candidate"
            sess["step"] = "ask_home"
            ui_intro = _build_ui(test, "intro", "ask_home", sess["target_part"])
            clips = [
                {"speaker": "examiner", "text": tone.CANONICAL["skip_advance"], "step": "skip", "ui": ui_intro, "cacheable": True},
                {"speaker": "partner", "text": voice.generate_partner_line("intro_name", test), "step": "partner_name", "ui": ui_intro, "cacheable": True},
                {"speaker": "examiner", "text": tone.CANONICAL["ask_home_template"].format(candidate="Candidate"), "step": "ask_home", "ui": ui_intro, "cacheable": False},
            ]

        elif phase == "intro" and step == "ask_home":
            sess["flags"]["home_ok"] = False
            ui_intro = _build_ui(test, "intro", "partner_home", sess["target_part"])
            clips = [
                {"speaker": "examiner", "text": f"{tone.CANONICAL['skip_advance']} {tone.CANONICAL['ask_partner_home_template'].format(partner=partner_name)}", "step": "ask_partner_home", "ui": ui_intro, "cacheable": False},
                {"speaker": "partner", "text": voice.generate_partner_line("intro_home", test), "step": "partner_home", "ui": ui_intro, "cacheable": True},
            ]
            first_part = 1 if sess["target_part"] == 0 else sess["target_part"]
            clips.extend(_enter_part(sess, test, first_part, with_transition=(first_part != 1)))

        elif phase == "part1":
            qs = _select_part1_questions(test)
            idx = int(sess.get("q_idx") or 0) + 1
            if idx >= min(3, len(qs)):
                end_clips, done = _finish_current_part(sess, test)
                clips = [{"speaker": "examiner", "text": tone.CANONICAL["skip_advance"], "step": "skip", "ui": _build_ui(test, phase, step, sess["target_part"]), "cacheable": True}] + end_clips
            else:
                sess["q_idx"] = idx
                sess["step"] = f"q_{idx}"
                ui_p1 = _build_ui(test, "part1", sess["step"], sess["target_part"])
                nq = qs[idx]["text"]
                clips = [{
                    "speaker": "examiner",
                    "text": f"{tone.CANONICAL['skip_advance']} {nq}",
                    "step": f"part1_q_{idx}",
                    "ui": ui_p1,
                    "cacheable": False,
                }]

        elif phase == "part2":
            if step in ("user_long_turn", "user_compare_followup"):
                sess["flags"]["part2_compared"] = False
                ui_t1 = _build_ui(test, "part2", step, sess["target_part"])
                clips = [{"speaker": "examiner", "text": tone.CANONICAL["skip_advance"], "step": "skip", "ui": ui_t1, "cacheable": True}]
                clips.extend(_part2_partner_sequence(sess, test))
            else:
                end_clips, done = _finish_current_part(sess, test)
                clips = [{"speaker": "examiner", "text": tone.CANONICAL["skip_advance"], "step": "skip", "ui": _build_ui(test, phase, step, sess["target_part"]), "cacheable": True}] + end_clips

        elif phase == "part3":
            p3 = test["parts"]["3"]
            opts = list(p3.get("options") or [])
            if step == "prep":
                first_opt = opts[0] if opts else ""
                sess["step"] = "discussion_0"
                sess["q_idx"] = 0
                sess["focus_option"] = first_opt
                sess["covered_options"] = [first_opt] if first_opt else []
                ui_d = _build_ui(test, "part3", "discussion_0", sess["target_part"])
                partner_open = voice.generate_partner_line("part3_open", test, focus_option=first_opt)
                clips = [
                    {"speaker": "examiner", "text": p3["start_discussion"], "step": "part3_start_discussion", "ui": ui_d, "cacheable": True},
                    {"speaker": "partner", "text": partner_open, "step": "part3_partner_open", "ui": ui_d, "cacheable": True},
                ]
            elif step.startswith("discussion"):
                sess["step"] = "decision_0"
                sess["q_idx"] = 0
                covered = list(sess.get("covered_options") or [])
                prop_opt = covered[0] if covered else (opts[0] if opts else "")
                sess["focus_option"] = prop_opt
                ui_dec = _build_ui(test, "part3", "decision_0", sess["target_part"])
                partner_dec_open = voice.generate_partner_line("part3_decision_open", test, focus_option=prop_opt)
                clips = [
                    {"speaker": "examiner", "text": f"{tone.CANONICAL['skip_advance']} {p3['decision_prompt']}", "step": "part3_decision_prompt", "ui": ui_dec, "cacheable": True},
                    {"speaker": "partner", "text": partner_dec_open, "step": "part3_partner_dec_open", "ui": ui_dec, "cacheable": True},
                ]
            else:
                end_clips, done = _finish_current_part(sess, test)
                clips = [{"speaker": "examiner", "text": tone.CANONICAL["skip_advance"], "step": "skip", "ui": _build_ui(test, phase, step, sess["target_part"]), "cacheable": True}] + end_clips

        elif phase == "part4":
            qs = _select_part4_questions(test)
            idx = int(sess.get("q_idx") or 0) + 1
            if idx >= len(qs):
                end_clips, done = _finish_current_part(sess, test)
                clips = [{"speaker": "examiner", "text": tone.CANONICAL["skip_advance"], "step": "skip", "ui": _build_ui(test, phase, step, sess["target_part"]), "cacheable": True}] + end_clips
            else:
                sess["q_idx"] = idx
                sess["step"] = f"q_{idx}_user"
                ui_p4 = _build_ui(test, "part4", sess["step"], sess["target_part"])
                nq = qs[idx]
                cand_name = sess.get("candidate_name") or "Candidate"
                if idx % 2 == 1:
                    partner_own = voice.generate_partner_line("part4_answer", test, question_text=nq["text"], turn_index=idx)
                    clips = [
                        {"speaker": "examiner", "text": f"{tone.CANONICAL['skip_advance']} {partner_name}, {_lc_first(nq['text'])}", "step": f"part4_partner_first_q_{idx}", "ui": ui_p4, "cacheable": True},
                        {"speaker": "partner", "text": partner_own, "step": f"part4_partner_first_a_{idx}", "ui": ui_p4, "cacheable": nq["text"] in voice._PART4_PARTNER_BANK},
                        {"speaker": "examiner", "text": f"Thank you. And you, {cand_name}? {_lc_first(nq['text'])}", "step": f"part4_q_{idx}", "ui": ui_p4, "cacheable": False},
                    ]
                else:
                    clips = [{
                        "speaker": "examiner",
                        "text": f"{tone.CANONICAL['skip_advance']} {cand_name}, {_lc_first(nq['text'])}",
                        "step": f"part4_q_{idx}",
                        "ui": ui_p4,
                        "cacheable": False,
                    }]

        audio_clips, tts_err = _synth_sequence(clips, partner_voice)
        if tts_err:
            return None, (503 if tts_err == "speech_not_configured" else 502), tts_err

        _save_session(sess)
        final_ui = _build_ui(test, sess["phase"], sess["step"], sess["target_part"])
        return {
            "skipped": True,
            "accepted": False,
            "retry": False,
            "speaker": audio_clips[0]["speaker"],
            "audio_b64": audio_clips[0]["audio_b64"],
            "mime": "audio/wav",
            "sequence": audio_clips,
            "state": _public_state(sess),
            "ui": final_ui,
            "done": done,
        }, 200, None


# ---------------------------------------------------------------------------
# Public API: generate_report (3 bands 0-5 + comments, NO pronunciation!)
# ---------------------------------------------------------------------------
def _round_half_band(value):
    clamped = max(0.0, min(5.0, float(value)))
    return round(clamped * 2.0) / 2.0


def generate_report(uid, session_id, save=False):
    """Build the Cambridge 3-band Speaking v3 report (no pronunciation).

    If `save=True`, appends a compact summary (no transcript, no pronunciation)
    to `speaking_v3` inside the user's `progress.json`.
    """
    with _SESS_LOCK:
        sess, load_err = load_session(uid, session_id)
        if load_err:
            code = 410 if load_err == "session_expired" else 404
            return None, code, load_err

        flags = sess.get("flags") or {}
        scores = sess.get("scores") or []

        if scores:
            gv_raw = sum(s["gv"] for s in scores) / len(scores)
            dm_raw = sum(s["dm"] for s in scores) / len(scores)
            ic_raw = sum(s["ic"] for s in scores) / len(scores)
        else:
            gv_raw, dm_raw, ic_raw = 0.0, 0.0, 0.0

        # Apply flag adjustments honestly
        off_topic = int(flags.get("off_topic_turns") or 0)
        non_en = int(flags.get("non_english_turns") or 0)
        skipped = int(flags.get("skipped_turns") or 0)

        if flags.get("name_ok") is False or flags.get("home_ok") is False:
            ic_raw -= 0.4
        if off_topic > 0:
            dm_raw -= min(1.5, off_topic * 0.4)
            ic_raw -= min(1.5, off_topic * 0.4)
        if non_en > 0:
            gv_raw -= min(1.5, non_en * 0.5)
        if flags.get("part2_compared") is False:
            dm_raw -= 0.5
        if skipped > 0 and not scores:
            gv_raw = dm_raw = ic_raw = 0.0

        bands = {
            "grammar_vocabulary": _round_half_band(gv_raw),
            "discourse": _round_half_band(dm_raw),
            "interactive": _round_half_band(ic_raw),
        }

        comments = _build_report_comments(bands, flags, len(scores))

        report = {
            "session_id": session_id,
            "test_id": sess.get("test_id"),
            "part": sess.get("target_part", 0),
            "bands": bands,
            "comments": comments,
            "flags": {
                "name_ok": flags.get("name_ok"),
                "home_ok": flags.get("home_ok"),
                "off_topic_turns": off_topic,
                "non_english_turns": non_en,
                "silence_turns": int(flags.get("silence_turns") or 0),
                "skipped_turns": skipped,
                "part2_compared": flags.get("part2_compared"),
            },
            "saved": False,
        }

        if save is True:
            try:
                prog = store.get_progress(uid) or {}
                if not isinstance(prog, dict):
                    prog = {}
                history = prog.get("speaking_v3")
                if not isinstance(history, list):
                    history = []
                history.append({
                    "date": date.today().isoformat(),
                    "test_id": sess.get("test_id"),
                    "part": sess.get("target_part", 0),
                    "bands": bands,
                    "flags": report["flags"],
                })
                prog["speaking_v3"] = history[-100:]
                store.put_progress(uid, prog)
                report["saved"] = True
            except Exception:
                report["saved"] = False

        return report, 200, None


def _build_report_comments(bands, flags, scored_turns):
    if scored_turns == 0:
        msg = "No spoken responses were recorded for assessment in this session."
        return {
            "grammar_vocabulary": msg,
            "discourse": msg,
            "interactive": msg,
            "overall": msg,
        }

    gv = bands["grammar_vocabulary"]
    dm = bands["discourse"]
    ic = bands["interactive"]

    if gv >= 4.0:
        gv_c = "Good range of B2 vocabulary and grammatical control across your responses."
    elif gv >= 3.0:
        gv_c = "Satisfactory control of everyday grammar and vocabulary; aim to introduce more complex structures and varied lexis."
    else:
        gv_c = "Limited range or accuracy noted; practise building fuller sentences in English without reverting to another language."

    if flags.get("non_english_turns", 0) > 0:
        gv_c += " Note: non-English speech occurred during the session; keep all responses strictly in English."

    if dm >= 4.0:
        dm_c = "Responses were well developed, coherent, and directly addressed the tasks."
    elif dm >= 3.0:
        dm_c = "Generally coherent answers; link ideas more consistently using discourse markers such as 'whereas', 'however', and 'although'."
    else:
        dm_c = "Responses were brief or drifted off-topic; focus on answering the exact question asked and extending your points."

    if flags.get("part2_compared") is False:
        dm_c += " In Part 2, remember to compare both photographs directly rather than describing only one."

    if ic >= 4.0:
        ic_c = "Effective interaction with the examiner and partner, responding appropriately and sustaining the discussion."
    elif ic >= 3.0:
        ic_c = "Adequate interaction; try responding more directly to your partner's points and inviting their views."
    else:
        ic_c = "Communication required repeated prompts; listen carefully to each question and respond directly."

    if flags.get("name_ok") is False or flags.get("home_ok") is False:
        ic_c += " Opening introductory questions were not answered clearly."
    if flags.get("off_topic_turns", 0) > 0:
        ic_c += f" {flags['off_topic_turns']} turn(s) did not address the question asked."

    avg = round((gv + dm + ic) / 3.0, 1)
    overall = (
        f"Estimated Cambridge B2 First Speaking average across assessed criteria: {avg}/5.0 "
        "(Grammar & Vocabulary, Discourse Management, and Interactive Communication)."
    )
    return {
        "grammar_vocabulary": gv_c,
        "discourse": dm_c,
        "interactive": ic_c,
        "overall": overall,
    }
