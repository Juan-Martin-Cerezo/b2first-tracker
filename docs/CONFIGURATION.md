# Configuration Reference

B2 First Tracker reads all runtime settings from environment variables. No secrets belong in the repository; on a hosted server, load them from a `chmod 600` environment file (for example via systemd `EnvironmentFile`).

With no AI keys configured, the app still starts and runs accounts, study plans, timers, materials, charts, and the browser-voice Speaking exam.

## AI writing & speaking report

| Variable | Default | Effect |
| --- | --- | --- |
| `B2_AI_PROVIDER` | `deepseek` | Text model provider for Writing correction, Speaking partner replies, and Speaking reports (`deepseek` or `gemini`). |
| `B2_AI_MODEL` | `deepseek-chat` (or `gemini-2.0-flash` when provider is `gemini`) | Model ID sent to the text provider. |
| `B2_AI_BASE` | `https://api.deepseek.com` (or Gemini v1beta base) | Base URL override for the text provider (useful for proxies or offline test stubs). |
| `B2_AI_KEY` | *(unset)* | Server-side API key for the text provider. If unset, server-side AI grading returns `503 ai_not_configured` unless the user supplies a BYO key. |
| `B2_BYO_TRUSTED_BASES` | *(unset)* | Optional comma-separated allowlist of extra upstream base URLs accepted for bring-your-own-key requests. |

## Speaking voice (Gemini Live & turn-based fallback)

| Variable | Default | Effect |
| --- | --- | --- |
| `B2_SPK_GOOGLE_KEY` | *(unset)* | Google Gemini API key used to mint ephemeral Live tokens (`POST /api/speaking/token`) and run turn-based voice (`POST /api/speaking/turn`). |
| `B2_SPK_LIVE` | *(unset / off)* | Set to `1` (`true`, `yes`, `on`) to enable Gemini Live real-time audio. When unset, Speaking uses turn-based voice if `B2_SPK_GOOGLE_KEY` is set, or browser speech synthesis/recognition otherwise. |
| `B2_SPK_GOOGLE_MODEL` | `gemini-3.8-live` | Gemini Live model requested when minting ephemeral tokens. |
| `B2_SPK_TURN_MODEL` | `gemini-2.5-flash` | Gemini model used for turn-based transcription and examiner reply. |
| `B2_SPK_TTS_MODEL` | `gemini-2.5-flash-preview-tts` | Gemini TTS model used for natural voice replies in turn-based mode (`Puck` for examiner, `Kore` for partner). |
| `B2_SPK_TURN_BASE` | `https://generativelanguage.googleapis.com/v1beta` | Base URL override for Gemini turn/TTS calls. |
| `B2_SPK_GOOGLE_TOKEN_URL` | `https://generativelanguage.googleapis.com/v1beta/auth_tokens` | Ephemeral token provisioning URL override. |
| `B2_SPK_WS_URL` | `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained` | WebSocket URL returned to the browser for Live sessions. |

## Pronunciation assessment (optional Azure)

| Variable | Default | Effect |
| --- | --- | --- |
| `B2_SPK_AZURE_KEY` | *(unset)* | Azure AI Speech subscription key for `POST /api/speaking/pa`. Without it, the endpoint returns `503 speech_not_configured` and Pronunciation reports `not measured`. |
| `B2_SPK_AZURE_REGION` | *(unset)* | Azure Speech region (e.g. `eastus`) used to build the regional STT endpoint. |
| `B2_SPK_AZURE_ENDPOINT` | *(unset)* | Explicit Azure Speech endpoint URL override (takes precedence over region). |
| `B2_SPK_PA_DAILY_PER_USER` | `60` | Maximum Pronunciation Assessment calls per account per day. |

## Usage limits, concurrency & owner accounts

Per-account service caps (`5` writing evaluations, `1` speaking mock, and `15` speaking minutes per UTC day) are defined in [`plans.py`](../plans.py). Instance-wide caps and overrides are configured via environment variables:

