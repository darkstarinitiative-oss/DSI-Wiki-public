#!/usr/bin/env python3
"""
DSI-Wiki-Ingest-Service-Class.py — LLM-Wiki raw/ polling daemon
Uses Qwen3-8B via Ollama's /api/chat for ingest (2026-07-20 DSI-Agent-Profiles
Model-Priority decision: worker/ingest tier = Qwen3-8B, thinking=false).
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_scripts_root = str(Path(__file__).parent.parent)
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)

from common.ollama_lock import gpu_lock

SERVICE_VERSION = "0.1a"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATUS_PATH = Path(os.environ.get("WIKI_STATUS_PATH", str(_REPO_ROOT / "STATUS.json")))


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(_REPO_ROOT),
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# Updated by process_file() right when a run finishes (success or failure) --
# read by write_status() so the health widget (CODE/ui/DSI-Wiki-UI-Server.py)
# can show "last ingest" without waiting for the next poll-cycle snapshot.
_last_ingest = {"topic": None, "finished_at": None, "duration_seconds": None, "ok": None}

# DSI Info API Standard (DOCS/info-api-standard.md): last _FEED_MAX events, newest
# first. What counts as feed-worthy is this project's own call, per the standard --
# here that's every ingest outcome, one entry each.
_FEED_MAX = 10
_feed: list = []


def _push_feed(icon: str, title: str, note: str = ""):
    _feed.insert(0, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "icon": icon,
        "title": title,
        "note": note,
    })
    del _feed[_FEED_MAX:]


def write_status(instances_loaded: int):
    # DSI Info API Standard fields (service/version/status/status_note/services/feed)
    # alongside the pre-existing ones (kept for anything already reading them).
    ok = _last_ingest.get("ok")
    if ok is False:
        info_status, info_note = "warning", f"last ingest ({_last_ingest.get('topic')}) failed — see feed"
    else:
        info_status, info_note = "ok", "nominal"

    status = {
        "service": "dsi-wiki-ingest",
        "version": SERVICE_VERSION,
        "status": info_status,
        "status_note": info_note,
        "services": [
            {
                "name": "DSI-Wiki Ingest Daemon",
                "status": info_status,
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            },
        ],
        "feed": _feed,
        # Pre-existing fields, kept for backward compatibility with anything already
        # reading /api/status.
        "last_poll_ts": datetime.now(timezone.utc).isoformat(),
        "instances_loaded": instances_loaded,
        "ollama_model": OLLAMA_MODEL,
        "service_version": SERVICE_VERSION,
        "git_commit": _git_commit(),
        "last_ingest": _last_ingest,
    }
    try:
        STATUS_PATH.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass

# SIGUSR1 ile bekleme (time.sleep) anında kesilip kuyruk hemen işlenir.
# Otomatik/klasör-tetikli değil — sadece elle (kill -USR1) çağrıldığında devreye girer.
_wake_event = threading.Event()


def _handle_wake_signal(signum, frame):
    log(">> SIGUSR1 alindi, bekleme kesiliyor, kuyruk hemen kontrol edilecek.")
    _wake_event.set()

RAW_DIR = Path(os.environ.get("LLM_WIKI_RAW_DIR", "/home/ozan/LLM-Wiki/raw"))
ARCHIVE_DIR = Path(os.environ.get("LLM_WIKI_ARCHIVE_DIR", "/home/ozan/LLM-Wiki/raw_archive"))
POLL_INTERVAL = int(os.environ.get("LLM_WIKI_POLL_INTERVAL", "60"))
CLAUDE_TIMEOUT = int(os.environ.get("LLM_WIKI_CLAUDE_TIMEOUT", "600"))

# Çoklu instance yönlendirme — her route kendi base_dir + layers'ını taşır (bkz.
# JSONS/instances/*.json, DSI-Wiki-Service-Supervisor.py tarafından üretilir).
# Eşleşme yoksa default_base_dir / default_layers kullanılır.
ROUTES_PATH = Path(os.environ.get("LLM_WIKI_ROUTES", "/home/ozan/LLM-Wiki/ingest_routes.json"))
ROUTES_RELOAD_INTERVAL = 1800
_routes_cache = {"routes": [], "default_base_dir": None, "default_layers": None, "loaded_at": 0.0}

# Qwen3-8B (real: qwen3-worker) via local Ollama.
# thinking defaults to True: with think=false, qwen3:4b was observed narrating its
# reasoning as regular content instead of using Ollama's separate `message.thinking`
# field, so the delimiter parser below would grab a mid-monologue fragment instead of
# the real answer. With think=true, Ollama splits `message.thinking` (reasoning) from
# `message.content` (final answer) — only `content` is used below, so it comes back
# clean. Note: thinking is only actually toggled via /api/chat's top-level `think`
# field — /api/generate and prompt-level "/no_think" do NOT work on this model.
OLLAMA_URL = os.environ.get("LLM_WIKI_OLLAMA_URL", "http://localhost:11434/api/chat")
# Optional bearer auth for any Ollama/OpenAI-wire-compatible endpoint that needs it (Ollama
# Cloud, a self-hosted router in front of multiple backends -- see DOCS/llm-backend-roadmap.md).
# Empty (default) = no Authorization header, i.e. today's plain local-Ollama behavior, unchanged.
OLLAMA_API_KEY = os.environ.get("LLM_WIKI_OLLAMA_API_KEY", "")
# Downsized from qwen3-worker (qwen3:8b, 5.2GB) to qwen3:4b (2.5GB) 2026-07-30: on the
# 8GB GTX 1070, the 8B model was already spilling past VRAM into CPU offload on its
# own, before any other consumer even joined the queue (see common/ollama_lock.py).
OLLAMA_MODEL = os.environ.get("LLM_WIKI_OLLAMA_MODEL", "qwen3:4b")
OLLAMA_NUM_CTX = int(os.environ.get("LLM_WIKI_OLLAMA_NUM_CTX", "16384"))
OLLAMA_NUM_PREDICT = int(os.environ.get("LLM_WIKI_OLLAMA_NUM_PREDICT", "6000"))
OLLAMA_THINK = os.environ.get("LLM_WIKI_OLLAMA_THINK", "true").lower() == "true"


class _LLMResult:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_llm(prompt: str, timeout: int) -> _LLMResult:
    """Calls Qwen3-8B via Ollama's /api/chat. Mirrors the subprocess.CompletedProcess
    interface (.returncode/.stdout/.stderr) the call sites already expect."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": OLLAMA_THINK,
        "options": {"num_ctx": OLLAMA_NUM_CTX, "num_predict": OLLAMA_NUM_PREDICT},
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers=headers, method="POST")
    try:
        with gpu_lock(label="wiki-ingest"):
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
    except socket.timeout as e:
        raise TimeoutError(str(e)) from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"ollama not reachable at {OLLAMA_URL}: {e}") from e
    if "error" in body:
        return _LLMResult(1, "", str(body["error"]))
    content = body.get("message", {}).get("content", "")
    return _LLMResult(0, content, "")

