# Video Script — B2 First Tracker (Devpost submission)

**Target length:** 108 seconds (6 shots). Screen recording with voiceover. No music, no logos, no claims beyond what the app does. Record at desktop 1280×800 unless noted.

**Global rules (apply to every shot):**
- Never show: real student names, API keys (the `PLAN` tab key field must be empty or blurred), passwords while typing, browser bookmarks, personal email, or any file outside the repository.
- Record against the **real multi-user instance** (`python3 server.py` with registration open — not `B2_DEMO`): accounts are a feature and the video shows them. Create one fresh throwaway account on camera (synthetic name, synthetic password); never log into a real account.
- Speak at a calm pace; the text below is the exact wording, but natural delivery beats a rigid read.

---

## Shot 1 — The problem `[0:00–0:08]` (8 s)

**What you see:** Static slide or the exam overview of the app with the "Writing" section highlighted.

**What you say:**
> Writing is 25% of the Cambridge B2 First score — and it's the one part nobody corrects for you. This is B2 First Tracker.

**Do NOT show:** Any personal data. No third-party sites.

---

## Shot 2 — Accounts and the six-step intake `[0:08–0:28]` (20 s)

**What you see:** The live instance. Register the throwaway account (username + password only — no email asked), land on an empty tracker, and the intake wizard opens: 6 steps — a welcome screen, exam date & target grade (A/B/C), rate each skill 1–5 (with "take the 10-minute diagnostic instead" as an alternative), hours per week and study days, "what costs you the most?" (pick up to 3), and finally "Your plan is ready" with the week just built.

**What you say:**
> This is a real multi-user app: create an account and your progress lives in your own private space. Then it interviews you in six quick steps — your exam date and target grade, how you feel about each skill, how much time you can study, and what you struggle with.

**Do NOT show:** The password while typing (blur it). Do not reveal whether the account name is someone real.

---

## Shot 3 — The plan that quotes you, and the three-tap log `[0:28–0:48]` (20 s)

**What you see:** The PLAN tab: the weekly slots generated from the intake, each with its reason line, and the "why" panel quoting the answers back (exam date, target grade, study days, struggles, hours per week). Then the mobile viewport (390×844 in dev tools): the floating `+` button (FAB), the 3-step quick-log modal (part → duration → save), the toast and the streak counter incrementing with the weekly goal ring.

**What you say:**
> The weekly plan is built from your own answers — and it quotes them back, so you can see exactly why each slot is there. And logging a practice session takes three taps: the streak and the weekly goal update immediately, with a one-day freeze shield so a single miss doesn't wipe you out.

**Do NOT show:** Any pre-existing sessions with real dates tied to you. Use synthetic entries.

---

## Shot 4 — The AI Writing examiner `[0:48–1:18]` (30 s)

**What you see:** The "AI" tab. Paste a short English essay into the text area, select the genre (Essay), submit. Show the result panel scrolling: the 4 Cambridge bands (Content, Communicative Achievement, Organisation, Language, 0–5 each, total /20), each with an exact quote from the text, the 2 weaknesses per criterion, and the rewrite panel with 3 improved sentences.

**What you say:**
> Paste your essay and the examiner grades it on the official Cambridge scale — four bands out of five each, so a score out of twenty. Every band is backed by a quote from your own text. Every criterion lists two concrete weaknesses. And it rewrites three of your weak sentences at a stronger level — your sentences, not invented ones.

**Do NOT show:** The API key field (empty or blurred). Do not paste any text you didn't write for the demo.

---

## Shot 5 — Calibration `[1:18–1:36]` (18 s)

**What you see:** Split or sequential view: submit a deliberately weak text (short, simple sentences, off-topic) and show the score **9/20**; then submit a strong text and show **20/20**. Show the weaknesses list for the weak text.

**What you say:**
> This is the part that took the work. The first version graded like a cheerleader — every text got 19 out of 20. After calibration against the official band descriptors, a weak text scores 9, a medium one 14, and a strong one 20. Honest bands are the whole point.

**Do NOT show:** Provider errors, raw API responses, or the provider name in the request log if it exposes your key.

---

## Shot 6 — Closing `[1:36–1:48]` (12 s)

**What you see:** The repository on GitHub, then a terminal: `git clone` → `python3 server.py` → the app opening at `http://127.0.0.1:8088` and the login screen. Optionally flash the Account view (export, change password, Recent activity, delete) to end on the multi-user reality.

**What you say:**
> It's open source — pure Python standard library, one HTML file, no build step. Clone the repo, run `python3 server.py`, create your account, and you're studying. Every account keeps its own data. Links are in the submission.

**Do NOT show:** Your terminal prompt with username/hostname. Use a neutral prompt or crop it.

---

## Total: 108 s (within the 90–110 s target)
