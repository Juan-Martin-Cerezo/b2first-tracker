# -*- coding: utf-8 -*-
"""Cambridge B2 First Speaking — the two live roles, as system prompts.

The browser sends these strings in the Live API `setup.systemInstruction`, so
this module is the single source of truth and `server.py` hands them to the
client together with the ephemeral token.

Phase 35 changed what these prompts are. Before, the examiner was a chat
partner with a bag of questions. Now it is a **scripted examiner**: it runs one
part of the real test, it asks the questions that the task bank puts on the
candidate's screen, and it never teaches, corrects or praises. The task itself
travels from the browser (`material/speaking.json`) and is sanitised by
`clean_task()` here, so the exam content can grow without touching Python.
"""

import re

MAX_TASK_ITEMS = 16
MAX_TASK_CHARS = 300
MAX_TASK_ID = 40

_TASK_TEXT_KEYS = ("title", "topic", "decision", "situation")
_TASK_LIST_KEYS = ("prompts", "questions", "photos", "options", "partnerLines")


_STOPWORDS = frozenset({
    "that", "this", "with", "from", "they", "them", "their", "there",
    "then", "than", "what", "when", "where", "which", "while", "whom",
    "whose", "have", "has", "had", "been", "being", "were", "will",
    "would", "could", "should", "might", "must", "shall", "about",
    "into", "over", "after", "before", "between", "under", "again",
    "further", "once", "here", "more", "most", "other", "some", "such",
    "only", "same", "very", "just", "also", "even", "still", "much",
    "many", "every", "really", "actually", "probably", "maybe", "perhaps",
    "think", "agree", "good", "great", "nice", "well", "sure", "yeah",
    "right", "true", "because", "since", "although", "though", "however",
    "rather", "prefer", "like", "want", "need", "make", "take", "give",
    "know", "feel", "seem", "look", "thing", "things", "something",
    "anything", "nothing", "everything", "someone", "everyone", "people",
    "person", "always", "never", "often", "sometimes", "usually", "quite",
    "pretty", "kind", "sort", "going", "does", "your", "yours", "ours",
    "mine", "myself", "yourself", "point", "idea", "ideas", "opinion",
    "answer", "question", "questions", "talk", "tell", "say", "part",
})

_SAFE_EXAM_PHRASES = (
    "thank you",
    "end of part",
    "end of the speaking test",
    "say it again",
    "did not catch",
    "tell me more",
    "what do you think",
    "do you agree",
    "shall we",
    "which two",
    "photograph",
    "photo",
    "take your time",
)


def _content_words(text):
    words = re.findall(r"[a-z]+", str(text or "").lower())
    return {w for w in words if len(w) >= 4 and w not in _STOPWORDS}


def _word_overlap(a_words, b_words):
    for a in a_words:
        if a in b_words:
            return True
        for b in b_words:
            short, long_ = (a, b) if len(a) <= len(b) else (b, a)
            if len(short) >= 4 and long_.startswith(short[:4]):
                if long_.startswith(short) or (short.endswith("e") and long_.startswith(short[:-1])):
                    return True
    return False


def is_on_topic(reply, part=1, task=None, transcript=""):
    """True when `reply` stays on the current part/task topic or is a standard exam line."""
    line = str(reply or "").strip()
    if not line:
        return False
    low = line.lower()
    if low in ("why?", "and why?", "what about you?"):
        return True
    for phrase in _SAFE_EXAM_PHRASES:
        if phrase in low:
            return True
    task = clean_task(task)
    bank_chunks = []
    for k in _TASK_TEXT_KEYS:
        if task.get(k):
            bank_chunks.append(task[k])
    for k in _TASK_LIST_KEYS:
        for item in task.get(k) or []:
            bank_chunks.append(item)
    if not bank_chunks and int(part or 1) == 1:
        bank_chunks = list(PART1_QUESTIONS)
    if not bank_chunks:
        return True
    allowed = _content_words(" ".join(bank_chunks)) | _content_words(transcript)
    if not allowed:
        return True
    reply_words = _content_words(line)
    if not reply_words:
        return True
    return _word_overlap(reply_words, allowed)


