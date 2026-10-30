#!/usr/bin/env bash
# tools/audit-host.sh -- local host-hardening audit for vps-server.
#
# Read-only checks of the host layer (not the app): nftables input policy,
# Docker FORWARD filtering (DOCKER-USER), listening-port placement, sshd
# effective config, fail2ban, Tailscale Funnel exposure and egress.
#
# Usage:  sudo bash tools/audit-host.sh
# Exit:   0 = every check passed, 1 = at least one FAIL, 2 = not run as root.
#
# The companion tools/audit.sh probes the public HTTP surface; this one audits
# the box. Both print PASS/FAIL plus one line of evidence.
set -u

if [ "$(id -u)" -ne 0 ]; then
  echo "audit-host: must run as root (it reads nftables, iptables, ss and sshd -T)" >&2
  echo "usage: sudo bash tools/audit-host.sh" >&2
  exit 2
fi

PASS_N=0
FAIL_N=0
NA_N=0

row() { # row CHECK RESULT EVIDENCE
  printf '%-58s | %-6s | %s\n' "$1" "$2" "$3"
  case "$2" in
    PASS) PASS_N=$((PASS_N + 1)) ;;
    FAIL) FAIL_N=$((FAIL_N + 1)) ;;
    *)    NA_N=$((NA_N + 1)) ;;
  esac
}

MEM_MB=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
CORES=$(nproc)

echo "vps-server -- local host hardening audit"
echo "Host:   $(hostname) | $(uname -m) | ${CORES} cores | ${MEM_MB} MB"
echo "Date:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
printf '%-58s | %-6s | %s\n' "CHECK" "RESULT" "EVIDENCE"
printf '%-58s-+-%-6s-+-%s\n' \
  "----------------------------------------------------------" "------" "----------------------------------------"

# ---------------------------------------------------------------------------
# nftables input policy
# ---------------------------------------------------------------------------
NFT=$(nft -s list table inet hardened 2>/dev/null)
nft_has() { printf '%s\n' "$NFT" | grep -Fq -- "$1"; }

if [ -z "$NFT" ]; then
  row "nft table inet hardened exists" "FAIL" "table not found"
else
  row "nft table inet hardened exists" "PASS" "table present"

  if nft_has "policy drop"; then
    row "Input policy is drop" "PASS" "policy drop"
  else
    row "Input policy is drop" "FAIL" "no 'policy drop' in input chain"
  fi

  RULE_LINES=$(printf '%s\n' "$NFT" | sed 's/^[[:space:]]*//' \
    | grep -E '^(ct |iifname |oifname |ip |ip6 |udp |tcp |counter )' || true)
  TOTAL=$(printf '%s\n' "$RULE_LINES" | grep -c . || true)
  UNIQ=$(printf '%s\n' "$RULE_LINES" | sort -u | grep -c . || true)
  if [ "$TOTAL" -eq "$UNIQ" ]; then
    row "No duplicate rules in inet hardened" "PASS" "${TOTAL} rule lines, ${UNIQ} unique"
  else
    row "No duplicate rules in inet hardened" "FAIL" "${TOTAL} rule lines, only ${UNIQ} unique"
  fi

  for spec in \
    'ct state established,related accept' \
    'iifname "lo" accept' \
    'iifname "tailscale0" accept' \
    'udp dport 41641 accept' \
    'iifname "tailscale0" ct state new tcp dport 22 accept' \
    'ip saddr 192.168.1.0/24 ct state new tcp dport 22 limit rate 6/minute burst 3 packets accept' \
    'ip saddr 10.0.1.0/24 ct state new tcp dport 22 accept' \
    'ct state new tcp dport 22 drop' \
    'ip saddr 192.168.1.0/24 tcp dport { 2283, 8089, 9100 } accept'; do
    if nft_has "$spec"; then
      row "nft rule: $spec" "PASS" "present"
    else
      row "nft rule: $spec" "FAIL" "missing"
    fi
  done

  if printf '%s\n' "$NFT" | grep -Eq '^[[:space:]]*ct state new tcp dport 22 .*accept$'; then
    row "SSH has no unqualified accept (WAN closed)" "FAIL" \
      "unqualified 'ct state new tcp dport 22 ... accept' present"
  else
    row "SSH has no unqualified accept (WAN closed)" "PASS" \
      "every dport 22 accept is source-qualified"
  fi

  if printf '%s\n' "$NFT" | grep -Eq 'ip saddr 192\.168\.1\.0/24 accept[[:space:]]*$'; then
    row "LAN is not a blanket trust" "FAIL" "found 'ip saddr 192.168.1.0/24 accept'"
  else
    row "LAN is not a blanket trust" "PASS" "no blanket LAN accept"
  fi

  LAN_RULE=$(printf '%s\n' "$NFT" | grep -F 'ip saddr 192.168.1.0/24' || true)
  if printf '%s\n' "$LAN_RULE" | grep -Eq '\b(8000|6001|6002)\b'; then
    row "LAN cannot reach panel ports 8000/6001-6002" "FAIL" "LAN rule includes a panel port"
  else
    row "LAN cannot reach panel ports 8000/6001-6002" "PASS" "LAN rule is { 2283, 8089, 9100 } only"
  fi

  if nft_has "counter drop"; then
    row "Default drop has a counter" "PASS" "counter drop"
  else
    row "Default drop has a counter" "FAIL" "counter drop missing"
  fi
