#!/bin/bash
# DSI-Wiki setup — creates the ingest .env + first instance, adapts systemd
# units/config to this clone's path, then runs the supervisor (installs +
# starts the services). This is the non-Docker path.
#
# Docker is the primary supported path — see SERVICES/DEPLOY.md:
#   cp SERVICES/.env.example SERVICES/.env   # fill in host paths
#   docker compose -f SERVICES/docker-compose.yml up -d
#
#   ./setup.sh              interactive, installs systemd --user services
#   ./setup.sh --no-systemd skip supervisor/systemd (e.g. inside a container
#                           build); prints foreground run commands instead
#
# Non-interactive: pre-answer via env vars WIKI_RAW_DIR, WIKI_ARCHIVE_DIR,
# WIKI_INSTANCE_NAME, WIKI_BASE_DIR.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ING="$ROOT/CODE/ingest"
NO_SYSTEMD=0
[ "${1:-}" = "--no-systemd" ] && NO_SYSTEMD=1

ask() { # ask VAR "prompt" "default"
    local var="$1" prompt="$2" def="$3" val
    if [ -n "${!var:-}" ]; then return 0; fi
    read -r -p "$prompt [$def]: " val || val=""
    printf -v "$var" '%s' "${val:-$def}"
}

echo "== DSI-Wiki setup ($ROOT) =="

# 1. .env
if [ -f "$ING/.env" ]; then
    echo " * $ING/.env exists, keeping it."
else
    ask WIKI_RAW_DIR      "Raw notes drop dir"      "$HOME/Wiki-RAW"
    ask WIKI_ARCHIVE_DIR  "Ingested-note archive"   "$HOME/Wiki-ARCHIVE"
    sed -e "s|^LLM_WIKI_RAW_DIR=.*|LLM_WIKI_RAW_DIR=$WIKI_RAW_DIR|" \
        -e "s|^LLM_WIKI_ARCHIVE_DIR=.*|LLM_WIKI_ARCHIVE_DIR=$WIKI_ARCHIVE_DIR|" \
        -e "s|^LLM_WIKI_ROUTES=.*|LLM_WIKI_ROUTES=$ROOT/JSONS/DSI-Wiki-Multi-Server-Config.json|" \
        -e "s|^INSTANCES_DIR=.*|INSTANCES_DIR=$ROOT/JSONS/instances|" \
        "$ROOT/SERVICES/.env.example" > "$ING/.env"
    mkdir -p "$WIKI_RAW_DIR" "$WIKI_ARCHIVE_DIR"
    echo " * $ING/.env created."
fi

# 2. First instance (no keyword/tag -> becomes the default route)
if ls "$ROOT/JSONS/instances"/*.json 2>/dev/null | grep -qv default.json; then
    echo " * JSONS/instances/ already has a non-default instance, keeping it."
else
    ask WIKI_INSTANCE_NAME "Instance name"          "main"
    ask WIKI_BASE_DIR      "Instance base_dir"      "$HOME/Wiki-BASE"
    printf '{\n  "name": "%s",\n  "base_dir": "%s",\n  "enabled": true\n}\n' \
        "$WIKI_INSTANCE_NAME" "$WIKI_BASE_DIR" > "$ROOT/JSONS/instances/$WIKI_INSTANCE_NAME.json"
    mkdir -p "$WIKI_BASE_DIR"/{documentation,llm,minified}
    echo " * JSONS/instances/$WIKI_INSTANCE_NAME.json created."
fi

# 3. Adapt systemd unit + config paths to this clone
for f in "$ROOT"/SERVICES/*.service "$ROOT"/JSONS/DSI-Wiki-HTTP-Config.json; do
    sed -i "s|/home/user/BASE/MAIN/DSI-Wiki|$ROOT|g" "$f"
done
echo " * unit + config paths point at $ROOT."

# 4. Supervisor (generates routing config, installs + starts services)
if [ "$NO_SYSTEMD" = 1 ]; then
    # Only rebuild the routing config — skip the systemd install/start step.
    python3 - <<EOF
import importlib.util
spec = importlib.util.spec_from_file_location("sup", "$ROOT/TOOLS/DSI-Wiki-Service-Supervisor.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.rebuild_multi_server_config()
EOF
    echo " * --no-systemd: services not installed. Run in foreground with:"
    echo "     set -a; . $ING/.env; set +a"
    echo "     python3 $ING/DSI-Wiki-Ingest-Service-Class.py       # ingest daemon"
    echo "     python3 $ROOT/CODE/gateway/DSI-Wiki-HTTP-Server.py  # gateway :8430"
else
    python3 "$ROOT/TOOLS/DSI-Wiki-Service-Supervisor.py"
fi

echo "== done =="
