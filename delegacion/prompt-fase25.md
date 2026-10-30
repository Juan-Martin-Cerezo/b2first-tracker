# PROMPT — Fase 25: host multi-propósito endurecido (red + docker)

Sos ingeniero senior de seguridad de infraestructura Linux. Host: **Raspberry Pi 5, 8 GB, ARM**,
`vps-server`. Repo `/home/juan/b2first-tracker` (la app vive en este host, pero esta fase es del
**host**, no de la app). **CODIFICAR.** Inglés en docs/commits.

## Reglas de seguridad para VOS como agente (leelas dos veces)

1. **Nunca** dejes el host sin SSH. `sshd` escucha en 22 y Juan entra por LAN y por tailnet.
2. **Nunca** toques las reglas de `iifname "lo"` ni `iifname "tailscale0"`, ni el `udp dport 41641`.
3. Aplicá **siempre** con rollback armado (abajo). Si el rollback dispara, la fase falló: no lo
   des por bueno.
4. No reinicies `docker`, ni Coolify, ni Immich. Solo cambian reglas de filtrado y bindings.
5. No toques `fcc-claude` ni el `docker-proxy` de 8080 (no existe hoy, pero no lo crees).

## Estado real medido (todo verificado hoy, no supongas)

```
nft: table inet hardened, chain input policy drop, PERO:
     ip saddr 192.168.1.0/24 accept        <-- toda la LAN es de confianza
     (las reglas están DUPLICADAS: el archivo se aplicó dos veces)
     archivo: /home/juan/.config/nft/hardened.nft  (servicio nft-hardened.service)

docker publica en 0.0.0.0 y SALTEА el input chain (DNAT en ip nat PREROUTING + FORWARD accept):
     2283 immich_server     200 desde la LAN
     8000 coolify (panel)   302 desde la LAN
     8089 app random        302
     6001/6002 coolify      404
     9100 pi-thermal-monitor (python, sin auth) 200   <-- métricas abiertas
     22 sshd (key-only, PermitRootLogin without-password, sin fail2ban)

funnel: SOLO 8088 público a 127.0.0.1:8088 (+ 8443 tailnet-only → 127.0.0.1:3200). Correcto.
```

## A — UN solo ruleset, idempotente, sin duplicados

- Reescribí `/home/juan/.config/nft/hardened.nft` completo, con `flush ruleset` explícito al
  principio **solo** de la tabla propia (`delete table inet hardened` + `table inet hardened {...}`)
  para que aplicarlo dos veces dé exactamente el mismo resultado. Verificalo: aplicar dos veces
  seguidas y comparar `nft list table inet hardened | sha256sum`.
- La política de LAN deja de ser "todo confiable". Reemplazá `ip saddr 192.168.1.0/24 accept` por
  puertos explícitos:

| Puerto | Origen permitido | Servicio |
| --- | --- | --- |
| 22/tcp | LAN + tailnet | sshd (rate limit 6/min, burst 3) |
| 2283/tcp | LAN + tailnet | Immich |
| 9100/tcp | LAN + tailnet | pi-thermal-monitor (solo lectura) |
| 8089/tcp | LAN + tailnet | app existente |
| 6001-6002/tcp | **solo tailnet** | Coolify (no necesita LAN) |
| 8000/tcp | **solo tailnet** | panel Coolify |
| 8088/tcp | **solo lo** | la app (el Funnel entra por 127.0.0.1) |
| 3306, 8799 | nadie | ya están en 127.0.0.1 |

Todo lo demás: `drop` con contador. Mantené el `limit rate` en SSH y agregá
`ct state new tcp dport 22 limit rate 6/minute burst 3 accept` (hoy es 10/min).

## B — Docker deja de saltear el firewall

Los puertos publicados por docker **no pasan por el input chain**: hay que frenarlos en FORWARD
con la cadena `DOCKER-USER` (iptables-nft). Reglas exactas, en este orden:

```
-A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
-A DOCKER-USER -i lo -j RETURN
-A DOCKER-USER -i tailscale0 -j RETURN
-A DOCKER-USER -s 192.168.1.0/24 -j RETURN
-A DOCKER-USER -j DROP
```

- Persistencia: unit `docker-user-hardening.service` (oneshot, `After=docker.service`,
  `RemainAfterExit=yes`) que las aplica al boot, con el mismo criterio de idempotencia
  (`iptables -C` antes de `-I`). Docker **respeta** el contenido de `DOCKER-USER` al recrear.
