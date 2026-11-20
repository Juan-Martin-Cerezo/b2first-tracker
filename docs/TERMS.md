# Terms of Use — B2 First Tracker

**Version 1.2** · Last updated: 2026-11-18 · Served live at `/terms`

**Changelog**

- 1.2 — 2026-11-18 · Hosted service: accounts live on the provider's server, there
  is no purchase flow, and the fair-use limits are stated plainly.
- 1.1 — 2026-11-02 · Account recovery: reset requests from the login screen, manual
  reset by the operator, 90-day retention of requests.
- 1.0 — 2026-10-30 · First complete version: acceptable use, fair-use limits,
  provider costs, availability and liability.

These terms govern your use of the hosted B2 First Tracker service at
`https://firsttracker.app`. By creating an account you accept them, together with
the Privacy Policy at `/privacy`.

## 1. The service

B2 First Tracker is a hosted study tool for the Cambridge B2 First exam. Accounts
and progress live on the provider's server, and you use the app from a browser.
The service is provided **as is**, with no service-level agreement.

## 2. No guarantee of a Cambridge score or result

The app tracks practice, proposes a study plan, and can ask an AI model to
correct writing or simulate a speaking exam. **None of that is an official
Cambridge assessment.** The app does not guarantee a pass, a grade, a CEFR level
or a particular score, and it cannot predict an official result. AI feedback can
be wrong: treat it as a second opinion, not as an examiner's decision. The only
authoritative result is the one issued by Cambridge.

## 3. Accounts

- One account per person. Do not share credentials or impersonate someone else.
- You are responsible for keeping your password safe. There is no email on file, so no
  reset link can be sent. From the login screen you can file a reset request with your
  user name and, optionally, a contact. The operator resets the password by hand;
  nobody is contacted unless you left a contact. Requests are kept for 90 days, then
  deleted.
- You must be at least 16 years old. If you are under 18, you need permission
  from a parent or guardian.
- We may close an account that abuses the service, attacks the host, or evades
  the limits described below.

## 4. Fair use and limits

Every account has the full service. To keep AI provider costs predictable, the
service applies **daily fair-use limits** per UTC day — currently **5 writing
evaluations** and **1 Speaking mock (up to 15 minutes)** per account, plus an
instance-wide monthly cap on live voice minutes. The current meter is visible
under **Settings → Usage limits**. Limits reset automatically and never change
the work already saved in your account. Accounts using their own provider key
(BYO) are not metered by the service.

Automated scraping, credential stuffing, deliberately exhausting quotas, or using
the AI endpoint for anything other than your own study is prohibited.

The operator may change the limits or the available models with notice in the app
or in this document. Continued use after a change means you accept the new
limits.

## 5. Your own provider key (BYO)

If you connect your own AI provider key, you are solely responsible for:

- the key, its security and any activity billed to it;
- the provider's terms of service and data-processing terms;
- **all costs** the provider charges you. This app does not meter, bill, cap or
  reimburse provider usage when a BYO key is in use.

The key is kept in your browser's localStorage and sent only with your own
requests. **Clear key** in the AI provider card removes it from that browser; the
server never stores it.

## 6. Third-party services

The app uses **Google** for live speaking audio and, optionally, text generation,
**DeepSeek** for writing corrections by default, and **Microsoft Azure** for
pronunciation only when the operator configures it. The hosting and edge network
providers deliver the HTTP request to the service. Their availability, pricing and
policies are outside this service's control. An outage of any of them may disable
the related feature.

## 7. Content and conduct

You keep ownership of everything you write. You grant the service only the
permission needed to store your progress and to forward the text or audio you
explicitly submit for correction or scoring. Do not submit content that is
illegal, that you have no right to share, or that contains another person's
personal data.

## 8. Availability, changes and termination

- The service may be offline for maintenance, updates or network problems. There
  is no uptime commitment.
- The operator may modify or discontinue features. Material changes are announced
  in the app.
- You may stop using the service at any time. **Export my data** and **Delete my
  account** in the Account panel are immediate and self-service.

## 9. Disclaimer and limitation of liability

To the maximum extent permitted by Argentine law, the service is provided
without warranties of any kind, express or implied, including fitness for a
particular purpose and non-infringement. The operator is not liable for indirect,
incidental or consequential damages, for lost study time, for an exam result, or
for costs charged by a provider you connected yourself. Nothing in these terms
excludes liability that cannot be excluded by law.

## 10. Privacy

Data handling is described in the Privacy Policy at `/privacy`. In short: account
and progress data stay on the provider's server; speaking audio is never stored;
no data is sold and there is no advertising or cross-site tracking (only
cookie-free aggregate Cloudflare Web Analytics).

## 11. Governing law and contact

These terms are governed by the laws of the Argentine Republic. Questions and
security reports go through the repository's private advisory form:
https://github.com/Juan-Martin-Cerezo/b2first-tracker/security/advisories/new

## 12. Changes to these terms

The version and date at the top are authoritative. The changelog records each
material revision. If you do not accept a revision, export your data and delete
your account.
