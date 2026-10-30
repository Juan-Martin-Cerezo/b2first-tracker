# Host hardening — vps-server

> Phase 25. Written 2026-10-30. Every number below was measured on this host;
> commands that produced them are in §2 and §6. This document covers the **host**
> (firewall, Docker forwarding, SSH, fail2ban, patching), not the app.

## 0. Host

| Fact | Value |
| --- | --- |
| Board | Raspberry Pi 5, **8 GB** (`MemTotal` 8062 MB), ARM64, **4 cores** |
| OS | Debian GNU/Linux 13 (trixie), kernel `6.18.34+rpt-rpi-2712` |
| LAN address | `192.168.1.83/24` on `eth0`, gateway `192.168.1.1` |
| Tailnet address | `100.112.213.66` (`vps-server.tail40095b.ts.net`) |
| Public ingress | Tailscale Funnel `https://vps-server.tail40095b.ts.net` → `127.0.0.1:8088` |
| Hostname | `vps-server` |

Two independent filters protect this box:

1. **`table inet hardened`** — `input` hook, `policy drop`. Controls traffic
   addressed to the host itself (SSH, `pi-thermal-monitor`, the app on
   `127.0.0.1:8088`).
2. **`DOCKER-USER`** — `FORWARD` hook. Docker DNATs published ports in
   `nat/PREROUTING` and accepts them in `FORWARD/DOCKER-FORWARD`, so published
   container ports **never traverse the input chain**. `DOCKER-USER` is
   evaluated before `DOCKER-FORWARD`, which makes it the correct place to
   restrict them.

Both are idempotent and applied by systemd units:

| File | Unit |
| --- | --- |
| `/home/juan/.config/nft/hardened.nft` | `nft-hardened.service` |
| `/usr/local/sbin/docker-user-hardening.sh` | `docker-user-hardening.service` |
| `/etc/ssh/sshd_config.d/99-hardening.conf` | `ssh.service` (drop-in) |
| `/etc/fail2ban/jail.local` | `fail2ban.service` |

## 1. Exposure matrix, before → after

Measured from a real `192.168.1.0/24` source with a throwaway network namespace
(§2), not from the host itself — traffic originated on the host uses loopback
and would bypass both the input LAN rules and `DOCKER-USER`.

"Internet" means "what the host filter would accept if the home router forwarded
the port". The router does not forward any of these except the Funnel's 443.

### Before (phase 24 state)

| Port | Service | LAN | Tailnet | Internet (host filter) |
| --- | --- | --- | --- | --- |
| 22/tcp | sshd | **open** | open | **rate-limited accept** (10/min) |
| 2283/tcp | Immich | **200** | open | **accept** (Docker FORWARD, no `DOCKER-USER`) |
| 8089/tcp | existing app | **302** | open | **accept** (Docker FORWARD) |
| 8000/tcp | Coolify panel | **302** | open | **accept** (Docker FORWARD) |
| 6001-6002/tcp | Coolify | **404** | open | **accept** (Docker FORWARD) |
| 9100/tcp | `pi-thermal-monitor` (no auth) | **200** | open | drop |
| 8088/tcp | B2 First app | closed (127.0.0.1) | closed (127.0.0.1) | via Funnel only |
| 3306/tcp | MariaDB | closed (127.0.0.1) | closed | closed |
| 8799/tcp | internal python | closed (127.0.0.1) | closed | closed |

The input chain also contained a **blanket** `ip saddr 192.168.1.0/24 accept`:
every LAN device was trusted for every port the host listened on.

### After (phase 25)

| Port | Service | LAN | Tailnet | Internet (host filter) |
| --- | --- | --- | --- | --- |
| 22/tcp | sshd | **accept, 6/min burst 3** | accept | **drop** (measured) |
| 2283/tcp | Immich | **accept** | accept | **drop** |
| 8089/tcp | existing app | **accept** | accept | **drop** |
| 8000/tcp | Coolify panel | **drop** (measured `000`) | accept | **drop** |
| 6001-6002/tcp | Coolify | **drop** (measured `000`) | accept | **drop** |
| 9100/tcp | `pi-thermal-monitor` | **accept** (read-only) | accept | **drop** |
| 8088/tcp | B2 First app | closed (127.0.0.1) | closed (127.0.0.1) | via Funnel only |
| 3306/tcp | MariaDB | closed (127.0.0.1) | closed | closed |
| 8799/tcp | internal python | closed (127.0.0.1) | closed | closed |