- Probá que no rompe nada: contenedores levantan, Immich responde desde la LAN, Coolify desde
  tailnet, y el host sigue saliendo a internet (`curl -sI https://api.deepseek.com`).

## C — Contenedores y servicios

- `pi-thermal-monitor` (`/home/juan/pi-thermal-monitor/app.py`): sigue escuchando en 0.0.0.0 pero
  ahora **solo accesible desde LAN/tailnet** por la regla de nft. Documentalo.
- **No** cambies los `compose` de Immich ni Coolify: el filtrado se hace en FORWARD (menos
  invasivo y reversible).

## D — SSH y parcheo

- `sshd`: `MaxAuthTries 3`, `LoginGraceTime 20`, `AllowUsers juan`, `X11Forwarding no`,
  `ClientAliveInterval 120`. Escribí un drop-in en `/etc/ssh/sshd_config.d/`, **no** edites el
  principal. Validá con `sshd -t` **antes** de `systemctl reload ssh`.
- `unattended-upgrades` está inactivo y Juan prefiere actualizaciones manuales: **no lo actives**.
  En cambio, agregá al `HANDOFF.md` un runbook de parcheo mensual con el comando exacto y la
  verificación posterior.
- `fail2ban`: si `apt-get install` funciona sin arrastrar 200 MB, instalalo con una jail para
  `sshd` (maxretry 4, bantime 1h, backend systemd). Si no, documentá que el rate limit de nft es
  el control vigente. No inventes que está instalado.

## E — Procedimiento de aplicación con rollback (obligatorio)

```bash
# 1. snapshot SOLO de nuestra tabla (nft list ruleset NO sirve como rollback:
#    reaplicarlo AGREGA reglas duplicadas en vez de restaurar -- así se duplicó
#    el ruleset que hay hoy).
sudo nft list table inet hardened > /root/hardened-snapshot.nft
sudo cat > /root/nft-rollback.sh <<'EOF'
#!/bin/bash
/usr/sbin/nft delete table inet hardened 2>/dev/null
/usr/sbin/nft -f /root/hardened-snapshot.nft
logger -t nft-rollback "nft hardened restaurado desde snapshot"
EOF
sudo chmod +x /root/nft-rollback.sh
# 2. probá el rollback AHORA, antes de aplicar nada: tiene que dejar la tabla
#    idéntica (mismo sha256) y el servicio 200. Si el rollback no funciona,
#    no apliques la fase.
sudo /root/nft-rollback.sh && sudo nft list table inet hardened | sha256sum
# 3. armar el rollback automático ANTES de aplicar
sudo systemd-run --on-active=150 --unit=nft-auto-rollback /root/nft-rollback.sh
# 4. aplicar
sudo nft -f /home/juan/.config/nft/hardened.nft
# 5. verificar TODO esto
#    - curl -s -o /dev/null -w '%{http_code}' https://vps-server.tail40095b.ts.net/api/health   -> 200
#    - curl -s from LAN IP on 2283 -> 200 ; on 8000 from LAN -> debe FALLAR ahora (tailnet only)
#    - tailscale status | head -3  (sin cambios)
#    - ss -tlnp | grep -c LISTEN  (mismo conteo o más, nunca menos por servicios caídos)
#    - docker ps --format '{{.Names}} {{.Status}}' | grep -c healthy  (igual o más)
#    - timeout 5 bash -c 'echo > /dev/tcp/192.168.1.83/22' && echo ssh-lan-ok
# 6. solo si TODO pasa:
sudo systemctl stop nft-auto-rollback.timer nft-auto-rollback.service 2>/dev/null
```

Si algo falla: **dejá que el rollback dispare**, esperá 160 s, verificá que volvió
(`sha256sum` del ruleset igual al snapshot) y reportá el fallo con la evidencia.

## F — Entregables

- `docs/HOST-HARDENING.md`: matriz **antes/después** de exposición (puerto → quién llega antes /
  quién después), el procedimiento de rollback, y el runbook de parcheo mensual.
- `tools/audit-host.sh`: checks locales (nft sin duplicados, DOCKER-USER presente, puertos
  escuchando en lo que corresponde, sshd `-T` con los valores esperados, `funnel` solo 8088).
  PASS/FAIL con evidencia, exit non-zero si algo falla. **Corrélo y pegá la salida en el commit.**
- `HANDOFF.md`: §4 (SSH/parcheo), §7 (tabla de controles) y §14 (runbook) actualizados. Agregá
  el dato real del host: **Pi 5 8 GB**, 4 cores.
- Dos commits: `security(host): ...` y `docs(host): exposure matrix and rollback runbook`.
