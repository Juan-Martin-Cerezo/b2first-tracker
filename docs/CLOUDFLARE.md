# Cloudflare in front of the Pi

## Why

Measured from the Pi itself on 2026-10-30, same minute, same file:

| Path | DNS | TLS | TTFB | Page total |
| --- | --- | --- | --- | --- |
| `127.0.0.1:8088` (loopback) | 0 ms | 0 ms | **1 ms** | 1 ms |
| Tailscale Funnel (`*.ts.net`) | 331–1051 ms | 1140 ms | **1215 ms** | 1715–1750 ms |
| Cloudflare quick tunnel | 30 ms | 55 ms | **116–803 ms** | **120–1156 ms** |

The server is not the bottleneck: the same request answers in 1 ms locally and
1.2 s through the Funnel. The Funnel sends traffic out to Tailscale's ingress and
back, and that hop dominates every page load. Cloudflare terminates TLS at an edge
near the user and keeps a persistent QUIC connection to the Pi, so the browser
never pays the Tailscale detour.

Caveat: these numbers were taken **from the Pi**, not from a phone on mobile
data. They compare the two paths fairly (both leave through the same home uplink)
but the absolute best case for a real user is not measured yet.

## The manual step (only Juan can do it)

```
cloudflared tunnel login            # opens a browser, authorises this machine
```

Then a domain in Cloudflare. `firsttracker.app` was US$0 for year 1 at Name.com
(verify before buying). Add the site in the Cloudflare dashboard and set the two
nameservers Cloudflare gives you at the registrar.

Avoid "b2 first" in the domain: it is a Cambridge trademark.

## Then

```bash
DOMAIN=firsttracker.app bash cloudflare/setup.sh
```

`setup.sh` creates the tunnel, installs the credentials with `0600`, writes
`/etc/cloudflared/config.yml` (QUIC, 64 keep-alive connections to the origin,
5 s connect timeout), routes DNS, and installs the systemd service.

## Cache rules (dashboard, after the tunnel works)

| Path | Rule | Why |
| --- | --- | --- |
| `/api/*` | Bypass | Never cache auth, progress or AI responses |
| `/assets/*`, `/files/*` | Cache, Edge TTL 1 month | Static, versioned by ETag |
| `/`, `/libros.json` | Cache, Edge TTL 5 min | Respects the ETags the server sends |

## Turning the Funnel off

Only after `https://<domain>/api/health` answers 200 **and** a real page load
works:

```bash
tailscale funnel --https=443 off
```

Rollback, one line, no reboot:

```bash
tailscale funnel 8088 on
```

## Security notes

- The tunnel is **outbound** from the Pi: no inbound port is opened, and the
  firewall keeps 8088 closed to the internet (verified from a `netns` with a
  public source address).
- Because Cloudflare becomes the only public entry point, the per-IP rate limits
  in `server.py` will see Cloudflare edge IPs. Authenticated routes already limit
  **per user** (phase 23), so only anonymous routes (`/api/config`, `/api/health`,
  `/api/login`) share an IP bucket. If 429s show up under load, raise those
  ceilings or read the real client IP from `CF-Connecting-IP`.
- Cloudflare sees the plaintext of every request (TLS terminates at the edge) —
  including the audio endpoints if they ever proxy through the Pi. Today the
  speaking audio goes browser → Google directly, so this does not apply.
