#!/usr/bin/env bash
# One-time install of the DSI-Wiki Cloudflare Tunnel connector on this host.
# Scoped deliberately to the wiki.* / wiki-api.* / wiki-http.* / wiki-mcp.* hostnames only —
# this host does not run the other dsigames.com.tr projects that share the same tunnel
# (api/mainboard/witch/ihale/providers/ssh), so those are intentionally left out of the
# ingress list here (they 404 instead of silently proxying to a service/SSH port that isn't
# actually running on this box).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

ENV_FILE="${SUDO_USER:+/home/$SUDO_USER/.env}"
ENV_FILE="${ENV_FILE:-/home/ozan/.env}"
DNS_TOKEN=$(grep -m1 '^CLOUDFLARE_DNS_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
ACCOUNT_ID=$(grep -m1 '^CLOUDFLARE_DNS_TOKEN=' "$ENV_FILE" >/dev/null && echo "1050123017121f737539fc84a4c8695f")
TUNNEL_ID="de6ad0d9-e8a0-41b2-818f-ed58c1040f47"

if [ -z "$DNS_TOKEN" ]; then
  echo "CLOUDFLARE_DNS_TOKEN not found in $ENV_FILE" >&2
  exit 1
fi

CONNECTOR_TOKEN=$(curl -sS -H "Authorization: Bearer ${DNS_TOKEN}" -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/token" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['result'])")

if [ -z "$CONNECTOR_TOKEN" ]; then
  echo "Failed to fetch connector token from Cloudflare API." >&2
  exit 1
fi

CLOUDFLARED_BIN="/usr/local/bin/cloudflared"
if [ ! -x "$CLOUDFLARED_BIN" ]; then
  curl -fsSL -o "$CLOUDFLARED_BIN" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$CLOUDFLARED_BIN"
fi

"$CLOUDFLARED_BIN" service install "$CONNECTOR_TOKEN"

mkdir -p /etc/cloudflared
cat > /etc/cloudflared/config.yml <<EOF
tunnel: ${TUNNEL_ID}
token: ${CONNECTOR_TOKEN}
ingress:
  - hostname: wiki.dsigames.com.tr
    service: http://127.0.0.1:8430
  - hostname: wiki-api.dsigames.com.tr
    service: http://127.0.0.1:8430
  - hostname: wiki-http.dsigames.com.tr
    service: http://127.0.0.1:8430
  - hostname: wiki-mcp.dsigames.com.tr
    service: http://127.0.0.1:8430
  - service: http_status:404
EOF
chmod 600 /etc/cloudflared/config.yml

systemctl daemon-reload
systemctl restart cloudflared
sleep 3
systemctl is-active cloudflared
echo "Installed. Verify with: curl -sS https://wiki.dsigames.com.tr/api/instances"
