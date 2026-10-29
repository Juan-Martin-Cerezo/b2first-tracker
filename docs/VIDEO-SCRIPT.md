# Video Script — B2 First Tracker (Devpost submission)

**Target length:** 102 seconds (6 shots). Screen recording with voiceover. No music, no logos, no claims beyond what the app does. Record at desktop 1280×800 unless noted.

**Global rules (apply to every shot):**
- Never show: real student names, API keys (the `PLAN` tab key field must be empty or blurred), browser bookmarks, personal email, or any file outside the repository.
- Use the demo mode (`B2_DEMO=1 python3 server.py`) with a fresh profile so all data shown is synthetic.
- Speak at a calm pace; the text below is the exact wording, but natural delivery beats a rigid read.

---

## Shot 1 — The problem `[0:00–0:08]` (8 s)

**On screen:** Static slide or the exam overview of the app with the "Writing" section highlighted.

**Say:**
> Writing is 25% of the Cambridge B2 First score — and it's the one part nobody corrects for you. This is B2 First Tracker.

**Do NOT show:** Any personal data. No third-party sites.

---

## Shot 2 — The diagnostic `[0:08–0:24]` (16 s)

**On screen:** The diagnostic tab: 12-question quiz, one question answered wrong on purpose, then the results panel with the 3 weakest parts highlighted and the error log populated (`L-GAP`, `G-ERR`, `T-MIS`, `T-LIM`).

**Say:**
> Start with a 12-item diagnostic — about 10 minutes, all seven parts of Reading and Use of English. It fills your error log and points out your three weakest parts from day one.

**Do NOT show:** The answer explanations during the quiz (spoiler protection is a feature; don't blur it away — just don't hover). Don't show any account name.

---

## Shot 3 — Quick-log and streak `[0:24–0:38]` (14 s)

**On screen:** Mobile viewport (390×844 in dev tools). Tap the floating `+` button (FAB) bottom-right, walk through the 3-step quick-log modal (part → duration → save), see the toast and the streak counter increment, with the weekly goal ring updating.

**Say:**
> Logging a study session takes three taps: the floating button, the part, the time. The streak and the weekly goal update immediately — including a one-day freeze shield so a single miss doesn't wipe you out.

**Do NOT show:** Any pre-existing sessions with real dates tied to you. Use synthetic entries.

---

## Shot 4 — The AI Writing examiner `[0:38–1:08]` (30 s)

**On screen:** The "AI" tab. Paste a short English essay into the text area, select the genre (Essay), submit. Show the result panel scrolling: the 4 Cambridge bands (Content, Communicative Achievement, Organisation, Language, 0–5 each, total /20), each with an exact quote from the text, the 2 weaknesses per criterion, and the rewrite panel with 3 improved sentences.

**Say:**
> Paste your essay and the examiner grades it on the official Cambridge scale — four bands out of five each, so a score out of twenty. Every band is backed by a quote from your own text. Every criterion lists two concrete weaknesses. And it rewrites three of your weak sentences at a stronger level — your sentences, not invented ones.

**Do NOT show:** The API key field (empty or blurred). Do not paste any text you didn't write for the demo.

---

## Shot 5 — Calibration `[1:08–1:30]` (22 s)

**On screen:** Split or sequential view: submit a deliberately weak text (short, simple sentences, off-topic) and show the score **9/20**; then submit a strong text and show **20/20**. Show the weaknesses list for the weak text.

**Say:**
> This is the part that took the work. The first version graded like a cheerleader — every text got 19 out of 20. After calibration against the official band descriptors, a weak text scores 9, a medium one 14, and a strong one 20. Honest bands are the whole point.

**Do NOT show:** Provider errors, raw API responses, or the provider name in the request log if it exposes your key.

---

## Shot 6 — Closing `[1:30–1:42]` (12 s)

**On screen:** The repository on GitHub, then a terminal: `git clone` → `python3 server.py` → the app opening at `http://127.0.0.1:8088`.

**Say:**
> It's open source — pure Python standard library, one HTML file, no build step. Clone the repo, run `python3 server.py`, and you're studying. Links are in the submission.

**Do NOT show:** Your terminal prompt with username/hostname. Use a neutral prompt or crop it.

---

## Total: ~102 s (within the 90–110 s target)