Notes:

- **SSH** is now **LAN + tailnet only**. Phase 25 first left the generic rule
  (`ct state new tcp dport 22 limit rate 6/minute burst 3 accept`) with no source
  qualifier, which the netns probe measured as **open from a simulated internet
  source** (`203.0.113.5` → `22 -> ABIERTO`). That was the last port reachable
  from WAN, so it was qualified on 2026-10-30 by hand:

  ```
  iifname "tailscale0" ct state new tcp dport 22 accept
  ip saddr 192.168.1.0/24 ct state new tcp dport 22 limit rate 6/minute burst 3 accept
  ct state new tcp dport 22 drop
  ```

  Re-measured after the change: LAN `22 -> ABIERTO`, internet `22 -> bloqueado`,
  Funnel `/api/health` still `200`. **Consequence: SSH from outside the house
  requires Tailscale.** That is the intended posture; the LAN rule keeps local
  access working if the tailnet ever breaks.
  Rollback for this change: `/root/hardened.nft.bak-*` (the automated snapshot
  recipe is §3.1).
- **Tailnet** still reaches every service: `iifname "tailscale0" accept` in
  `input` and `-i tailscale0 -j RETURN` in `DOCKER-USER`. This is deliberate —
  Coolify (panel + 6001-6002) is tailnet-only.
- **`pi-thermal-monitor`** still binds `0.0.0.0:9100` and has no auth. It is now
  reachable **only** from LAN and tailnet because the input chain drops every
  other source. Changing the bind is unnecessary; the filter is the control.
- **Coolify's root SSH from `10.0.1.6`** is preserved. Coolify manages this host
  over SSH from its own container; `AllowUsers juan root@10.0.1.*` allows
  `root` only from the Coolify bridge and denies interactive root from LAN and
  tailnet. Without the scoped exception, Coolify deploys would break.
- **Port 3200** (target of the tailnet-only `8443` Funnel) had no listener on
  the day of this phase. That is a pre-existing state, not caused by phase 25;
  the Funnel mapping is unchanged and tailnet-only.

### Why the literal `DOCKER-USER` snippet was tightened

The phase specified `-A DOCKER-USER -s 192.168.1.0/24 -j RETURN`. That returns
**every** LAN packet to **every** published port, so LAN would still reach the
Coolify panel on 8000 and 6001-6002 — contradicting the matrix above and step
E.5 ("8000 from LAN must fail"). The deployed rules restrict LAN to the two
services that need it, matching the original destination port before DNAT
(`8089` maps to container port `80`):

```
-A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN
-A DOCKER-USER -i lo -j RETURN
-A DOCKER-USER -i tailscale0 -j RETURN
-A DOCKER-USER -o eth0 -j RETURN
-A DOCKER-USER -s 192.168.1.0/24 -m conntrack --ctorigdstport 2283 -j RETURN
-A DOCKER-USER -s 192.168.1.0/24 -m conntrack --ctorigdstport 8089 -j RETURN
-A DOCKER-USER -j DROP
```

`-o eth0 -j RETURN` is required because this chain sees **all** forwarding, not
only inbound published ports: without it, `NEW` container egress (image pulls,
DeepSeek, etc.) would be dropped. Verified with `wget` inside the `coolify`
container reaching `api.deepseek.com` (HTTP 401 = reachable, unauthenticated).

## 2. Verification (reproducible)