# Tum katman talimatlari (documentation/llm/minified/changelog/devlog) ve yazma modu ("overwrite"/
# "append") sadece JSONS/instances/*.json -> layers.<layer>.prompt/mode alanindan gelir. Kodda hicbir
# sabit/varsayilan talimat metni tutulmaz — bir instance kendi layers'ini tanimlamazsa o katman
# hic uretilmez (bkz. get_layers()).


def load_routes(force: bool = False):
    now = time.time()
    if not force and (now - _routes_cache["loaded_at"]) < ROUTES_RELOAD_INTERVAL:
        return _routes_cache["routes"]
    try:
        data = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
        _routes_cache["routes"] = data.get("routes", [])
        _routes_cache["default_base_dir"] = data.get("default_base_dir")
        _routes_cache["default_layers"] = data.get("default_layers")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log(f"   !! {ROUTES_PATH.name} okunamadi ({e}), routing devre disi.")
        _routes_cache["routes"] = []
    _routes_cache["loaded_at"] = now
    return _routes_cache["routes"]


def get_base_dir(route) -> Path:
    if route and route.get("base_dir"):
        return Path(route["base_dir"])
    default = _routes_cache.get("default_base_dir")
    if not default:
        raise RuntimeError(f"default_base_dir yok ({ROUTES_PATH}) ve route eşleşmedi — yazılacak yer belirsiz.")
    return Path(default)


