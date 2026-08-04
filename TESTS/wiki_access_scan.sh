#!/bin/bash
# wiki_access_scan.sh — find internal scripts using deprecated wiki access
# (direct Wiki-BASE file reads, internal HTTP to the 8430 gateway, internal MCP).
# Usage: wiki_access_scan.sh scan    -> write offender list to reports/wiki-access-sunnet.md, exit 0
#        wiki_access_scan.sh verify  -> exit 0 if no offenders remain, 1 otherwise
PAT='mcp__llm-wiki|localhost:8430|127\.0\.0\.1:8430|CLEANUP/DATA/Wiki-BASE'
REPORT=/home/ozan/CLEANUP/MAIN/DSI-Wiki/reports/wiki-access-sunnet.md

scan() {
    grep -rn -E "$PAT" /home/ozan/READY /home/ozan/.local/bin /home/ozan/codebase/projects \
        --include='*.py' --include='*.sh' \
        --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=node_modules 2>/dev/null \
        | grep -v 'DSI-Wiki/' | grep -v '_nightly_factcheck_logs'
}

case "$1" in
    scan)   scan > "$REPORT"; cat "$REPORT"; exit 0 ;;
    verify) if scan | grep -q .; then scan; exit 1; else echo CLEAN; exit 0; fi ;;
    *)      echo "usage: $0 scan|verify" >&2; exit 2 ;;
esac
