#!/usr/bin/env bash
# One-time install of the DSI-Wiki Cloudflare Tunnel connector on this host.
# Scoped deliberately to wiki-prefixed hostnames on the configured domain only — other
# unrelated projects that may share the same account tunnel are intentionally left out of the
# ingress list here (they 404 instead of silently proxying to a service/SSH port that isn't
# actually running on this box).
#
# No real Cloudflare account/tunnel/domain identifiers are hardcoded here — all of them come
# from ~/.env (gitignored, per INDEP_GIT_RULES), read fresh on every run:
#   CLOUDFLARE_DNS_TOKEN       -- API token with dns_records:edit/read, zone:read on the zone
#   CLOUDFLARE_ACCOUNT_ID      -- Cloudflare account ID
#   CLOUDFLARE_TUNNEL_ID       -- the account tunnel's ID (cfd_tunnel)
#   CLOUDFLARE_DNS_ZONE        -- the domain, e.g. example.com (DNS records must already exist
#                                 pointing wiki*.<zone> at this tunnel -- this script only
#                                 installs the local connector + ingress, it doesn't create DNS)
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

ENV_FILE="${SUDO_USER:+/home/$SUDO_USER/.env}"
ENV_FILE="${ENV_FILE:-/home/user/.env}"
_get() { grep -m1 "^$1=" "$ENV_FILE" | cut -d= -f2-; }
DNS_TOKEN=$(_get CLOUDFLARE_DNS_TOKEN)
ACCOUNT_ID=$(_get CLOUDFLARE_ACCOUNT_ID)
TUNNEL_ID=$(_get CLOUDFLARE_TUNNEL_ID)
DOMAIN=$(_get CLOUDFLARE_DNS_ZONE)

for var_name in DNS_TOKEN ACCOUNT_ID TUNNEL_ID DOMAIN; do
  if [ -z "${!var_name}" ]; then
    echo "Missing ${var_name} (as CLOUDFLARE_*) in $ENV_FILE" >&2
    exit 1
  fi
done

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
  - hostname: wiki.${DOMAIN}
    service: http://127.0.0.1:8430
  - hostname: wiki-api.${DOMAIN}
    service: http://127.0.0.1:8430
  - hostname: wiki-http.${DOMAIN}
    service: http://127.0.0.1:8430
  - hostname: wiki-mcp.${DOMAIN}
    service: http://127.0.0.1:8430
  - service: http_status:404
EOF
chmod 600 /etc/cloudflared/config.yml

systemctl daemon-reload
systemctl restart cloudflared
sleep 3
systemctl is-active cloudflared
echo "Installed. Verify with: curl -sS https://wiki.${DOMAIN}/api/instances"