def get_layers(route) -> dict:
    if route and route.get("layers"):
        return route["layers"]
    return _routes_cache.get("default_layers") or {}


def match_route(topic: str):
    topic_lower = topic.lower()
    for route in load_routes():
        if route.get("keyword", "").lower() in topic_lower:
            return route
    return None


PROMPT_HEADER = """\
You are a technical documentation writer for the DSI (Dark Star Industries) AI system.

Given the raw source notes below, produce structured wiki output in the layers listed below.
Use the EXACT delimiter lines shown — they are parsed programmatically.

OUTPUT FORMAT (mandatory):
{layer_blocks}

RULES:
- English only
- Write only what is verifiable from the raw source — no hallucinations
- If a section has no supporting facts in the raw source, write "Not covered in raw source."
  — never invent specifics (function names, numbers, config values, endpoints) to fill it
{route_rules}
TOPIC: {topic}

RAW SOURCE:
{raw_content}
"""

ROUTE_RULES_TEMPLATE = """\
- This topic belongs to project route "{tag}". Add a line "Tags: {tag}" near the
  top of the DOCUMENTATION layer (and mention it in LLM layer too), so it stays
  searchable via wiki_search("{tag}").
"""

# MAIN_<name> / SUB_<name>_<sub> hiyerarsisi: llm+minified+brief katmanlari her zaman
# MAIN seviyesinde tek dosyada konsolide edilir, sub'lar kendi llm/minified/brief'ini
# uretmez (sadece documentation layer'i kendi dosyasina yazar). brief = orta-boy
# ajan ozeti: bir projeye sifirdan devam edecek ajan icin tek MAIN-seviyesi ozet.
CONSOLIDATED_LAYER_NAMES = ("llm", "minified", "brief")

CONSOLIDATE_PROMPT_HEADER = """\
You are a technical documentation writer for the DSI (Dark Star Industries) AI system.

Below are one or more DOCUMENTATION-layer wiki pages: the main topic page and/or its
sub-module pages. Produce a SINGLE consolidated output per layer listed below that
covers the main topic AND all its sub-modules together as one coherent whole —
do not produce one block per source page, and do not just concatenate them.

OUTPUT FORMAT (mandatory):
{layer_blocks}

RULES:
- English only
- Write only what is verifiable from the source pages below — no hallucinations
- If a layer has no supporting facts anywhere in the sources, write
  "Not covered in source documentation."
{route_rules}
TOPIC: {topic}

SOURCE DOCUMENTATION PAGES:
{raw_content}
"""


def parse_hierarchical_topic(topic: str) -> str | None:
    """MAIN_<name> or SUB_<name>_<sub> -> 'MAIN_<name>'; anything else -> None."""
    parts = topic.split("_")
    if parts[0] == "MAIN" and len(parts) == 2:
        return topic
    if parts[0] == "SUB" and len(parts) == 3:
        return f"MAIN_{parts[1]}"
    return None


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def build_layer_instructions(layer_name: str, layer_cfg: dict) -> str:
    return layer_cfg.get("prompt", "")


def build_prompt(topic: str, raw_content: str, layers_cfg: dict, route_rules: str) -> tuple[str, list[str]]:
    layer_names = ["documentation"] + [n for n in layers_cfg if n != "documentation"]
    blocks = []
    for name in layer_names:
        instr = build_layer_instructions(name, layers_cfg.get(name, {}))
        blocks.append(f"==={name.upper()}===\n<{instr}>")
    prompt = PROMPT_HEADER.format(
        layer_blocks="\n".join(blocks),
        route_rules=route_rules,
        topic=topic,
        raw_content=raw_content,
    )
    return prompt, layer_names


def parse_output(stdout: str, layer_names: list[str]) -> dict[str, str] | None:
    positions = []
    for name in layer_names:
        delim = f"==={name.upper()}==="
        idx = stdout.find(delim)
        if idx == -1:
            return None
        positions.append((idx, delim, name))
    positions.sort()
    result = {}
    for i, (idx, delim, name) in enumerate(positions):
        start = idx + len(delim)
        end = positions[i + 1][0] if i + 1 < len(positions) else len(stdout)
        result[name] = stdout[start:end].strip()
    return result


