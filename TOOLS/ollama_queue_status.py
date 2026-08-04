#!/usr/bin/env python3
"""DSI-ollama-queue-status — show what's currently queued/running on the shared
local-GPU Ollama lock (see CODE/common/ollama_lock.py)."""
import sys
from pathlib import Path

_scripts_root = str(Path(__file__).resolve().parent.parent / "CODE")
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from common.ollama_lock import queue_status


def main():
    state = queue_status()
    if not state:
        print("queue empty")
        return
    for job_id, entry in sorted(state.items(), key=lambda kv: kv[1].get("since", "")):
        print(f"{entry.get('status', '?'):8} {entry.get('label', ''):24} "
              f"pid={entry.get('pid')} since={entry.get('since')} job={job_id}")


if __name__ == "__main__":
    main()
