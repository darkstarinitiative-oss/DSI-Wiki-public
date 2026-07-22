#!/bin/bash
# End-to-end package test: build the image (runs setup.sh --no-systemd inside),
# start the gateway, verify the API serves a seeded topic. Exit 0 = package OK.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG=dsi-wiki-test
CTR=dsi-wiki-test-run
PORT=18430

cleanup() { docker rm -f "$CTR" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== build =="
docker build -t "$IMG" "$ROOT"

echo "== run =="
cleanup
docker run -d --name "$CTR" -p "$PORT:8430" "$IMG"

echo "== seed topic =="
docker exec "$CTR" sh -c 'echo "# Docker packaging smoke topic" > /data/base/minified/DOCKER_SMOKE.md'

echo "== wait for gateway =="
for i in $(seq 1 30); do
    curl -sf "http://localhost:$PORT/api/instances" >/dev/null 2>&1 && break
    sleep 1
    [ "$i" = 30 ] && { echo "FAIL: gateway never came up"; docker logs "$CTR"; exit 1; }
done

echo "== checks =="
curl -sf "http://localhost:$PORT/api/instances" | grep -q containertest \
    || { echo "FAIL: instance missing from /api/instances"; exit 1; }
curl -sf "http://localhost:$PORT/api/topics?instance=containertest&layer=minified" | grep -q DOCKER_SMOKE \
    || { echo "FAIL: seeded topic not listed"; exit 1; }
curl -sf "http://localhost:$PORT/api/wiki?instance=containertest&topic=DOCKER_SMOKE&layer=minified" | grep -q "smoke topic" \
    || { echo "FAIL: topic content not served"; exit 1; }
docker exec "$CTR" python3 /app/_Python/cli/wiki_topics.py --instance containertest --layer minified | grep -q DOCKER_SMOKE \
    || { echo "FAIL: CLI read inside container failed"; exit 1; }

echo "== PASS: package installs, gateway serves, CLI reads =="
