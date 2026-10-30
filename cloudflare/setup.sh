#!/bin/bash
# Put Cloudflare in front of the Pi. Run once, after `cloudflared tunnel login`.
#
# Why: the Tailscale Funnel hop measured 1.2s TTFB from the same host that
# answers 127.0.0.1 in 1ms. A Cloudflare edge answers DNS in 30ms and TLS in
# 55ms, and the tunnel keeps a persistent QUIC connection to the nearest edge
# instead of round-tripping through Tailscale's ingress.
#
# Prerequisite (manual, needs a browser):  cloudflared tunnel login
# then point a domain's nameservers at Cloudflare and set DOMAIN below.
set -euo pipefail

DOMAIN="${DOMAIN:-firsttracker.app}"
NAME="${NAME:-b2first}"
ORIGIN="${ORIGIN:-http://127.0.0.1:8088}"

command -v cloudflared >/dev/null || { echo "cloudflared missing"; exit 1; }
cloudflared tunnel list 2>/dev/null | grep -q " $NAME " || cloudflared tunnel create "$NAME"

CREDS=$(ls ~/.cloudflared/*"$NAME"*.json 2>/dev/null | head -1)
[ -n "$CREDS" ] || { echo "no credentials json: run 'cloudflared tunnel login' first"; exit 1; }

sudo install -d -m 700 /etc/cloudflared
sudo install -m 600 "$CREDS" /etc/cloudflared/creds.json
sudo tee /etc/cloudflared/config.yml >/dev/null <<EOF
tunnel: $NAME
credentials-file: /etc/cloudflared/creds.json
protocol: quic
ingress:
  - hostname: $DOMAIN
    service: $ORIGIN
    originRequest:
      connectTimeout: 5s
      keepAliveConnections: 64
      keepAliveTimeout: 30s
  - service: http_status:404
EOF

cloudflared tunnel route dns "$NAME" "$DOMAIN" || true
sudo cloudflared service install
sudo systemctl enable --now cloudflared

sleep 5
curl -sf -o /dev/null -w "origin via CF: %{http_code} in %{time_total}s\n" "https://$DOMAIN/api/health"

cat <<'NEXT'

Done. Now, in the Cloudflare dashboard (Rules -> Cache Rules) for this hostname:
  - /api/*            -> Bypass cache
  - /assets/*, /files/* -> Cache eligible, Edge TTL 1 month
  - /, /libros.json   -> Cache eligible, Edge TTL 5 min (respects our ETag)
Then stop the Funnel:  tailscale funnel --https=443 off
Rollback:              sudo systemctl disable --now cloudflared && tailscale funnel 8088 on
NEXT
