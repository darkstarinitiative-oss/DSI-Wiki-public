#!/bin/bash
# End-to-end package test for the gateway container: build the shared image (SERVICES/Dockerfile),
# run just the gateway, seed a topic directly (bypassing Ollama — this checks packaging/serving,
# not the LLM pipeline), verify the API and in-container CLI both read it back. Exit 0 = package OK.
#
# Does NOT exercise ingest→Ollama→layers — that needs a real, fast-enough Ollama and is verified
# separately (see SERVICES/DEPLOY.md) rather than here.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG=dsi-wiki-test
CTR=dsi-wiki-test-run
PORT=18430
INSTANCE=default-instance

cleanup() { docker rm -f "$CTR" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== build =="
docker build -t "$IMG" -f "$ROOT/SERVICES/Dockerfile" "$ROOT"

echo "== run =="
cleanup
docker run -d --name "$CTR" -p "$PORT:8430" "$IMG"

echo "== seed topic =="
docker exec "$CTR" sh -c 'mkdir -p /data/base/minified && echo "# Docker packaging smoke topic" > /data/base/minified/DOCKER_SMOKE.md'

echo "== wait for gateway =="
for i in $(seq 1 30); do
    curl -sf "http://localhost:$PORT/api/instances" >/dev/null 2>&1 && break
    sleep 1
    [ "$i" = 30 ] && { echo "FAIL: gateway never came up"; docker logs "$CTR"; exit 1; }
done

echo "== checks =="
curl -sf "http://localhost:$PORT/api/instances" | grep -q "$INSTANCE" \
    || { echo "FAIL: instance missing from /api/instances"; exit 1; }
curl -sf "http://localhost:$PORT/api/topics?instance=$INSTANCE&layer=minified" | grep -q DOCKER_SMOKE \
    || { echo "FAIL: seeded topic not listed"; exit 1; }
curl -sf "http://localhost:$PORT/api/wiki?instance=$INSTANCE&topic=DOCKER_SMOKE&layer=minified" | grep -q "smoke topic" \
    || { echo "FAIL: topic content not served"; exit 1; }
docker exec "$CTR" python3 /app/SKILLS/cli/wiki_topics.py --instance "$INSTANCE" --layer minified | grep -q DOCKER_SMOKE \
    || { echo "FAIL: CLI read inside container failed"; exit 1; }
curl -s "http://localhost:$PORT/api/status" | grep -qE '"service"|STATUS.json not yet written' \
    || { echo "FAIL: /api/status endpoint not responding as expected"; exit 1; }

echo "== PASS: package builds, gateway serves, CLI reads, /api/status responds =="