```bash
# 1. Local host audit: 55 checks, exits non-zero on any FAIL.
sudo bash tools/audit-host.sh

# 2. Idempotency: apply twice, same stateless sha.
sudo nft -f /home/juan/.config/nft/hardened.nft
nft -s list table inet hardened | sha256sum
sudo nft -f /home/juan/.config/nft/hardened.nft
nft -s list table inet hardened | sha256sum   # identical

# 3. DOCKER-USER is idempotent too.
sudo /usr/local/sbin/docker-user-hardening.sh   # "already applied" on a second run
sudo iptables -S DOCKER-USER

# 4. Real LAN-source probe (creates and deletes a netns + veth).
#    Expect: 22 open, 2283 200, 8089 302, 9100 200,
#            8000/6001/6002/8088/3306/8799 000.
#    The probe script lives in the phase scratchpad; it is not a repo artifact.
```

Why `nft -s` for the idempotency sha: the plain `nft list table` includes live
counter values, so its hash changes every time a packet hits `counter drop`.
`-s` (`--stateless`) omits them and is the stable comparison.

Evidence from the day of the phase:

```
# nft: 3 consecutive applications
first= c60dc55c870bb97468418e260deace500498b1a7d9731984d6aae5770a68fd3e
second=c60dc55c870bb97468418e260deace500498b1a7d9731984d6aae5770a68fd3e
third= c60dc55c870bb97468418e260deace500498b1a7d9731984d6aae5770a68fd3e

# LAN probe, after
22     open
2283   200
8089   302
8000   000
6001   000
6002   000
9100   200
8088   000
3306   000
8799   000
```

## 3. Rollback

There are two layers. Rolling back the host firewall must never require a
reboot.

### 3.1 nftables — `table inet hardened`

`nft list ruleset` is **not** a valid rollback: re-applying it adds duplicate
rules instead of restoring. That is exactly how the duplicated ruleset found at
the start of phase 25 was produced. Snapshot only your own table.

> Pitfall hit during this phase: `sudo nft list ... > /root/file` runs the
> redirection as your user, before `sudo`, and silently fails. Use `sudo tee`
> or `sudo sh -c '... > file'`.

```bash
# 1. Snapshot only our table.
sudo nft list table inet hardened | sudo tee /root/hardened-snapshot.nft >/dev/null
sudo chmod 600 /root/hardened-snapshot.nft

# 2. Rollback script.
sudo tee /root/nft-rollback.sh >/dev/null <<'EOF'
#!/bin/bash
/usr/sbin/nft delete table inet hardened 2>/dev/null
/usr/sbin/nft -f /root/hardened-snapshot.nft
logger -t nft-rollback "nft hardened restored from snapshot"
EOF
sudo chmod 700 /root/nft-rollback.sh

# 3. Test the rollback BEFORE applying anything. It must restore the same table.
sudo nft -s list table inet hardened | sha256sum
sudo /root/nft-rollback.sh
sudo nft -s list table inet hardened | sha256sum      # same
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/api/health  # 200

# 4. Arm the automatic rollback, apply, verify, disarm.
sudo systemd-run --on-active=150 --unit=nft-auto-rollback /root/nft-rollback.sh
sudo nft -f /home/juan/.config/nft/hardened.nft
# ... verification (see §2) within the 150 s window ...
sudo systemctl stop nft-auto-rollback.timer nft-auto-rollback.service 2>/dev/null

# If something fails, do nothing: the timer restores the snapshot after 150 s.
# Then confirm the sha is back and report the failure with evidence.
```

Rollback evidence from phase 25: the pre-phase table was the duplicated ruleset
(plain sha `e46b561f…`); `/root/nft-rollback.sh` restored exactly that table
(stateless `e381d81f…`, plain `e46b561f…`), services stayed at HTTP 200.

Auto-rollback is armed with a **transient** systemd timer; it disappears after
it fires or is stopped. Never leave it armed after a successful change.

### 3.2 Docker `DOCKER-USER`

```bash
sudo systemctl disable --now docker-user-hardening.service
sudo iptables -F DOCKER-USER
```

Docker preserves `DOCKER-USER` when containers are recreated, but it does not
restore rules after a manual flush or a host reboot — hence the oneshot unit
(`After=docker.service`, `RemainAfterExit=yes`).

### 3.3 SSH

```bash
sudo rm /etc/ssh/sshd_config.d/99-hardening.conf
sudo sshd -t && sudo systemctl reload ssh
```

Never edit `/etc/ssh/sshd_config` for these knobs; the drop-in wins and is the
single rollback point.

