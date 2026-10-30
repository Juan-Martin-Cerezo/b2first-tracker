# Privacy Policy — B2 First Tracker

*Last updated: 2026-10-30 · Served live at [`GET /privacy`](/privacy) (same text).*

This tracker is a self-hosted study app. It stores the minimum needed to work
and to find bugs. **Events are logged, never content:** the telemetry records
what you do in the app (a view opened, a session saved, an error raised), never
what you wrote, answered or typed.

## 1. What we store

- **Account** — your chosen username and a salted, hashed password
  (PBKDF2-HMAC-SHA256, 600,000 iterations). The password itself is never stored.
- **Study progress** — your practice log, error log, plan and settings, as JSON
  files on this server (one folder per account).
- **Session tokens, hashed** — sessions are stored as `sha256(token)`; the raw
  token is never written to disk.
- **Usage events** — anonymous product events (feature used, view opened, time
  in ms, error message truncated to 120 chars). They carry a random per-tab
  session id and, when you are logged in, your account id. The client IP is
  stored only as a salted hash (`sha256(ip+salt)`, 16 hex chars), never in clear
  text.
- **Access audit log** — sign-ins, failed sign-ins and account changes
  (timestamp, event type, username, hashed-at-source IP) to detect abuse.

## 2. What we do not store

- No email addresses (accounts are username + password only).
- No real names, phone numbers or addresses.
- No payment data: the app is free, nothing is sold.
- No third-party analytics, no advertising, no tracking cookies. There is
  exactly one first-party preference cookie-equivalent (localStorage) holding
  your theme and your local data — it never leaves your browser except when you
  sync or export.
- No content telemetry: never your writings, answers, notes or passwords.

## 3. Why

- **To make the app work** — your progress has to live somewhere so the plan,
  streaks and charts are yours across devices.
- **To detect errors** — truncated error messages and usage counts show what
  breaks and what people actually use, so it can be fixed.

## 4. Retention

- **Usage events**: 7 days. Files older than that are deleted automatically on
  every write.
- **Access audit log**: kept until it reaches 5 MB, then rotated once (older
  copy deleted on the next rotation).
- **Study progress**: until you delete your account.
- **Local backups**: kept for 14 days (local rotation + weekly backup).

## 5. Your rights

- **Export** — `GET /api/export` (or "Export my data" in Account) downloads
  everything stored about you as JSON.
- **Delete** — `DELETE /api/account` (or "Delete my account" in Account) erases
  your account *and its files on the server*: progress, backups and session
  tokens.
- Because there is no email on file, account recovery is impossible after
  deletion: export first if you want a copy.

## 6. AI correction

The AI corrector sends **only the text you explicitly choose to correct**,
together with the task type (Essay, Article, Report, Review or Email), to the
configured provider — DeepSeek (default) or Google Gemini. Nothing else is
sent: no account data, no progress, no identifiers. The text is forwarded for
the single request and is **not stored on this server** beyond that request; the
provider's own retention policy applies to what they receive. The resulting
bands and feedback are saved only inside your own progress when you accept the
correction.

## 7. Speaking practice — pronunciation

The speaking studio can score pronunciation. That is the one thing a transcript
cannot measure, so a short clip of your voice is sent to **Azure AI Speech
(Pronunciation Assessment)** — a Microsoft service — to get phoneme-level
scores. What is sent: at most **10 seconds of audio per turn** (not the whole
session) and, optionally, the reference text of the sentence you were asked to
read. Nothing else: no account data, no identifiers, no transcript.

Your audio is **not stored**, not even temporarily on this server: it is
forwarded for the single request and discarded in the same handler. It is
never written to disk, never put in the audit log, never kept for "quality" or
"debugging". Only the numeric result (accuracy, fluency, completeness, prosody
and per-word scores) is kept, and only if you choose to save the session. The
Azure subscription key lives in this server's environment and never reaches
your browser.

Azure/Microsoft processes the audio **outside Argentina** (their regional
speech endpoints), under Microsoft's own retention policy for the request. If
the speech service is not configured on this instance, the endpoint answers
"speech not configured" and pronunciation is reported as **not measured** — the
app never invents that score.

## 8. Live examiner — what Google receives

The live examiner (Speaking Parts 1 and 2) runs on **Google Gemini Live**, a
realtime voice service. Your browser connects **directly to Google** with a
short-lived, single-use token that this server mints for you; the token opens
exactly one session and lives about 30 minutes.

What Google receives: your **microphone audio** (16 kHz PCM, streamed while the
exam runs) and the examiner's own instructions (the exam script). It returns the
examiner's voice (24 kHz PCM) and two transcripts: what you said and what the
examiner said.

What we receive: only the token request, the number of minutes you spent (for
the daily limit) and, if you later choose to save the session, the transcript.
Your audio **never passes through our server** and is **never stored here**, not
even temporarily. Google processes the audio outside Argentina under Google's
own retention policy for the Live API. The Google key lives in this server's
environment and never reaches your browser. If this instance has no speech key,
the examiner falls back to a clearly-labelled simulated voice and no audio
leaves your browser.

## 9. Do Not Track

If your browser sends `Do Not Track: 1` (or the global privacy control signal),
the app sends **no telemetry at all** — no usage events, no error reports. Every
feature keeps working exactly the same.

## 10. Contact

Questions or requests about your data: **TODO_OWNER_EMAIL** (this placeholder is
replaced with the real owner address before public deployment — see the README).

## 11. Applicable law

This policy is written with Argentina's Personal Data Protection Law
(**Ley 25.326**) in mind, including access, correction and deletion rights.
This document describes how the app actually handles data; it does not claim
certified compliance with any regulation.
