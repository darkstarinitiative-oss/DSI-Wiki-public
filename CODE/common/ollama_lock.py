"""Cross-process VRAM queue for local Ollama calls.

The GPU (GTX 1070, 8GB VRAM) cannot hold multiple models generating at once without
contention/CPU-offload slowdown. Root-caused 2026-07-29/30: the nightly fact-check
degraded from ~39 topics/night to ~7 before hitting its 1h job timeout, with many
individual per-topic Ollama calls themselves timing out — no subsystem serialized
against any other. This closes a previously scoped-but-never-shipped gap (Dispatcher++
task t_11bf78f3, 2026-07-21 devlog: "explicitly deferred beyond this task: a distinct
queued/queued_vram state" — the task record itself was later lost in a DB migration
and the state was never actually built).

Design: a caller does NOT poll for its turn (that was source_registry.py's
acquire()-returns-False-retry shape, rejected here as the wrong primitive). It
registers itself as "queued" in a small JSON ledger, then blocks on `flock()` — the
kernel puts the process to sleep and wakes it the moment the lock is free, with zero
busy-waiting. Only once woken does it flip its own ledger entry to "running". The
ledger is purely for observability (`queue_status()` — what's queued/running right
now); the actual queueing/notification is the kernel's flock wait queue.
"""
import fcntl
import json
import os
import signal
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_lock_dir_env = os.environ.get("WIKI_LOCK_DIR")
if not _lock_dir_env:
    raise RuntimeError(
        "WIKI_LOCK_DIR is not set — source SERVICES/.env first (`set -a; source "
        "SERVICES/.env; set +a`) before running this host-side. No fallback path: an "
        "unset var is a hard error, not a silent guess (see README.md § Running "
        "host-side tools)."
    )
_LOCK_DIR = Path(_lock_dir_env)
LOCK_PATH = _LOCK_DIR / ".ollama_gpu.lock"
STATE_PATH = _LOCK_DIR / ".ollama_gpu_queue.json"
STATE_LOCK_PATH = _LOCK_DIR / ".ollama_gpu_queue.state.lock"
OLLAMA_URL = os.environ.get("LLM_WIKI_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
# Optional: set to point call_ollama() at any Ollama/OpenAI-wire-compatible endpoint that
# needs bearer auth -- Ollama Cloud, a self-hosted router in front of multiple backends, etc.
# Empty (default) = no Authorization header, i.e. today's plain local-Ollama behavior, unchanged.
OLLAMA_API_KEY = os.environ.get("LLM_WIKI_OLLAMA_API_KEY", "")

# Max time one caller may hold the VRAM lock once it's running, before it's forcibly
# evicted (2026-07-30): a stuck/slow holder at the head of the queue would otherwise
# block every other queued caller indefinitely — flock() itself has no timeout, so
# this is enforced with SIGALRM around the "running" phase only (never during the
# queued wait).
STALE_RUNNING_SECONDS = 15 * 60


class GPULockTimeout(Exception):
    """Raised in the lock holder when it exceeds STALE_RUNNING_SECONDS — the lock is
    released (via gpu_lock's finally) so the next queued caller can proceed."""


def _alarm_handler(signum, frame):
    raise GPULockTimeout(f"held the VRAM lock longer than {STALE_RUNNING_SECONDS}s — evicted")


@contextmanager
def _state_lock():
    STATE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_LOCK_PATH, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _read_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _set_job(job_id: str, status: str | None, label: str) -> None:
    with _state_lock():
        state = _read_state()
        if status is None:
            state.pop(job_id, None)
        else:
            state[job_id] = {
                "status": status, "label": label, "pid": os.getpid(),
                "since": datetime.now(timezone.utc).isoformat(),
            }
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def queue_status() -> dict:
    """Everything currently queued or running, for monitoring/dashboards."""
    with _state_lock():
        return _read_state()


@contextmanager
def gpu_lock(label: str = ""):
    """Enter the VRAM queue: registers as "queued", blocks on the kernel wait queue
    (no polling) until it's this call's turn, flips to "running", yields, then
    releases and deregisters. Safe across separate processes."""
    job_id = f"{os.getpid()}-{uuid.uuid4().hex[:6]}"
    _set_job(job_id, "queued", label)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOCK_PATH, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)  # sleeps here; kernel wakes us on our turn
            _set_job(job_id, "running", label)
            previous_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.alarm(STALE_RUNNING_SECONDS)
            try:
                yield
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous_handler)
                fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        _set_job(job_id, None, label)


def call_ollama(model: str, messages: list, tools: list | None = None,
                 think: bool = False, timeout: int = 120,
                 options: dict | None = None, url: str = OLLAMA_URL,
                 api_key: str = OLLAMA_API_KEY, label: str = "") -> dict:
    """Queued POST to an Ollama-wire-compatible /api/chat endpoint. Returns the parsed JSON
    response body. `url`/`api_key` default to LLM_WIKI_OLLAMA_URL/LLM_WIKI_OLLAMA_API_KEY, so
    swapping backends (Ollama Cloud, a self-hosted router, anything else speaking this same
    wire format) is a config change, not a code change -- see DOCS/llm-backend-roadmap.md.
    """
    import urllib.request

    payload = {"model": model, "messages": messages, "think": think, "stream": False}
    if tools:
        payload["tools"] = tools
    if options:
        payload["options"] = options
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST",
    )
    with gpu_lock(label=label or model):
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