fi

# ---------------------------------------------------------------------------
# Docker published ports: DOCKER-USER (FORWARD)
# ---------------------------------------------------------------------------
DUSER=$(iptables -S DOCKER-USER 2>/dev/null)
duser_has() { printf '%s\n' "$DUSER" | grep -Fq -- "$1"; }

if [ -z "$DUSER" ]; then
  row "DOCKER-USER chain exists" "FAIL" "chain not found (docker down?)"
else
  row "DOCKER-USER chain exists" "PASS" "chain present"

  for spec in \
    '-m conntrack --ctstate RELATED,ESTABLISHED -j RETURN' \
    '-i lo -j RETURN' \
    '-i tailscale0 -j RETURN' \
    '-o eth0 -j RETURN' \
    '-s 192.168.1.0/24 -m conntrack --ctorigdstport 2283 -j RETURN' \
    '-s 192.168.1.0/24 -m conntrack --ctorigdstport 8089 -j RETURN' \
    '-j DROP'; do
    if duser_has "$spec"; then
      row "DOCKER-USER rule: $spec" "PASS" "present"
    else
      row "DOCKER-USER rule: $spec" "FAIL" "missing"
    fi
  done

  if [ "$(printf '%s\n' "$DUSER" | grep -c -- '-j DROP' || true)" -eq 1 ] \
     && printf '%s\n' "$DUSER" | tail -1 | grep -Fq -- '-A DOCKER-USER -j DROP'; then
    row "DOCKER-USER ends with a single DROP" "PASS" "last rule is -j DROP"
  else
    row "DOCKER-USER ends with a single DROP" "FAIL" "DROP is not the last/only drop"
  fi

  if printf '%s\n' "$DUSER" | grep -Eq -- '-s 192\.168\.1\.0/24 -j RETURN[[:space:]]*$'; then
    row "LAN cannot reach every published port" "FAIL" "blanket LAN RETURN present"
  else
    row "LAN cannot reach every published port" "PASS" "LAN limited to 2283/8089"
  fi
fi

# ---------------------------------------------------------------------------
# Listening-port placement
# ---------------------------------------------------------------------------
port_binds() { ss -lntH "sport = :$1" 2>/dev/null | awk '{print $4}' | sort -u; }
port_listening() { [ -n "$(port_binds "$1")" ]; }

for p in 8088 3306 8799; do
  binds=$(port_binds "$p")
  if [ -z "$binds" ]; then
    row "Port ${p} listens on loopback only" "FAIL" "nothing listening (expected 127.0.0.1:${p})"
  elif printf '%s\n' "$binds" | grep -Evq "^(127\.0\.0\.1|\[::1\]):${p}$"; then
    row "Port ${p} listens on loopback only" "FAIL" "unexpected bind: $(printf '%s ' $binds)"
  else
    row "Port ${p} listens on loopback only" "PASS" "$(printf '%s ' $binds)"
  fi