| Variable | Default | Effect |
| --- | --- | --- |
| `B2_AI_DAILY_PER_USER` | `200` | Low-level per-user text AI call ceiling in `server.py` (standard accounts hit `plans.py`'s `5`/day writing cap first). |
| `B2_AI_DAILY_TOTAL` | `1200` | Instance-wide daily text AI call cap across non-owner accounts. Hosted instances typically lower this (e.g. `20`) to match prepaid budget. |
| `B2_SPK_MIN_DAILY_PER_USER` | `60` | Low-level per-user daily speaking minute ceiling in `server.py` (standard accounts hit `plans.py`'s `15` min/day cap first). |
| `B2_SPK_MIN_DAILY_TOTAL` | `600` | Instance-wide daily speaking minute cap across non-owner accounts. Hosted instances typically lower this (e.g. `25`) to fit monthly budget. |
| `B2_SPK_MONTHLY_MINUTES` | `900` | Global monthly Gemini Live minute guard (`data/spk_spend.json`). Applies to **every** account, including owners, to cap real monthly spend. |
| `B2_SPK_MAX_INFLIGHT` | `4` | Maximum concurrent upstream Speaking turn/TTS calls per instance. |
| `B2_SPK_QUEUE_WAIT` | `8` | Seconds a Speaking request waits for an upstream slot before returning `503 busy`. |
| `B2_OWNER_UIDS` | `owner` | Comma-separated account IDs treated as instance owners (exempt from daily writing/speaking caps; still subject to `B2_SPK_MONTHLY_MINUTES` and per-minute rate limits). |

## Server, storage & authentication

| Variable | Default | Effect |
| --- | --- | --- |
| `PORT` | `8088` | TCP listening port. |
| `B2_HOST` | `127.0.0.1` | Bind address. Defaults to loopback for reverse-proxy deployments; set `0.0.0.0` inside Docker or LAN. |
| `B2_DATA_DIR` / `DATA_DIR` | `./data` | Directory where accounts, tokens, progress, backups, usage, and audit logs are stored (`B2_DATA_DIR` takes precedence over `DATA_DIR`). |
| `B2_REGISTER` | `open` | Account signup policy: `open` allows public registration; `closed` disables `POST /api/register`. |
| `B2_PUBLIC_URL` | `https://firsttracker.app` | Canonical public URL used for OAuth callbacks, passkey origin checks, and `security.txt`. |
| `B2_ALLOWED_HOSTS` | *(empty)* | Optional comma-separated allowlist of `Host` headers. Empty disables host filtering. |
| `B2_RP_ID` | `firsttracker.app` | WebAuthn Relying Party ID for passkey registration and login. |
| `B2_GOOGLE_CLIENT_ID` | *(unset)* | Google OAuth 2.0 client ID for "Continue with Google". |
| `B2_GOOGLE_CLIENT_SECRET` | *(unset)* | Google OAuth 2.0 client secret (used server-side only). |
| `B2_PUBLIC_HEALTH` | `0` | Set to `1` to include absolute filesystem paths in `/api/health`. Keep `0` in production. |
| `B2_NO_CACHE` | `0` | Set to `1` to disable static asset compression/ETag caching (benchmarking only). |
| `B2_CONNECTION_LIMIT` | `512` | Maximum simultaneous open sockets before returning `503 busy`. |
| `B2_KEEPALIVE_TIMEOUT` | `5` | Idle HTTP keep-alive socket timeout in seconds. |
| `B2_KEEPALIVE_MAX_REQUESTS` | `100` | Maximum requests served per keep-alive connection. |
| `B2_RATE_USER_API` | `1200` | Authenticated API requests per minute per account. |
| `B2_RATE_IP_AUTH` | `240` | Auth endpoint requests (login/register/password) per minute per IP. |
| `B2_RATE_IP_ANON` | `600` | Unauthenticated requests per minute per IP. |
| `B2_REGISTER_PER_HOUR` | `30` | Maximum registrations per IP per hour. |
| `B2_LOGIN_IP_PER_10MIN` | `120` | Maximum login attempts per IP per 10 minutes. |
