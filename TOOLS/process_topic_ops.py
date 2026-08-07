#!/usr/bin/env python3
"""Processes topic-ops requests dropped by the Gateway's /api/delete_topic_request and
/api/factcheck_request (WIKI_RAW_DIR/_ops/*.json, one file per request) -- run externally
(host cron, every minute, same as TOOLS/write_ingest_status.py), never from inside the
ingest daemon's own poll loop: that loop already blocks on real ingest work sometimes, and
a browser-triggered delete/fact-check queuing up behind a slow LLM ingest call is the exact
"self-report from inside a process that can stall" problem STATUS.json's rewrite was about
-- staying out of it applies here too, not just to health reporting.

Runs natively on the host with the host paths from SERVICES/.env directly (delete just
removes files under WIKI_BASE_DIR; fact-check shells out to the already-host-native
DSI-Wiki-Nightly-FactCheck.py --topic, same env overrides its own systemd unit uses).

Install: crontab -e
    * * * * * /usr/bin/python3 /BIG/PROJECTS/DSI/DSI-WIKI/TOOLS/process_topic_ops.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = Path(os.environ.get("WIKI_RAW_DIR", "/BIG/DATA/WIKI/Wiki-RAW"))
OPS_DIR = RAW_DIR / "_ops"
INSTANCES_DIR = Path(os.environ.get("INSTANCES_DIR", str(_REPO_ROOT / "JSONS" / "instances")))
FACTCHECK_SCRIPT = _REPO_ROOT / "CODE" / "ingest" / "DSI-Wiki-Nightly-FactCheck.py"
HOST_BASE_DIR = Path(os.environ.get("WIKI_BASE_DIR", "/BIG/DATA/WIKI/Wiki-BASE"))

LAYERS = ('raw', 'documentation', 'llm', 'minified', 'brief', 'changelog', 'devlog', 'silinmişler')


def _enabled_base_dirs() -> list[Path]:
    # instances/*.json's "base_dir" is /data/base (container-internal, 2026-08-06
    # bind-mount refactor) -- this script runs host-native (cron), so it needs the real
    # host path (WIKI_BASE_DIR), not that field. Only correct as long as every enabled
    # instance shares the one base_dir docker-compose.yml actually mounts -- same caveat
    # as DSI-Wiki-Nightly-FactCheck.py's identical fix.
    dirs = []
    for f in sorted(INSTANCES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("enabled") and data.get("base_dir"):
            dirs.append(HOST_BASE_DIR)
    return dirs


def _delete_topic(topic: str) -> str:
    removed = []
    for base_dir in _enabled_base_dirs():
        for layer in LAYERS:
            p = base_dir / layer / f"{topic}.md"
            if p.exists():
                p.unlink()
                removed.append(str(p))
    return f"deleted {len(removed)} layer file(s)" if removed else "nothing found"


def _factcheck_topic(topic: str) -> str:
    env = dict(os.environ)
    env["LLM_WIKI_OLLAMA_URL"] = "http://127.0.0.1:11434/api/chat"
    env.setdefault("NIGHTLY_FACTCHECK_SAFE_ROOT", "/BIG")
    env.setdefault("WIKI_BASE_DIR", os.environ.get("WIKI_BASE_DIR", "/BIG/DATA/WIKI/Wiki-BASE"))
    env.setdefault("INSTANCES_DIR", str(INSTANCES_DIR))
    result = subprocess.run(
        [sys.executable, str(FACTCHECK_SCRIPT), "--topic", topic],
        capture_output=True, text=True, timeout=900, env=env,
    )
    if result.returncode != 0:
        return f"exited {result.returncode}: {(result.stderr or '')[:300]}"
    return "done"


def main() -> int:
    if not OPS_DIR.is_dir():
        return 0
    for op_path in sorted(OPS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime):
        try:
            req = json.loads(op_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"bad ops request {op_path.name}: {e}", file=sys.stderr)
            op_path.unlink(missing_ok=True)
            continue
        op, topic = req.get("op"), req.get("topic")
        try:
            if op == "delete" and topic:
                print(f"{op_path.name}: delete {topic} -> {_delete_topic(topic)}")
            elif op == "factcheck" and topic:
                print(f"{op_path.name}: factcheck {topic} -> {_factcheck_topic(topic)}")
            else:
                print(f"{op_path.name}: unrecognized request {req}", file=sys.stderr)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"{op_path.name}: failed: {e}", file=sys.stderr)
        finally:
            op_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
