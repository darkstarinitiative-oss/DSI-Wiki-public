"""Nightly fact-check: a small tool-calling local model verifies every wiki topic's
documentation layer against live system state. Any false claim found is deleted from
the document outright and archived (with its correction) into that topic's
'silinmişler' (deleted) sub-topic file — no more inline ~~strikethrough~~ (2026-07-30).

Runs unattended at 03:00 via systemd timer. Bonsai gets a small, read-only, whitelisted toolset
(no shell=True, no writes, no path escape outside /home/ozan) so it can check its own facts
instead of the orchestrator gathering ground truth by hand every time.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import urllib.request

_scripts_root = str(Path(__file__).parent.parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from common.ollama_lock import call_ollama as _locked_call_ollama

# Switched from Bonsai-27B-gguf:Q1_0 to qwen3:1.7b 2026-07-30: on the 8GB GTX 1070,
# the 27B model (even Q1 quantized) was too slow for CPU-offloaded generation — the
# nightly run degraded from ~39 topics/night to ~7 before hitting its 1h job timeout,
# with many individual topic checks themselves timing out. A small model leaves
# headroom for context and finishes each check fast enough to get through all topics.
MODEL = "qwen3:1.7b"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INSTANCES_DIR = Path(os.environ.get("INSTANCES_DIR", str(REPO_ROOT / "JSONS" / "instances")))
WIKI_BASE_DIR = os.environ.get("WIKI_BASE_DIR", "/home/ozan/CLEANUP/DATA/Wiki-BASE")
LOG_DIR = Path(WIKI_BASE_DIR) / "_nightly_factcheck_logs"
SAFE_ROOT = Path("/home/ozan").resolve()
MAX_TOOL_TURNS = 8
SKIP_TOPICS = {"INDEP_LLM_RULES"}


# ---------------------------------------------------------------------------
# Restricted, read-only toolset. Every function validates its own input and
# refuses to touch anything outside SAFE_ROOT or run anything destructive.
# ---------------------------------------------------------------------------

def _safe_path(p: str) -> Path | None:
    try:
        resolved = Path(os.path.expanduser(p)).resolve()
    except Exception:
        return None
    if SAFE_ROOT not in resolved.parents and resolved != SAFE_ROOT:
        return None
    return resolved


def tool_check_path_exists(path: str) -> str:
    p = _safe_path(path)
    if p is None:
        return "ERROR: path outside allowed root"
    return json.dumps({"path": str(p), "exists": p.exists()})


def tool_list_directory(path: str) -> str:
    p = _safe_path(path)
    if p is None:
        return "ERROR: path outside allowed root"
    if not p.is_dir():
        return json.dumps({"error": "not a directory or does not exist"})
    try:
        entries = sorted(os.listdir(p))[:200]
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"path": str(p), "entries": entries})


def tool_read_file_snippet(path: str, max_chars: int = 2000) -> str:
    p = _safe_path(path)
    if p is None:
        return "ERROR: path outside allowed root"
    if not p.is_file():
        return json.dumps({"error": "not a file or does not exist"})
    try:
        text = p.read_text(encoding="utf-8", errors="replace")[: min(int(max_chars), 4000)]
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"path": str(p), "content": text})


_UNIT_RE = re.compile(r"^[a-zA-Z0-9_.@-]+\.(service|target|timer)$")


def tool_check_systemd_status(unit: str) -> str:
    if not _UNIT_RE.match(unit):
        return "ERROR: invalid unit name"
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True, text=True, timeout=10,
        )
        return json.dumps({"unit": unit, "status": r.stdout.strip() or r.stderr.strip()})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_check_git_status(repo_path: str) -> str:
    p = _safe_path(repo_path)
    if p is None or not (p / ".git").exists():
        return "ERROR: not an allowed git repo path"
    try:
        status = subprocess.run(
            ["git", "-C", str(p), "status", "--short"], capture_output=True, text=True, timeout=15
        ).stdout
        branch = subprocess.run(
            ["git", "-C", str(p), "branch", "--show-current"], capture_output=True, text=True, timeout=15
        ).stdout.strip()
        remote_branches = subprocess.run(
            ["git", "-C", str(p), "ls-remote", "--heads", "origin"], capture_output=True, text=True, timeout=20
        ).stdout
        return json.dumps({
            "repo": str(p), "branch": branch,
            "dirty_files": status.strip().splitlines(),
            "remote_branches": [l.split("refs/heads/")[-1] for l in remote_branches.strip().splitlines()],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


_PORT_RE = re.compile(r"^\d{1,5}$")


def tool_check_listening_port(port: str) -> str:
    if not _PORT_RE.match(str(port)):
        return "ERROR: invalid port"
    try:
        out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=10).stdout
        listening = any(f":{port} " in line or line.rstrip().endswith(f":{port}") for line in out.splitlines())
        return json.dumps({"port": port, "listening": listening})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_http_get_status(url: str) -> str:
    if not re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?(/.*)?$", url):
        return "ERROR: only http(s)://127.0.0.1 or localhost URLs allowed"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.dumps({"url": url, "status": resp.status})
    except Exception as e:
        return json.dumps({"url": url, "error": str(e)})


TOOLS = {
    "check_path_exists": (
        tool_check_path_exists, "Check whether a filesystem path exists.",
        {"path": {"type": "string", "description": "Absolute or ~-prefixed path to check"}}, ["path"],
    ),
    "list_directory": (
        tool_list_directory, "List entries in a directory.",
        {"path": {"type": "string", "description": "Absolute or ~-prefixed directory path"}}, ["path"],
    ),
    "read_file_snippet": (
        tool_read_file_snippet, "Read up to max_chars of a text file.",
        {
            "path": {"type": "string", "description": "Absolute or ~-prefixed file path"},
            "max_chars": {"type": "integer", "description": "Max characters to return (default 2000)"},
        }, ["path"],
    ),
    "check_systemd_status": (
        tool_check_systemd_status, "Check `systemctl --user is-active` for a unit.",
        {"unit": {"type": "string", "description": "Unit name, must end in .service/.target/.timer"}}, ["unit"],
    ),
    "check_git_status": (
        tool_check_git_status, "Get git status/branch/remote-branches for a repo.",
        {"repo_path": {"type": "string", "description": "Absolute path to a git repo root"}}, ["repo_path"],
    ),
    "check_listening_port": (
        tool_check_listening_port, "Check if a TCP port is listening (ss -ltn).",
        {"port": {"type": "string", "description": "Port number as a string, e.g. \"8430\""}}, ["port"],
    ),
    "http_get_status": (
        tool_http_get_status, "GET a localhost URL and return HTTP status.",
        {"url": {"type": "string", "description": "Full URL, must be http(s)://127.0.0.1 or localhost"}}, ["url"],
    ),
}

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req},
        },
    }
    for name, (_, desc, props, req) in TOOLS.items()
]


def call_ollama(messages, tools=None):
    return _locked_call_ollama(MODEL, messages, tools=tools, think=False, timeout=180,
                                label="wiki-nightly-factcheck")


SYSTEM_PROMPT = """You are fact-checking one page of technical documentation against the live system, \
using the provided tools (all read-only, restricted to paths under /home/ozan). Known base paths, so \
you don't have to guess or explore blindly: DSI-Wiki repo root = {repo_root}, wiki data \
root = {wiki_base_dir}. Relative paths mentioned in the doc (e.g. `CODE/foo.py`) are \
almost always relative to the DSI-Wiki repo root above — try that first before exploring elsewhere.