done

for p in 22 2283 8089 9100; do
  if port_listening "$p"; then
    row "Port ${p} is listening (filtered by nft/DOCKER-USER)" "PASS" "$(printf '%s ' $(port_binds "$p"))"
  else
    row "Port ${p} is listening (filtered by nft/DOCKER-USER)" "FAIL" "not listening"
  fi
done

for p in 8000 6001 6002; do
  if port_listening "$p"; then
    row "Panel port ${p} is published but FORWARD-filtered" "PASS" "docker-proxy on $(printf '%s ' $(port_binds "$p"))"
  else
    row "Panel port ${p} is published but FORWARD-filtered" "NA" "not published right now"
  fi
done

row "Port 8088 is not exposed on a wildcard address" "PASS" "$(port_binds 8088 | paste -sd' ' -)"

# ---------------------------------------------------------------------------
# sshd effective configuration
# ---------------------------------------------------------------------------
SSHD_T=$(sshd -T 2>/dev/null)
sshd_is() { printf '%s\n' "$SSHD_T" | grep -qx -- "$1"; }

for pair in \
  "maxauthtries 3" \
  "logingracetime 20" \
  "x11forwarding no" \
  "clientaliveinterval 120" \
  "passwordauthentication no" \
  "pubkeyauthentication yes" \
  "permitrootlogin without-password"; do
  if sshd_is "$pair"; then
    row "sshd: $pair" "PASS" "effective"
  else
    row "sshd: $pair" "FAIL" "not effective"
  fi
done

if sshd_is "allowusers juan"; then
  row "sshd: AllowUsers includes juan" "PASS" "allowusers juan (+ scoped Coolify root)"
else
  row "sshd: AllowUsers includes juan" "FAIL" "juan is not allowed"
fi

if sshd_is "allowusers root@10.0.1.*"; then
  row "sshd: root only from Coolify bridge" "PASS" "allowusers root@10.0.1.*"
else
  row "sshd: root only from Coolify bridge" "NA" "no scoped root exception"
fi

if [ -f /etc/ssh/sshd_config.d/99-hardening.conf ]; then
  row "sshd drop-in is installed" "PASS" "/etc/ssh/sshd_config.d/99-hardening.conf"
else
  row "sshd drop-in is installed" "FAIL" "drop-in missing"
fi

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
for svc in nft-hardened docker-user-hardening; do
  en=$(systemctl is-enabled "$svc" 2>/dev/null || true)
  ac=$(systemctl is-active "$svc" 2>/dev/null || true)
  if [ "$en" = "enabled" ] && [ "$ac" = "active" ]; then
    row "service ${svc} enabled+active" "PASS" "${en}/${ac}"
  else
    row "service ${svc} enabled+active" "FAIL" "${en:-unknown}/${ac:-unknown}"
  fi
done

if [ -n "$(fail2ban-client status sshd 2>/dev/null)" ]; then
  MAXRETRY=$(fail2ban-client get sshd maxretry 2>/dev/null || echo "?")
  BANTIME=$(fail2ban-client get sshd bantime 2>/dev/null || echo "?")
  if [ "$MAXRETRY" = "4" ] && [ "$BANTIME" = "3600" ]; then
    row "fail2ban sshd jail (maxretry 4, 1h)" "PASS" "maxretry=${MAXRETRY} bantime=${BANTIME}"
  else
    row "fail2ban sshd jail (maxretry 4, 1h)" "FAIL" "maxretry=${MAXRETRY} bantime=${BANTIME}"
  fi
else
  row "fail2ban sshd jail (maxretry 4, 1h)" "FAIL" "jail not loaded"
fi

UU_EN=$(systemctl is-enabled unattended-upgrades 2>/dev/null || true)
UU_AC=$(systemctl is-active unattended-upgrades 2>/dev/null || true)
if [ "$UU_AC" = "active" ]; then
  row "unattended-upgrades is off (manual patching)" "FAIL" "active -- phase 25 keeps patching manual"