def write_layers(topic: str, contents: dict[str, str], layers_cfg: dict, base_dir: Path):
    for name, content in contents.items():
        cfg = layers_cfg.get(name, {})
        mode = cfg.get("mode", "overwrite")
        layer_dir = base_dir / name
        layer_dir.mkdir(parents=True, exist_ok=True)
        path = layer_dir / f"{topic}.md"
        if name == "minified":
            # Deterministic, not LLM-authored: the model was asked to append this
            # line itself and sometimes wrote "--layer minified" instead of "llm"
            # (self-referential slip). Appending it here guarantees it's always
            # correct and always present.
            content = f"{content}\nLLM:DSI-wiki-get {topic} --layer llm"
        if mode == "append":
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n## {ts}\n{content}\n")
        else:
            path.write_text(content, encoding="utf-8")

    log_path = base_dir / "documentation" / "log.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"- [{ts}] ingest: {topic}\n")


def archive_file(raw_path: Path):
    ARCHIVE_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    dest = ARCHIVE_DIR / f"{ts}_{raw_path.name}"
    shutil.move(str(raw_path), str(dest))
    log(f"   >> Archived: {dest.name}")


def regenerate_consolidated_layers(main_topic: str, base_dir: Path, layers_cfg: dict, route_rules: str):
    """Rebuilds llm/minified for `main_topic` from ALL known documentation pages
    (the main page itself + every SUB_<name>_* page found), overwriting the single
    MAIN-level llm/minified files. Called after any MAIN or SUB raw ingest."""
    layer_names = [n for n in CONSOLIDATED_LAYER_NAMES if n in layers_cfg]
    if not layer_names:
        return

    main_name = main_topic[len("MAIN_"):]
    doc_dir = base_dir / "documentation"
    sources = []
    main_doc = doc_dir / f"{main_topic}.md"
    if main_doc.exists():
        sources.append((main_topic, main_doc.read_text(encoding="utf-8")))
    for sub_doc in sorted(doc_dir.glob(f"SUB_{main_name}_*.md")):
        sources.append((sub_doc.stem, sub_doc.read_text(encoding="utf-8")))

    if not sources:
        log(f"   !! consolidate: no documentation found for {main_topic}, skipping.")
        return

    combined = "\n\n".join(f"=== SOURCE: {name} ===\n{text}" for name, text in sources)
    blocks = []
    for name in layer_names:
        instr = build_layer_instructions(name, layers_cfg.get(name, {}))
        blocks.append(f"==={name.upper()}===\n<{instr}>")
    prompt = CONSOLIDATE_PROMPT_HEADER.format(
        layer_blocks="\n".join(blocks),
        route_rules=route_rules,
        topic=main_topic,
        raw_content=combined,
    )

    log(f"   Consolidating {layer_names} for {main_topic} from {len(sources)} source page(s)"
        f" via bonsai ({OLLAMA_MODEL}, think={OLLAMA_THINK})...")
    try:
        result = run_llm(prompt, timeout=CLAUDE_TIMEOUT)
    except TimeoutError:
        log(f"   !! consolidate timed out after {CLAUDE_TIMEOUT}s — skipping.")
        return
    except ConnectionError as e:
        log(f"   !! consolidate: {e}")
        return

    if result.returncode != 0:
        log(f"   !! consolidate bonsai error: {result.stderr[:300]}")
        return

    parsed = parse_output(result.stdout, layer_names)
    if parsed is None:
        log("   !! consolidate: delimiter markers missing in bonsai output.")
        log(f"      First 400 chars: {result.stdout[:400]}")
        return

    write_layers(main_topic, parsed, layers_cfg, base_dir)
    log(f"   >> consolidated {list(parsed.keys())} written for: {main_topic} (from {len(sources)} source page(s))")


def _record_ingest_result(topic: str, started_at: float, ok: bool, note: str = ""):
    duration = round(time.time() - started_at, 1)
    _last_ingest["topic"] = topic
    _last_ingest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _last_ingest["duration_seconds"] = duration
    _last_ingest["ok"] = ok
    _push_feed(
        icon="ok" if ok else "warning",
        title=f"{topic}: {'ingested' if ok else 'failed'}",
        note=note or f"{duration}s",
    )