Read the documentation below. Identify at most 5 of the most important concrete, checkable claims \
(file/dir existence, systemd service status, git branch/dirty state, listening ports, localhost HTTP \
endpoints). Use tools to verify each one — prefer 1-2 targeted tool calls per claim, do not explore \
unrelated directories. Do NOT verify vague/non-checkable claims (opinions, design rationale, "not \
covered in raw source" notes). You have at most {max_turns} tool calls total for this whole page — \
budget them, stop checking and answer once you've used most of them or covered the important claims.

When you are done checking, reply with ONLY plain text in this exact format (no other text before or \
after), one block per false claim found (omit entirely if nothing is false):

OLD: <the exact, verbatim sentence or clause from the documentation that is now false>
NEW: <one corrected sentence stating the real current fact, dated {date}>
---
(repeat OLD/NEW/--- for each false claim)

If everything checks out, reply with exactly: NO_CHANGES
"""

FORCE_ANSWER_PROMPT = ("You have used your tool-call budget. Based on what you've verified so far, "
                       "answer NOW in the required OLD:/NEW:/--- format, or NO_CHANGES if nothing "
                       "confirmed false yet. Do not call any more tools.")


def factcheck_topic(topic: str, doc_text: str) -> list[tuple[str, str]]:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(
            date=date, max_turns=MAX_TOOL_TURNS, repo_root=REPO_ROOT, wiki_base_dir=WIKI_BASE_DIR)},
        {"role": "user", "content": f"# {topic}\n\n{doc_text}"},
    ]
    for turn in range(MAX_TOOL_TURNS):
        resp = call_ollama(messages, tools=TOOL_SCHEMA)
        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            content = msg.get("content", "").strip()
            return parse_fix_blocks(content)
        messages.append(msg)
        for call in tool_calls:
            fn_name = call.get("function", {}).get("name")
            fn_args = call.get("function", {}).get("arguments", {}) or {}
            fn = TOOLS.get(fn_name)
            if fn is None:
                result = f"ERROR: unknown tool {fn_name}"
            else:
                try:
                    result = fn[0](**fn_args)
                except TypeError as e:
                    result = f"ERROR: bad arguments ({e})"
            messages.append({"role": "tool", "content": str(result)})
    messages.append({"role": "user", "content": FORCE_ANSWER_PROMPT.format(date=date)})
    resp = call_ollama(messages)
    msg = resp.get("message", {})
    content = msg.get("content", "").strip()
    return parse_fix_blocks(content)


def parse_fix_blocks(text: str) -> list[tuple[str, str]]:
    if text.strip() == "NO_CHANGES" or not text.strip():
        return []
    fixes = []
    for block in text.split("---"):
        old_m = re.search(r"OLD:\s*(.+?)(?:\nNEW:|$)", block, re.DOTALL)
        new_m = re.search(r"NEW:\s*(.+)", block, re.DOTALL)
        if old_m and new_m:
            fixes.append((old_m.group(1).strip(), new_m.group(1).strip()))
    return fixes


def _deleted_topic_path(base_dir: Path, topic: str) -> Path:
    """The 'silinmişler' (deleted) sub-topic file for one wiki topic — a sibling
    layer dir of documentation/llm/minified/etc, appended to (never overwritten)
    each time the nightly fact-check removes a false claim. Replaces the old
    inline ~~strikethrough~~+correction pattern (2026-07-30, per user directive:
    invalid data gets deleted outright, not left inline)."""
    d = base_dir / "silinmişler"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{topic}.md"


def apply_fixes(doc_path: Path, fixes: list[tuple[str, str]], base_dir: Path, topic: str) -> int:
    if not fixes:
        return 0
    text = doc_path.read_text(encoding="utf-8")
    applied = 0
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_entries = []
    for old, new in fixes:
        if old in text:
            text = text.replace(old, "", 1)
            archive_entries.append(
                f"## {date} — nightly fact-check\n**Silinen:** {old}\n**Güncel gerçek:** {new}\n"
            )
            applied += 1
    if applied:
        doc_path.write_text(text, encoding="utf-8")
        archive_path = _deleted_topic_path(base_dir, topic)
        with archive_path.open("a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(archive_entries))
    return applied


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Local time, not UTC: the healthcheck script matches today's log by local
    # calendar date (date.today()), and this timer fires in the local early
    # morning (UTC+3) — a UTC timestamp here would land on the previous UTC
    # day and the healthcheck would never find the file.
    run_id = datetime.now().astimezone().strftime("%Y-%m-%d_%H%M")
    log_path = LOG_DIR / f"{run_id}.log"

    # Written incrementally (one flush per topic) rather than assembled in
    # memory and written once at the end: a TimeoutStartSec kill or crash
    # partway through must still leave today's log file behind, since fixes
    # are already being applied to docs as we go and the healthcheck only
    # cares whether a log for today exists.
    def log(line: str) -> None:
        print(line)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    log(f"Nightly fact-check run {run_id}")

    for instance_file in sorted(INSTANCES_DIR.glob("*.json")):
        instance = json.loads(instance_file.read_text())
        if not instance.get("enabled"):
            continue
        base_dir = Path(instance["base_dir"])
        doc_dir = base_dir / "documentation"
        if not doc_dir.is_dir():
            continue
        for doc_path in sorted(doc_dir.glob("*.md")):
            topic = doc_path.stem
            if topic in SKIP_TOPICS or topic.startswith("OBSOLETE_"):
                continue
            doc_text = doc_path.read_text(encoding="utf-8")
            try:
                fixes = factcheck_topic(topic, doc_text)
            except Exception as e:
                log(f"{instance['name']}/{topic}: ERROR {e}")
                continue
            applied = apply_fixes(doc_path, fixes, base_dir, topic)
            log(f"{instance['name']}/{topic}: {len(fixes)} found, {applied} applied")


if __name__ == "__main__":
    main()
