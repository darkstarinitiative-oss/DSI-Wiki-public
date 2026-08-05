#!/usr/bin/env bash
# Full API/CLI/MCP/health test suite. Run this after every update, before tagging
# a release (see INDEP_GIT_RULES). Prints a markdown table + pass/fail totals;
# non-zero exit if anything failed.
#
# Requires: the stack already running (docker compose up -d), CLI proxies
# installed (TOOLS/install-cli-proxies.sh), cloudflared + dsi-wiki-factcheck.timer
# installed if you want the public/health checks to run too.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"

INSTANCE="${1:-Cain-the-elder}"
pass=0; fail=0; rows=()

run() {
  local desc="$1" actual="$2" pattern="$3"
  if echo "$actual" | grep -qE "$pattern"; then
    rows+=("| $desc | PASS |"); pass=$((pass+1))
  else
    rows+=("| $desc | FAIL |"); fail=$((fail+1))
  fi
}

run "API GET /api/instances" "$(curl -sS --max-time 8 http://localhost:8430/api/instances)" "\"$INSTANCE\""
run "API GET /api/topics" "$(curl -sS --max-time 8 "http://localhost:8430/api/topics?instance=$INSTANCE&layer=minified")" 'MAIN_'
run "API GET /api/wiki" "$(curl -sS --max-time 8 "http://localhost:8430/api/wiki?instance=$INSTANCE&topic=MAIN_SYSTEM&layer=brief")" '"content"'
run "API GET /api/search" "$(curl -sS --max-time 8 "http://localhost:8430/api/search?instance=$INSTANCE&q=DSI-Wiki&layer=documentation")" '"results"'
run "API GET /api/status" "$(curl -sS --max-time 8 http://localhost:8430/api/status)" '"last_poll_ts"'
run "API GET /api/info" "$(curl -sS --max-time 8 http://localhost:8430/api/info)" '"status"'
run "HTTP /http/dashboard" "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 http://localhost:8430/http/dashboard)" '^200$'
run "HTTP /http/info-viewer" "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 http://localhost:8430/http/info-viewer)" '^200$'
run "HTTP /http/api/health" "$(curl -sS --max-time 8 http://localhost:8430/http/api/health)" 'services'
run "CLI DSI-wiki-topics" "$(DSI-wiki-topics --instance "$INSTANCE" --layer minified 2>&1)" 'MAIN_'
run "CLI DSI-wiki-get" "$(DSI-wiki-get MAIN_SYSTEM --layer brief --instance "$INSTANCE" 2>&1)" '.'
run "CLI DSI-wiki-search" "$(DSI-wiki-search DSI-Wiki --instance "$INSTANCE" --layer documentation 2>&1)" '.'

MCP_INIT=$(curl -sS --max-time 10 -X POST http://localhost:8430/mcp/ \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"dsi-test","version":"1.0"}}}')
run "MCP initialize" "$MCP_INIT" '"serverInfo"'

BACKEND_KEY_TEST=$(REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" python3 -c "
import sys, os
sys.path.insert(0, os.path.join(os.environ['REPO_ROOT'], 'CODE'))
os.environ['LLM_WIKI_OLLAMA_API_KEY'] = 'test-key-not-real'
import importlib
import common.ollama_lock as ol
importlib.reload(ol)
import urllib.request
captured = {}
orig = urllib.request.urlopen
def fake_urlopen(req, timeout=None):
    captured['auth'] = req.get_header('Authorization')
    raise SystemExit(0)  # short-circuit before any real network call
urllib.request.urlopen = fake_urlopen
try:
    ol.call_ollama('m', [{'role': 'user', 'content': 'x'}], timeout=1)
except SystemExit:
    pass
print('OK' if captured.get('auth') == 'Bearer test-key-not-real' else 'MISSING')
" 2>&1)
run "Pluggable backend: LLM_WIKI_OLLAMA_API_KEY sends Authorization header" "$BACKEND_KEY_TEST" '^OK$'

run "Health: gateway container running" "$(docker inspect -f '{{.State.Status}}' services-gateway-1 2>&1)" '^running$'
run "Health: ingest container running" "$(docker inspect -f '{{.State.Status}}' services-ingest-1 2>&1)" '^running$'
run "Health: ollama reachable" "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:11434/api/tags)" '^200$'
run "Health: cloudflared.service active" "$(systemctl is-active cloudflared 2>&1)" '^active$'
run "Health: dsi-wiki-factcheck.timer active" "$(systemctl is-active dsi-wiki-factcheck.timer 2>&1)" '^active$'

echo "| Test | Result |"
echo "|---|---|"
printf '%s\n' "${rows[@]}"
echo
echo "TOTAL: pass=$pass fail=$fail  ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
[ "$fail" -eq 0 ]