def process_file(raw_path: Path):
    topic = raw_path.stem
    started_at = time.time()
    log(f"-> Processing: {raw_path.name} (topic={topic})")

    route = match_route(topic)
    route_rules = ""
    if route:
        log(f"   >> route matched: tag={route.get('tag')} base_dir={route.get('base_dir')}")
        route_rules = ROUTE_RULES_TEMPLATE.format(tag=route.get("tag", ""))
    base_dir = get_base_dir(route)
    layers_cfg = get_layers(route)

    main_topic = parse_hierarchical_topic(topic)
    consolidate = main_topic is not None and any(n in layers_cfg for n in CONSOLIDATED_LAYER_NAMES)
    file_layers_cfg = layers_cfg
    if consolidate:
        # MAIN_/SUB_ topics never get their own llm/minified — those are always
        # regenerated at the MAIN level below, from all known documentation pages.
        file_layers_cfg = {n: cfg for n, cfg in layers_cfg.items() if n not in CONSOLIDATED_LAYER_NAMES}

    raw_content = raw_path.read_text(encoding="utf-8")
    prompt, layer_names = build_prompt(topic, raw_content, file_layers_cfg, route_rules)

    log(f"   Running bonsai ({OLLAMA_MODEL}, think={OLLAMA_THINK}) ... (layers={layer_names}, timeout={CLAUDE_TIMEOUT}s)")
    try:
        result = run_llm(prompt, timeout=CLAUDE_TIMEOUT)
    except TimeoutError:
        log(f"   !! Timed out after {CLAUDE_TIMEOUT}s — skipping.")
        _record_ingest_result(topic, started_at, ok=False, note=f"timed out after {CLAUDE_TIMEOUT}s")
        return
    except ConnectionError as e:
        log(f"   !! {e}")
        _record_ingest_result(topic, started_at, ok=False, note=str(e)[:200])
        return

    if result.returncode != 0:
        log(f"   !! bonsai error: {result.stderr[:300]}")
        _record_ingest_result(topic, started_at, ok=False, note=f"bonsai error: {result.stderr[:150]}")
        return

    parsed = parse_output(result.stdout, layer_names)
    if parsed is None:
        log("   !! Delimiter markers missing in bonsai output.")
        log(f"      First 400 chars: {result.stdout[:400]}")
        _record_ingest_result(topic, started_at, ok=False, note="delimiter markers missing in model output")
        return

    write_layers(topic, parsed, file_layers_cfg, base_dir)
    log(f"   >> {len(parsed)} layers written for: {topic} (base_dir={base_dir}, layers={list(parsed.keys())})")
    _record_ingest_result(topic, started_at, ok=True, note=f"{len(parsed)} layer(s) written")

    if consolidate:
        regenerate_consolidated_layers(main_topic, base_dir, layers_cfg, route_rules)

    archive_file(raw_path)


def get_pending_files() -> list:
    files = list(RAW_DIR.glob("*.md"))
    files.sort(key=lambda f: f.stat().st_mtime)
    return files


def main():
    RAW_DIR.mkdir(exist_ok=True)
    routes = load_routes(force=True)
    signal.signal(signal.SIGUSR1, _handle_wake_signal)
    log(f">> ingest_worker started | pid={os.getpid()} | raw={RAW_DIR} | poll={POLL_INTERVAL}s | "
        f"engine=bonsai-ollama:{OLLAMA_MODEL}:think={OLLAMA_THINK} | routes={len(routes)}")
    write_status(len(routes))

    while True:
        load_routes()  # cache TTL'i (ROUTES_RELOAD_INTERVAL) dolmussa sessizce yeniler
        pending = get_pending_files()
        if pending:
            log(f">> {len(pending)} file(s) queued.")
            for f in pending:
                process_file(f)
        else:
            log(">> Queue empty, waiting...")
        write_status(len(_routes_cache.get("routes", [])))
        _wake_event.wait(timeout=POLL_INTERVAL)
        _wake_event.clear()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log(">> Stopped (Ctrl+C).")