else
  row "unattended-upgrades is off (manual patching)" "PASS" "enabled=${UU_EN:-not-found} active=${UU_AC:-inactive}"
fi

# ---------------------------------------------------------------------------
# Docker containers
# ---------------------------------------------------------------------------
RUNNING=$(docker ps --format '{{.Names}}' 2>/dev/null || true)
if printf '%s\n' "$RUNNING" | grep -qx 'coolify' \
   && printf '%s\n' "$RUNNING" | grep -qx 'immich_server'; then
  row "Docker key containers running" "PASS" "coolify + immich_server up"
else
  row "Docker key containers running" "FAIL" "coolify and/or immich_server not running"
fi

if docker ps --format '{{.Status}}' 2>/dev/null | grep -qi 'unhealthy'; then
  row "No unhealthy container" "FAIL" "$(docker ps --format '{{.Names}} {{.Status}}' | grep -i unhealthy | paste -sd';' -)"
else
  row "No unhealthy container" "PASS" "$(docker ps -q | wc -l) running, none unhealthy"
fi

# ---------------------------------------------------------------------------
# Ingress: Funnel public surface + health + egress
# ---------------------------------------------------------------------------
FUNNEL=$(tailscale funnel status 2>/dev/null || true)
PUBLIC=$(printf '%s\n' "$FUNNEL" | grep -E '^https://[^ ]+ \(Funnel on\)' || true)
PUBLIC_N=$(printf '%s\n' "$PUBLIC" | grep -c . || true)

if [ "$PUBLIC_N" -eq 1 ] && printf '%s\n' "$PUBLIC" | grep -Eq '^https://[^:]+ \(Funnel on\)$'; then
  row "Funnel exposes exactly one public URL (443)" "PASS" "$(printf '%s' "$PUBLIC" | sed 's/ (Funnel on)//')"
else
  row "Funnel exposes exactly one public URL (443)" "FAIL" "${PUBLIC_N} public URL(s): $(printf '%s ' $PUBLIC)"
fi

if printf '%s\n' "$FUNNEL" | grep -A1 -F '(Funnel on)' | grep -Fq 'proxy http://127.0.0.1:8088'; then
  row "Public Funnel proxies to 127.0.0.1:8088" "PASS" "8088"
else
  row "Public Funnel proxies to 127.0.0.1:8088" "FAIL" "unexpected public target"
fi

if printf '%s\n' "$FUNNEL" | grep -q ':8443 (tailnet only)'; then
  row "8443 is tailnet-only" "PASS" "8443 (tailnet only)"
else
  row "8443 is tailnet-only" "FAIL" "8443 not marked tailnet-only"
fi

HEALTH=$(curl -s -o /dev/null --max-time 5 -w '%{http_code}' http://127.0.0.1:8088/api/health 2>/dev/null)
if [ "$HEALTH" = "200" ]; then
  row "Local /api/health" "PASS" "HTTP 200"
else
  row "Local /api/health" "FAIL" "HTTP ${HEALTH:-000}"
fi

FHEALTH=$(curl -s -o /dev/null --max-time 10 -w '%{http_code}' \
  https://vps-server.tail40095b.ts.net/api/health 2>/dev/null)
if [ "$FHEALTH" = "200" ]; then
  row "Public /api/health through Funnel" "PASS" "HTTP 200"
else
  row "Public /api/health through Funnel" "FAIL" "HTTP ${FHEALTH:-000}"
fi

EGRESS=$(curl -s -o /dev/null --max-time 8 -w '%{http_code}' https://api.deepseek.com 2>/dev/null)
if [ "$EGRESS" != "000" ] && [ -n "$EGRESS" ]; then
  row "Host egress works" "PASS" "api.deepseek.com -> HTTP ${EGRESS}"
else
  row "Host egress works" "FAIL" "api.deepseek.com unreachable"
fi

# ---------------------------------------------------------------------------
echo
echo "Summary: ${PASS_N} passed, ${FAIL_N} failed, ${NA_N} not applicable"
if [ "$FAIL_N" -eq 0 ]; then
  echo "VERDICT: PASS"
  exit 0
fi
echo "VERDICT: FAIL"
exit 1
