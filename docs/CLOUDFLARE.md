# Cloudflare tunnel — what is actually deployed

Live since 2026-10-30. `https://firsttracker.app` is the only public entry point;
the Tailscale Funnel is **off**.

## Measured (from the Pi, same file)

| Path | TTFB | Page |
| --- | --- | --- |
| `127.0.0.1:8088` | 1 ms | 1 ms |
| Tailscale Funnel (retired) | 1215 ms | 1715 ms |
| `https://firsttracker.app` | **114 ms** | 120 ms |
| `https://app.firsttracker.app` | **86 ms** | — |
| LAN `192.168.1.83:8088` | 16 ms | 16 ms |

## Shape

```
browser → Cloudflare edge (TLS terminates here) → QUIC tunnel → 127.0.0.1:8088
```

- Tunnel `b2first`, id `31bbf247-eb28-4a89-b8c8-cd2b7732b8ac`.
- Own config and credentials in **`/etc/cloudflared-b2first/`** (`0700`, `0600`),
  own unit `cloudflared-b2first.service`. It deliberately does **not** share
  `/etc/cloudflared/`, which belongs to the older `financemacro` tunnel.
- `protocol: quic`, 64 keep-alive connections, 5 s connect timeout.
- Ingress accepts the apex, `app.` and `www.`; everything else returns 404.
- DNS: CNAME → tunnel at the apex (Cloudflare flattens it), at `app.` and `www.`.

## What had to be removed first

The registrant's default parking records — `A 91.195.240.94` (SEDO-NET, now
Name.com's parking IP) on `*`, the apex and `www` — were proxied through
Cloudflare and made the apex answer **525** (Cloudflare could not do TLS with a
parking page). They were deleted in the dashboard; the apex CNAME could then be
created.

## Verification

```bash
curl -s -o /dev/null -w "%{http_code} %{time_starttransfer}\n" https://firsttracker.app/api/health
bash tools/audit.sh          # 39/39 against the new hostname
curl -sI https://firsttracker.app/ | grep -i strict-transport
```

## Rollback

```bash
sudo systemctl disable --now cloudflared-b2first
tailscale funnel 8088 on      # brings the old public URL back
```

Nothing else depends on the tunnel: the app still listens on `0.0.0.0:8088`
(LAN + tailnet, dropped from the internet by nft) and the Funnel is one command
away.

## Incident: `/etc/cloudflared/` was overwritten

The first version of `cloudflare/setup.sh` wrote to `/etc/cloudflared/config.yml`
and `creds.json` without a backup, which are the `financemacro` tunnel's files.
That service was already `inactive` (the apex had been returning 525 for a while),
but the local credentials were lost. Recovery:

```bash
sudo cloudflared tunnel token financemacro-tunnel   # prints a token to run it
```

`setup.sh` now resolves the credentials file by tunnel **id** (cloudflared names
it after the UUID, not the name) and is expected to be run with
`TUNNEL_ORIGIN_CERT=$HOME/.cloudflared/cert.pem`, because `sudo` resets `$HOME`.
