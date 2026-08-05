#!/usr/bin/env python3
"""
wiki_morning_refresh — one-shot 10:00 job (scheduled via crontab).

Sequence (each step gates the next):
  1. Free the GPU: whatever holds VRAM at 10:00 (the SDXL training if it is still
     running or has hung/crashed, plus any stuck Bonsai/hermes) is terminated and
     the Ollama model is unloaded, until VRAM is confirmed low.
  2. Back up the wiki data dir (/home/user/CLEANUP/DATA) to a timestamped tarball.
  3. ONLY if the backup succeeded: create per-topic dispatcher tasks for every
     wiki topic (all MAIN_ and SUB_ pages) — each task runs fact_scan then
     fact_check. The freed GPU lets Bonsai do the fact-check pass.

Self-removes its crontab line at the end so it runs exactly once.
Logs to /home/user/CLEANUP/DATA/_morning_refresh.log
"""
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/READY/DSI-Database"))

DATA_DIR = Path(os.environ.get("WIKI_DATA_DIR", "/home/user/CLEANUP/DATA"))
DOC_DIR = DATA_DIR / "Wiki-BASE" / "documentation"
BACKUP_DIR = Path("/home/user/backups")
LOG_FILE = DATA_DIR / "_morning_refresh.log"
OLLAMA_MODEL = "hf.co/prism-ml/Bonsai-27B-gguf:Q1_0"
TRAIN_MATCH = "sdxl_train_network.py"
VRAM_FREE_MIB = 800          # consider the GPU free below this
VRAM_WAIT_TIMEOUT = 180      # seconds to wait for VRAM to drain
SKIP_TOPICS = {"INDEP_LLM_RULES"}
PROJECT = "DSI-Wiki-FactCheck"


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------
# 1. Free the GPU
# --------------------------------------------------------------------------
def _vram_used_mib() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip().splitlines()
        return int(out[0]) if out else 0
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0


def _pkill(pattern: str, sig: str) -> int:
    # bracket trick so this process/command never matches itself
    bracketed = f"[{pattern[0]}]{pattern[1:]}"
    r = subprocess.run(["pgrep", "-f", bracketed], capture_output=True, text=True)
    pids = [p for p in r.stdout.split() if p]
    for p in pids:
        subprocess.run(["kill", sig, p], capture_output=True)
    return len(pids)


def free_gpu() -> None:
    log("STEP 1: freeing GPU")
    log(f"  VRAM before: {_vram_used_mib()} MiB")
    # SDXL training (still running or hung) — the user authorised freeing it at 10:00
    n = _pkill(TRAIN_MATCH, "-TERM")
    log(f"  SIGTERM to {n} training proc(s)")
    # stuck bonsai/hermes wiki workers
    _pkill("venv/bin/hermes", "-TERM")
    # unload the Ollama model
    subprocess.run(["ollama", "stop", OLLAMA_MODEL], capture_output=True, timeout=30)
    time.sleep(5)
    # escalate to KILL on anything still holding on
    if _vram_used_mib() > VRAM_FREE_MIB:
        _pkill(TRAIN_MATCH, "-KILL")
        _pkill("venv/bin/hermes", "-KILL")
        subprocess.run(["ollama", "stop", OLLAMA_MODEL], capture_output=True, timeout=30)

    deadline = time.time() + VRAM_WAIT_TIMEOUT
    while time.time() < deadline:
        used = _vram_used_mib()
        if used <= VRAM_FREE_MIB:
            log(f"  VRAM free: {used} MiB")
            return
        time.sleep(5)
    log(f"  WARNING: VRAM still {_vram_used_mib()} MiB after {VRAM_WAIT_TIMEOUT}s")


# --------------------------------------------------------------------------
# 2. Back up the wiki data dir
# --------------------------------------------------------------------------
def backup_wiki() -> bool:
    log("STEP 2: backing up wiki DATA")
    if not DATA_DIR.is_dir():
        log(f"  ERROR: {DATA_DIR} missing — aborting")
        return False
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"wiki-DATA-{ts}.tar.gz"
    r = subprocess.run(
        ["tar", "czf", str(dest), "-C", str(DATA_DIR.parent), DATA_DIR.name],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        log(f"  ERROR: backup failed rc={r.returncode} {r.stderr[:200]}")
        return False
    log(f"  backup OK: {dest} ({dest.stat().st_size // (1024*1024)} MiB)")
    return True


# --------------------------------------------------------------------------
# 3. Create per-topic fact_scan -> fact_check tasks
# --------------------------------------------------------------------------
def _topics() -> list[str]:
    if not DOC_DIR.is_dir():
        return []
    return sorted(p.stem for p in DOC_DIR.glob("*.md") if p.stem not in SKIP_TOPICS)


def _workflow(topic: str) -> dict:
    scan_cmd = (
        f"Fact-scan of DSI-Wiki topic '{topic}': gather current ground truth about "
        f"this topic from the live system (its source files, running services, ports, "
        f"configs) read-only, and write a concise findings note. Do not modify the wiki."
    )
    check_cmd = (
        f"Fact-check of DSI-Wiki topic '{topic}': compare its documentation layer "
        f"against the live system state from the fact-scan. Strike through (~~...~~) and "
        f"correct every false or outdated claim, following the DSI-Wiki nightly "
        f"fact-check convention. Read-only except the corrections to this topic's page."
    )
    return {
        "workflow_name": "wiki-fact-scan-check",
        "start_node": "fact_scan",
        "nodes": [
            {"id": "fact_scan", "profile": "Worker", "command": scan_cmd,
             "on_success": "fact_check", "on_fail": "error_identify",
             "on_provider_error": "error_identify", "on_refactor": "error_identify"},
            {"id": "fact_check", "profile": "Worker", "command": check_cmd,
             "on_success": "complete", "on_fail": "error_identify",
             "on_provider_error": "error_identify", "on_refactor": "error_identify"},
        ],
    }


def create_tasks() -> None:
    import json
    from databases.dispatcher.db import DSIDatabase
    log("STEP 3: creating per-topic fact-scan/check tasks")
    topics = _topics()
    if not topics:
        log(f"  ERROR: no topics found under {DOC_DIR}")
        return
    mains = [t for t in topics if t.startswith("MAIN_")]
    subs = [t for t in topics if t.startswith("SUB_")]
    log(f"  {len(topics)} topics ({len(mains)} MAIN, {len(subs)} SUB)")
    db = DSIDatabase()
    made = 0
    for topic in topics:
        wf = _workflow(topic)
        body = f"Fact scan + check for wiki topic {topic}.\n\n---WORKFLOW---\n" \
               + json.dumps(wf, indent=2, ensure_ascii=False)
        tid = f"t_{uuid.uuid4().hex[:8]}"
        db.insert_task(task_id=tid, title=f"Fact scan+check: {topic}", body=body,
                       project=PROJECT, tags=["wiki", "factcheck", topic],
                       status="ready", priority=3)
        made += 1
    log(f"  created {made} tasks in project {PROJECT}")


def remove_own_cron() -> None:
    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        kept = [ln for ln in cur.splitlines() if "wiki_morning_refresh" not in ln]
        subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True)
        log("  removed own crontab entry (one-shot done)")
    except (OSError, subprocess.SubprocessError):
        pass


def main() -> int:
    log("=== wiki_morning_refresh start ===")
    free_gpu()
    if not backup_wiki():
        log("ABORT: no backup → NOT creating fact-check tasks (they edit the wiki)")
        remove_own_cron()
        return 1
    create_tasks()
    remove_own_cron()
    log("=== wiki_morning_refresh done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