### 3.4 fail2ban

```bash
sudo systemctl disable --now fail2ban
sudo fail2ban-client unban --all    # if a legitimate IP was banned
```

Emergency unban while the service is running:
`sudo fail2ban-client set sshd unbanip <IP>`.

## 4. SSH policy

`/etc/ssh/sshd_config.d/99-hardening.conf`:

```
MaxAuthTries 3
LoginGraceTime 20
AllowUsers juan root@10.0.1.*
X11Forwarding no
ClientAliveInterval 120
```

Unchanged and still in force: key-only (`PasswordAuthentication no`),
`PermitRootLogin without-password`, `UsePAM yes`. Effective values are checked
by `sshd -T` in `tools/audit-host.sh`.

`sshd` listens on `0.0.0.0:22` and `[::]:22`. Two established root sessions from
`10.0.1.6` (Coolify) were present during the phase and survived the reload.

## 5. fail2ban

Installed from Debian trixie (`1.1.0-8`, 16 packages, ~9 MB installed — far
below the 200 MB threshold). Debian's default action is `nftables`, the sshd
jail reads the systemd journal.

`/etc/fail2ban/jail.local`:

```
[DEFAULT]
backend = systemd
bantime = 1h
findtime = 10m
maxretry = 4
ignoreip = 127.0.0.1/8 ::1 192.168.1.0/24

[sshd]
enabled = true
backend = systemd
maxretry = 4
bantime = 1h
```

Design choice: the **LAN is ignored** so a mistake can never remove the
recovery path to the host. The **tailnet is not ignored**, so a compromised
tailnet device can still be banned. Internet sources cannot reach `:22` on this
host anyway (nft input policy), so fail2ban is the second layer, not the gate.

Verified end to end: `banip 203.0.113.99` created the nft address set element,
`unbanip` removed it, two Coolify SSH sessions stayed up.

## 6. Monthly patching runbook (manual by design)

`unattended-upgrades` is **not installed/enabled** on this host and must stay
that way (Juan patches manually). At phase time `apt-get -s` reported 190
packages pending; schedule a window and run:

```bash
# 1. Refresh and review.
sudo apt-get update
apt-get --just-print upgrade | grep -c '^Inst '      # count pending
sudo apt-get full-upgrade -y

# 2. Remove obsolete packages.
sudo apt-get autoremove -y
sudo apt-get autoclean

# 3. Reboot if the kernel, libc, systemd, ssh or docker changed.
#    Check first:  sudo needrestart -b   (if installed)
#    Reboot is expected and safe: the app, Docker and Coolify all come back
#    via systemd. Do it from a tailnet/LAN session and reconnect.
sudo reboot

# 4. Verify after the reboot.
sudo bash tools/audit-host.sh                 # must be VERDICT: PASS
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/api/health   # 200
curl -s -o /dev/null -w '%{http_code}\n' https://vps-server.tail40095b.ts.net/api/health  # 200
sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E 'coolify|immich'
sudo systemctl --failed
sudo nft -s list table inet hardened | sha256sum     # same as before reboot
sudo iptables -S DOCKER-USER
```

If the reboot happens while `nft-hardened.service` or
`docker-user-hardening.service` is broken, the host comes up with Docker's
FORWARD chain accepting published ports and no input filtering. That is why the
post-reboot `audit-host.sh` is part of the runbook, not optional.

## 7. Residual risks (honest)

- SSH accepts new connections from any routable source at 6/min (the explicit
  phase rule). The home NAT does not forward 22. Tighten with `ip saddr
  192.168.1.0/24` if that changes.
- `pi-thermal-monitor` has no authentication. Network placement (LAN/tailnet)
  is the only control.
- Coolify `root` over SSH from `10.0.1.0/24` is key-only but privileged. The
  bridge is internal; a compromised Coolify container already has a foothold on
  the host's Docker socket.
- Tailnet is trusted for all services. That is intentional and required for
  Coolify; device hygiene is the control.
- The `8443` Funnel target (`127.0.0.1:3200`) had no listener at phase time. It
  is tailnet-only and does not expose anything, but it is dead configuration
  until the service returns.
