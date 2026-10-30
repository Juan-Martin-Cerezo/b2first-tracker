# Open asks from the owner (running list)

Last updated: 2026-10-30. Anything here came from Juan, not from me. Check this
file before saying "done".

| # | Ask | Status | Where |
| --- | --- | --- | --- |
| 1 | Speaking with AI: real task, AI as examiner, easy to understand | in queue | phase 35 |
| 2 | Three plans: tight free / own key / paid subscription | done (free+byo+pro+codes) | phase 31 |
| 3 | Real, automatic, secure payments — US$5/month | code queued, needs an adult Stripe account | phase 33 |
| 4 | Owner account without limits | done | commit 2329e0e |
| 5 | Writing word count is wrong | fixed: em dash and `&` counted as words | commit 6a52c23 |
| 6 | Examiner stayed offline | fixed: `responseModalities` must sit inside `generationConfig` | commit after 6a52c23 |
| 7 | Login with Google and other methods | in queue | phase 34 |
| 8 | Secure login | already there (PBKDF2 600k, hashed tokens, lockout, audit chain) | docs/SECURITY-CHECKLIST.md |
| 9 | Privacy, terms, security documents + text scan | running | phase 32 |
| 10 | Login limit too aggressive (10/10 min) | deferred on purpose, will be raised with phase 31 follow-up | — |
| 11 | Cloudflare Web Analytics beacon contradicts the privacy page | blocked on owner (dashboard → Web Analytics → disable) | docs/CLOUDFLARE.md |
| 12 | Rotate the Gemini key (it appeared in chat) | blocked on owner | — |
| 13 | Change the owner password (it appeared in chat) | blocked on owner | — |

## Blocked on the owner, with the reason
- Hackathon name and deadline → needed for README, description and the video script.
- Adult Stripe account → real recurring payments; 16 years old cannot open one.
- Azure Speech key → phoneme-level pronunciation; prepaid cards are rejected.
- Three phone tests (mobile data, iOS mic, voices) → only the owner has the devices.