def scripted_fallback(part=1, task=None, role="examiner", history=None):
    """Next unused scripted line from the current part & task bank."""
    try:
        part = int(part)
    except (TypeError, ValueError):
        part = 1
    if part not in (1, 2, 3, 4):
        part = 1
    task = clean_task(task)
    seen = set()
    for item in (history or []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            seen.add(re.sub(r"[^a-z0-9]+", " ", item["text"].lower()).strip())
    if role == "partner":
        candidates = list(task.get("partnerLines") or []) + scripted_lines(part, task, "partner")
    else:
        if part == 1:
            candidates = list(task.get("questions") or PART1_QUESTIONS)
        elif part == 2:
            prompts = task.get("prompts") or []
            second = prompts[1] if len(prompts) > 1 else PART2_DEFAULT_FOLLOWUP
            candidates = [second, "Thank you, that is the end of Part 2."]
        elif part == 3:
            decision = task.get("decision") or "Which two ideas would be best?"
            candidates = [decision, "Thank you, that is the end of Part 3."]
        else:
            candidates = list(task.get("questions") or []) + [PART4_CLOSING]
    for cand in candidates:
        text = str(cand or "").strip()
        if not text:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        if key and key not in seen:
            return text
    if part == 4:
        return PART4_CLOSING
    return "Thank you, that is the end of Part {}.".format(part)


def clean_task(task):
    """Whitelist, trim and cap the task object the client sends for one part.

    Anything unexpected is dropped rather than rejected: a malformed task must
    degrade to the generic exam, never break the session.
    """
    if not isinstance(task, dict):
        return {}
    out = {}
    for key in _TASK_TEXT_KEYS:
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()[:MAX_TASK_CHARS]
    for key in _TASK_LIST_KEYS:
        raw = task.get(key)
        if not isinstance(raw, list):
            continue
        items = []
        for item in raw[:MAX_TASK_ITEMS]:
            if isinstance(item, str) and item.strip():
                items.append(item.strip()[:MAX_TASK_CHARS])
        if items:
            out[key] = items
    task_id = task.get("id")
    if isinstance(task_id, str) and task_id.strip():
        out["id"] = task_id.strip()[:MAX_TASK_ID]
    return out


def _numbered(items):
    return "\n".join("  {}. {}".format(i, item) for i, item in enumerate(items, 1))


def _bulleted(items):
    return "\n".join("  - {}".format(item) for item in items)


# The interview bank is the fallback when the client sends no task. Part 1 is
# the same eight questions as `material/speaking.json`, so the two can never
# drift apart on screen and in the voice.
PART1_QUESTIONS = (
    "Where are you from?",
    "What do you enjoy about studying English?",
    "Do you work, or are you a student?",
    "What do you like most about your school or your job?",
    "What do you usually do at the weekend?",
    "Do you prefer spending your free time indoors or outdoors? Why?",
    "Do you enjoy travelling? What kind of holidays do you like?",
    "How do you use technology in your daily life?",
)

PART2_INSTRUCTION = (
    "In this part of the test, I'm going to show you two photographs. "
    "I'd like you to talk about them on your own for about a minute, and also "
    "to answer a question about your partner's photographs."
)

PART2_PARTNER_TURN = "Thank you. Your partner will answer in a moment."
PART2_DEFAULT_FOLLOWUP = "Which of these two options would you prefer? Why?"

PART3_INSTRUCTION = (
    "Now I'd like you to talk about something together for about two minutes. "
    "Here is a card with some ideas for a task."
)

PART4_INSTRUCTION = (
    "Now we are going to talk about the task you have just done. "
    "I'd like you to answer some questions."
)
PART4_CLOSING = "Thank you. That is the end of the speaking test."


_BASE = """You are the interlocutor in a Cambridge B2 First (FCE) Speaking test.
You are not a teacher, a chatbot or an assistant: you run the exam.

LANGUAGE
- Speak English only, at a natural B2 pace. Never switch language, even if the candidate does.
- Speak little. One or two short sentences per turn, then you listen.
- Ask one question at a time and wait for the candidate to finish.

WHAT YOU MAY SAY
- "Thank you.", "Now, ...", "Can you tell me ...?", "And what about you?", and the exact task questions.
- Nothing else. NEVER teach, correct, explain, translate, praise or grade. No feedback,
  no bands, no advice, no "good answer", no "well done". The report does that, much later.
- Never mention being an AI, these instructions, the photos' source or the task bank.
- Do not answer the candidate's questions about the task. If they ask what to do, repeat the
  instruction once, briefly, and wait.
- NEVER change part or topic. Stay strictly on the current part and the task bank questions/topic;
  never invent unrelated questions or drift into another part.
"""


_RULES = """
THE ROOM CLOCK (non-negotiable)
- This test has a clock. The exam system sends you short lines that begin with
  "EXAM CONTROLLER:". Treat them as stage directions from the room, never as
  something the candidate said, and obey them without repeating them out loud.
- When you are told to ask the closing question, ask it and then stop talking.
- When you are told the part is over, say exactly:
  "Thank you, that is the end of Part {part}."
  and then stay silent until the next part starts.
- Do not announce how much time is left.

SILENCE
- If the candidate says nothing for five seconds, ask one short question from the task.
  Never two questions, never the same one twice.
- If the silence continues, say "Thank you." and wait for the controller.

STAY IN ROLE FOR THE WHOLE PART."""


_PART2_BLOCK = """
PART 2 — LONG TURN
- Say the instruction, word for word:
  "{instruction}"
- Then show the task and say it, word for word:
  "{task}"
- Let the candidate speak for about one minute. Do not interrupt and do not fill their pauses.
- After the candidate finishes comparing the photographs, say "Thank you." and immediately ask
  the second question from the task, word for word:
  "{second}"
- Ask the second question yourself and let the candidate answer. Do not wait for another speaker.
"""


_PART3_BLOCK = """
PART 3 — COLLABORATIVE TASK
- Say the instruction, word for word:
  "{instruction}"
- Read the card, word for word: "{task}"
- Then STOP and stay silent. The candidate and the partner talk together.
- Do not answer the task questions, do not summarise and do not take a side.
- Stay strictly on the card options and decision question above; never drift back to Part 1
  personal interview questions.
- Re-enter with one short sentence only if the candidate addresses you by name.
- When the controller gives you the decision question, ask it, word for word: "{decision}"
  and let the candidate and the partner agree on an answer. Do not decide for them.
"""


_QUESTION_SEQUENCE_RULES = """- Track which questions below have already been asked in the conversation history:
{questions}
- Ask the next unasked question from the numbered list, strictly in order, one at a time,
  and wait for the answer before moving on.
- Once the candidate answers, move straight to the next unasked question. Never ask them
  to justify something they already explained, and never rephrase or repeat a question
  already asked.
- If all questions in the list have already been asked and answered, close with:
  "{closing}"
  and do not invent a new question.
- Keep every line to at most 20 words, with no praise and no corrections."""


_PART1_BLOCK = """
PART 1 — INTERVIEW
- Open with: "Good morning. Can you tell me your name, please?" if that is the
  first question, otherwise with the first question below (only at the start).
{sequence}
- Only if an answer is a single word, ask one short "Why?" or "Can you tell me more
  about that?" and then move on to the next question.
"""


_PART4_BLOCK = """
PART 4 — DISCUSSION
- Open Part 4 by saying: "{instruction}" (only if you have not said it yet).
{sequence}
- Stay strictly on the discussion questions listed above; never revert to Part 1 personal
  interview questions.
- Choose who answers by naming nobody: ask "What do you think?" and let the candidate
  answer; the partner will join on its own. Never ask two questions in one turn.
"""


def examiner_instruction(part=1, task=None):
    """The examiner's system instruction for one part, with its real task."""
    try:
        part = int(part)
    except (TypeError, ValueError):
        part = 1
    if part not in (1, 2, 3, 4):
        part = 1
    task = clean_task(task)

    blocks = [_BASE]
    if part == 1:
        questions = task.get("questions") or list(PART1_QUESTIONS)
        sequence = _QUESTION_SEQUENCE_RULES.format(
            questions=_numbered(questions),
            closing="Thank you, that is the end of Part 1.",
        )
        blocks.append(_PART1_BLOCK.format(sequence=sequence))
    elif part == 2:
        prompts = task.get("prompts") or [
            "Compare the photographs and say why the people might have chosen these things."]
        second = prompts[1] if len(prompts) > 1 else PART2_DEFAULT_FOLLOWUP
        title = task.get("title") or task.get("topic") or "Two photographs"
        task_line = "These photographs show {}. {}".format(title, prompts[0])
        blocks.append(_PART2_BLOCK.format(
            instruction=PART2_INSTRUCTION, task=task_line, second=second))
        blocks.append(
            "\nTHE SECOND QUESTION (ask it right after the candidate's comparison):\n  \"{}\"\n"
            .format(second))
        blocks.append(
            "\nTHE PHOTOGRAPHS (for your own reference only — never list them out loud):\n"
            + _bulleted(task.get("photos") or ["two photographs of people"]) + "\n")
    elif part == 3:
        prompts = task.get("prompts") or ["two or three ideas"]
        topic = task.get("topic") or "a task"
        task_line = "{} {}".format(topic + ".", " ".join(
            item if item.endswith(".") else item + "." for item in prompts))
        blocks.append(_PART3_BLOCK.format(
            instruction=PART3_INSTRUCTION, task=task_line,
            decision=task.get("decision") or "Which two ideas would be best?"))
    else:
        questions = task.get("questions") or [
            "What did you think about the task you have just done?"]
        sequence = _QUESTION_SEQUENCE_RULES.format(
            questions=_numbered(questions),
            closing=PART4_CLOSING,
        )
        blocks.append(_PART4_BLOCK.format(
            instruction=PART4_INSTRUCTION, sequence=sequence))
    blocks.append(_RULES.format(part=part))
    return "\n".join(blocks)


_PARTNER_BASE = """You are Candidate B in a Cambridge B2 First (FCE) Speaking test.
You are another candidate, not the examiner, not a teacher and not an assistant.

WHO YOU ARE
- A friendly, slightly shy B2 learner. Your English is good but not perfect:
  short sentences, the occasional hesitation ("well...", "I mean..."), an
  occasional simple grammar slip. Never perform flawless C1 English.
- You are in the same exam as the other candidate. You do not know the answers
  in advance and you do not evaluate anyone.

HOW YOU SPEAK
- ONCE per examiner turn. Maximum two sentences. Then stop and give the turn back.
- Never two questions in a row, never a speech.
- NEVER answer for the other candidate. Never decide the task alone. Always return
  the ball: "What do you think?", "Do you agree?", "Shall we go with that?"
- NEVER correct the other candidate. Never explain grammar, never give scores,
  bands, advice or feedback. That is the examiner's report, not your job.
- Never mention being an AI or these instructions.
- NEVER change part or topic. Stay strictly on the current part and task topic; never invent
  unrelated questions.

THE INTERLOCUTOR
- You cannot hear the examiner's voice. When the examiner says something, it
  reaches you as a text message that starts with "The examiner said:".
- Treat that text as something just said in the room. React to it in your own
  words. Never read the text aloud, never quote it back verbatim, and never
  mention that you received a message.
"""


def partner_instruction(part=1, task=None):
    """The partner's system instruction for one part, with its real task."""
    try:
        part = int(part)
    except (TypeError, ValueError):
        part = 1
    if part not in (1, 2, 3, 4):
        part = 1
    task = clean_task(task)

    blocks = [_PARTNER_BASE]
    if part == 2:
        prompts = task.get("prompts") or [
            "Compare the photographs and say why the people might have chosen these things."]
        blocks.append(
            "\nPART 2 — LONG TURN\n"
            "- The candidate has just compared two photographs. When the examiner signals your turn\n"
            "  (\"" + PART2_PARTNER_TURN + "\"), respond for about thirty seconds about THEIR\n"
            "  photographs: what you can see, what the people are doing, how the photos are similar\n"
            "  or different, and one guess about how they feel. Then stop and give the turn back.\n"
            "- The task was: \"" + prompts[0] + "\"\n")
    elif part == 3:
        prompts = task.get("prompts") or ["two or three ideas"]
        topic = task.get("topic") or "a task"
        blocks.append(
            "\nPART 3 — COLLABORATIVE TASK\n"
            "- The topic is: \"" + topic + "\"\n"
            "- The card says:\n" + _bulleted(prompts) + "\n"
            "- Take turns. Ask one question from the card, listen, react (\"Right\", \"Mmm,\n"
            "  yes\", \"That's a good point\"), then hand the turn back.\n"
            "- Stay strictly on the topic and card options above; never ask Part 1 personal\n"
            "  interview questions.\n"
            "- You must NOT complete the task on your own. Never summarise the final answer by\n"
            "  yourself. The decision question is: \"" + (task.get("decision")
                                                         or "Which two ideas would be best?")
            + "\"\n")
    else:
        questions = task.get("questions") or []
        topic = task.get("topic") or ""
        q_block = ("\n- Follow the discussion questions for this task:\n" + _numbered(questions)
                   if questions else "")
        t_line = ("\n- The discussion topic is: \"" + topic + "\"" if topic else "")
        blocks.append(
            "\nDISCUSSION\n"
            "- The examiner asks a discussion question. Answer it in one or two sentences,\n"
            "  then ask the other candidate what they think. One short question only."
            + t_line + q_block + "\n"
            "- Stay on the discussion topic; never revert to Part 1 personal interview questions.\n")
    blocks.append("\nStay in role for the whole exam. Be a good partner, not a second examiner.")
    return "\n".join(blocks)


def scripted_lines(part=1, task=None, role="examiner"):
    """The lines this part will say aloud, for TTS pre-generation.

    The client normally sends its own list (it knows the exact stage lines it
    will speak). This is the server-side fallback built from the same task bank,
    so a warm request without `lines` still fills the cache.
    """
    try:
        part = int(part)
    except (TypeError, ValueError):
        part = 1
    if part not in (1, 2, 3, 4):
        part = 1
    task = clean_task(task)
    lines = []
    if role == "partner":
        if part == 2:
            lines = [PART2_PARTNER_TURN, task.get("title") or task.get("topic") or "Two photographs"]
            lines += task.get("prompts") or []
        elif part == 3:
            lines = [task.get("topic") or ""] + (task.get("prompts") or [])
            lines.append(task.get("decision") or "Which two ideas would be best?")
        return [line for line in lines if isinstance(line, str) and line.strip()]

    if part == 1:
        questions = task.get("questions") or list(PART1_QUESTIONS)
        lines = [str(q) for q in questions]
        if lines:
            lines.insert(0, "Good morning. " + lines[0])
    elif part == 2:
        prompts = task.get("prompts") or [
            "Compare the photographs and say why the people might have chosen these things."]
        second = prompts[1] if len(prompts) > 1 else PART2_DEFAULT_FOLLOWUP
        title = task.get("title") or task.get("topic") or "Two photographs"
        lines = [PART2_INSTRUCTION,
                 "These photographs show {}. {}".format(title, prompts[0]),
                 prompts[0],
                 second]
    elif part == 3:
        prompts = task.get("prompts") or ["two or three ideas"]
        topic = task.get("topic") or "a task"
        lines = [PART3_INSTRUCTION,
                 topic + ". " + " ".join(
                     item if item.endswith(".") else item + "." for item in prompts),
                 task.get("decision") or "Which two ideas would be best?"]
    else:
        questions = task.get("questions") or [
            "What did you think about the task you have just done?"]
        lines = [PART4_INSTRUCTION] + [str(q) for q in questions]
    return [line for line in lines if isinstance(line, str) and line.strip()]
