#!/usr/bin/env python3
"""DSI-wiki-stat -- prints DSI-BEHOLDER's status snapshot (JSONS/watchlist.json targets, each
with its own services[]: self-reported process rows + container-level docker rows).

Deliberately NOT an HTTP call, NOT a new API: DATA/watchlist_status.json is a plain file
DSI-BEHOLDER's watchdog already writes once per --interval (see that repo's watchdog.py /
config.get_status_snapshot_path()) -- this just reads it. No network round-trip, no new
surface to spam, no server involved at all.
"""
import json
import os
import sys
from datetime import datetime, timezone

SNAPSHOT_PATH = os.environ.get(
    "BEHOLDER_STATUS_SNAPSHOT",
    "/BIG/PROJECTS/DSI/DSI-BEHOLDER/DATA/watchlist_status.json",
)

_ICON = {"ok": "\033[32m●\033[0m", "warning": "\033[33m●\033[0m", "error": "\033[31m●\033[0m"}


def _age(iso):
    if not iso:
        return "n/a"
    secs = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    if secs < 60:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs / 60)}m ago"
    return f"{int(secs / 3600)}h ago"


def main() -> int:
    if not os.path.isfile(SNAPSHOT_PATH):
        print(f"no snapshot yet at {SNAPSHOT_PATH} -- has DSI-BEHOLDER's watchdog run at least once?", file=sys.stderr)
        return 1
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print(f"DSI-BEHOLDER snapshot, checked {_age(data.get('checked_at'))}\n")
    for t in data.get("targets", []):
        dot = _ICON.get(t.get("status"), "\033[90m●\033[0m")
        print(f"{dot} {t['name']} ({t.get('type', '?')}) -- {t.get('detail', '')}")
        for svc in ((t.get("info") or {}).get("services") or []):
            sdot = _ICON.get(svc.get("status"), "\033[90m●\033[0m")
            extra = svc.get("detail", "")
            print(f"    {sdot} {svc['name']}" + (f"  [{extra}]" if extra else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
