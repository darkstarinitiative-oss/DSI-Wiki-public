#!/usr/bin/env python3
"""Writes STATUS.json for the DSI-Wiki Ingest Daemon -- run externally (host cron, every
minute), never from inside the ingest process itself: a process that hangs or dies can't
report its own hang/death, so health here is judged from OUTSIDE (docker inspect), not
self-reported. Content (feed/last_ingest) still comes from the daemon's own event log
(DATA/events/ingest_events.json, written once per completed ingest -- see
CODE/ingest/DSI-Wiki-Ingest-Service-Class.py's _write_events()), since that data can only
come from the daemon that did the work; only the up/down verdict is external.

Install: crontab -e
    * * * * * /usr/bin/python3 /BIG/PROJECTS/DSI/DSI-WIKI/TOOLS/write_ingest_status.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
CONTAINER = os.environ.get("WIKI_INGEST_CONTAINER", "DSI-WIKI.docker.ingest")
STATUS_PATH = Path(os.environ.get("WIKI_STATUS_DIR", str(_REPO_ROOT / "DATA" / "status"))) / "STATUS.json"
EVENTS_PATH = Path(os.environ.get("WIKI_INGEST_EVENTS_DIR", str(_REPO_ROOT / "DATA" / "events"))) / "ingest_events.json"
SERVICE_VERSION = "0.1a"


def _container_state() -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", CONTAINER],
            capture_output=True, text=True, timeout=5.0,
        )
    except (subprocess.SubprocessError, OSError) as e:
        return "error", str(e)
    if result.returncode != 0:
        return "error", "container not found"
    state = result.stdout.strip()
    return ("ok" if state == "running" else "error"), state


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(_REPO_ROOT),
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _read_events() -> dict:
    if not EVENTS_PATH.is_file():
        return {"last_ingest": None, "feed": []}
    try:
        with open(EVENTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"last_ingest": None, "feed": []}


def main() -> int:
    status, detail = _container_state()
    events = _read_events()
    now = datetime.now(timezone.utc).isoformat()

    status_note = "nominal" if status == "ok" else f"container {CONTAINER}: {detail}"
    doc = {
        "service": "dsi-wiki-ingest",
        "version": SERVICE_VERSION,
        "status": status,
        "status_note": status_note,
        "services": [
            {"name": "DSI-Wiki Ingest Daemon", "status": status, "last_heartbeat": now},
        ],
        "feed": events.get("feed", []),
        "last_ingest": events.get("last_ingest"),
        "git_commit": _git_commit(),
        "checked_at": now,
        "checked_by": "TOOLS/write_ingest_status.py (host cron)",
    }

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATUS_PATH)  # atomic
    return 0


if __name__ == "__main__":
    sys.exit(main())
