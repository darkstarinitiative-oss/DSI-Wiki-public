#!/usr/bin/env python3
"""Fix MAIN_ topics in Wiki-BASE: align llm/minified layers with documentation (source of truth)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "CODE"))
from gateway.api_app import load_instances

LAYERS = ('raw', 'documentation', 'llm', 'minified', 'brief', 'changelog', 'devlog', 'silinmişler')

def _base_dir():
    scan_dir = str(Path(__file__).resolve().parent.parent / "JSONS" / "instances")
    return load_instances(scan_dir)['default-instance']['base_dir']

def read_layer(topic: str, layer: str) -> str:
    base = Path(_base_dir())
    if not topic.endswith('.md'):
        topic = topic + '.md'
    path = base / layer / topic
    if path.exists():
        return path.read_text(encoding='utf-8')
    return ''

def write_layer(topic: str, layer: str, content: str):
    base = Path(_base_dir())
    if not topic.endswith('.md'):
        topic = topic + '.md'
    path = base / layer / topic
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    print(f"  ✓ Written {layer}/{topic}")

# ============================================================
# CORRECTED CONTENT FOR EACH MAIN_ TOPIC
# ============================================================

FIXES = {}

# 1. MAIN_DSI-AJAN-SiMiT
FIXES['MAIN_DSI-AJAN-SiMiT.md'] = {
    'llm': """D:~/READY/DSI-AJAN-SiMiT/offline-mobile-ai/
- Planning stage (2026-07-21). Architecture and phased roadmap (0-5) defined; Phase 0 (Android/ARM inference feasibility spike) dispatched as first DSI-task. Later phases intentionally not yet broken into tasks — they depend on Phase 0's result (blocking risk R1).
- Technical detail lives in sub-topic [[SUB_DSI-AJAN-SiMiT_Offline-Mobile-AI]] (on-device Flutter + llama.cpp Bonsai-27B assistant).
- Problem & Motivation: Not covered in raw source.
- TEC: Not covered in raw source.
- Configuration: Not covered in raw source.
- Usage: Not covered in raw source.
- Known Issues & Limitations: Not covered in raw source.
- Missing Information: Not covered in raw source.""",
    'minified': """DSI-AJAN-SiMiT (`~/READY/DSI-AJAN-SiMiT/offline-mobile-ai/`) is a project in the planning stage (2026-07-21): an offline on-device mobile AI assistant with a defined phased roadmap (0-5). Phase 0, the Android/ARM inference feasibility spike, has been dispatched as the first DSI-task, while later phases are intentionally deferred pending its result (blocking risk R1); the technical detail lives in the Offline-Mobile-AI sub-topic. Problem & Motivation, TEC, Configuration, Usage, Known Issues, and Missing Information are not covered in raw source."""
}

# 2. MAIN_DSI-ATLAS-R
FIXES['MAIN_DSI-ATLAS-R.md'] = {
    'llm': """D:~/CLEANUP/MAIN/DSI-ATLAS-R/,src/tests
- Onboarded into CLEANUP/MAIN (source root `~/CLEANUP/MAIN/DSI-ATLAS-R/`). Milestone directories m0 (30 files) and m2 (18 files) have real content; m1-synthetic-market-engine is empty (0 files); m3 does not exist as a directory; m4-population-manager (3 files) and m5-strategy-evolution (1 file) are stubs. A prior claim of an "M3-M8 chain" being set up did not result in real work landing on disk.
- Problem & Motivation: Not covered in raw source.
- TEC: Reference architecture for an algorithmic trading platform. Reference document: `docs/ARCHITECTURE.md` (if present). Milestone breakdown: m0=core infrastructure, m1=synthetic market engine (empty), m2=market data pipeline, m3=missing, m4=population manager (stub), m5=strategy evolution (stub). No running services/ports documented.
- Configuration: Not covered in raw source.
- Usage: Not covered in raw source.
- Known Issues & Limitations: m1 empty, m3 missing, m4/m5 stubs only. "M3-M8 chain" claim unverified.
- Missing Information: Architecture details, file/directory structure, key classes/functions by name, data flow, algorithms, running services/processes/ports.""",
    'minified': """DSI-ATLAS-R (source `~/CLEANUP/MAIN/DSI-ATLAS-R/`) is a reference architecture for an algorithmic trading platform onboarded into CLEANUP/MAIN. Milestones m0 (30 files) and m2 (18 files) have real content; m1 (synthetic market engine) is empty, m3 does not exist as a directory, and m4/m5 are stubs only. A prior claim of an "M3-M8 chain" being set up did not materialize on disk. Problem & Motivation, Configuration, Usage, and detailed TEC (architecture, file structure, key classes/functions, data flow, algorithms, running services/ports) are not covered in raw source. Known issues: m1 empty, m3 missing, m4/m5 stubs only."""
}

# 3. MAIN_DSI-Agent-Profiles
FIXES['MAIN_DSI-Agent-Profiles.md'] = {
    'llm': """D:/home/user/CLEANUP/MAIN/hermes-social-automation/profiles/
- Folder structure only known; source (`/home/user/CLEANUP/MAIN/hermes-social-automation/profiles/`) not yet scanned in detail. No documentation generated from actual profile file contents.
- CORRECTED (2026-07-23, nightly fact-check): Root source path `~/.hermes/profiles/` exists and is a directory.
- CORRECTED (2026-07-27, nightly fact-check): Root source path `/home/user/CLEANUP/MAIN/hermes-social-automation/profiles/` does not exist; the claimed `.hermes/profiles/` path was a hallucination in the raw notes.
- Subdirectories (per raw notes): `profiles/orchestrator/`, `profiles/worker/`, `profiles/code-writer/`, `profiles/code-analyst/`, `profiles/reviewer/`.
- Cross-references in source tree: DSI-Wiki > Ingest-Service; DSI-Social-Media > Twitter/Instagram/Content-Pipeline; DSI-System > Agent-Runtime.
- Not documented: how profiles are loaded by the agent runtime and their per-profile configuration.
- Problem & Motivation: Not covered in raw source.
- TEC: Not covered in raw source beyond folder names.
- Configuration: Not covered in raw source.
- Usage: Not covered in raw source.
- Known Issues & Limitations: Source path corrections applied (2026-07-23, 2026-07-27). Actual profile file contents unscanned.
- Missing Information: Profile loading mechanism, per-profile config, actual profile.yaml contents.""",
    'minified': """DSI-Agent-Profiles is the collection of DSI agent-role definitions; the source path has been corrected twice by nightly fact-checks (2026-07-23, 2026-07-27) and the current recorded path `/home/user/CLEANUP/MAIN/hermes-social-automation/profiles/` does not exist — the earlier `~/.hermes/profiles/` claim was a hallucination. Subdirectories per raw notes: orchestrator/, worker/, code-writer/, code-analyst/, reviewer/. Cross-referenced from DSI-Wiki (Ingest-Service), DSI-Social-Media (Twitter/Instagram/Content-Pipeline), and DSI-System (Agent-Runtime). No documentation exists yet for how profiles are loaded by the agent runtime or their per-profile configuration; actual profile file contents remain unscanned. Problem & Motivation, TEC, Configuration, Usage not covered in raw source."""
}

# 4. MAIN_DSI-Cross-Market-Crypto (NEW - only in documentation)
FIXES['MAIN_DSI-Cross-Market-Crypto.md'] = {
    'llm': """D:~/codebase/projects/dsi-cross-market-crypto/
- Status: Not covered in raw source (template output detected in documentation layer).
- Problem & Motivation: Not covered in raw source.
- TEC: Not covered in raw source.
- Configuration: Not covered in raw source.
- Usage: Not covered in raw source.
- Known Issues & Limitations: Documentation layer appears to contain template/output artifact rather than scanned content.
- Missing Information: All CORE sections.""",
    'minified': """DSI-Cross-Market-Crypto: documentation layer contains template/output artifact rather than scanned source content. No source path, architecture, configuration, or usage details are documented. All CORE sections (Status, Problem & Motivation, TEC, Configuration, Usage, Known Issues, Missing Information) are not covered in raw source. A Wave 1 source scan is required."""
}

# 5. MAIN_DSI-Database
FIXES['MAIN_DSI-Database.md'] = {
    'llm': """D:~/READY/DSI-Database/
C:databases/dispatcher/schema.sql; databases/dispatcher/db.py; api/main.py; ~/.hermes/config.yaml (custom_providers); ~/.hermes/.env
R:python3 -m api.main   # or: uvicorn api.main:app  (from ~/READY/DSI-Database); sqlite3 ~/READY/DSI-Database/DATA/dsi-dispatcher.db
X:port 9123 (FastAPI "DSI-Database API"; /health /keys /providers /models /profiles /tasks /executions /events /metrics; no auth) — NOT currently listening

- Actively developed, in-progress migration. Renamed 2026-07-20 from mistakenly-titled `MAIN_DSI-Agent-Simit` — content was always about this project, only the topic name was wrong (a 2026-07-18 raw note had proposed `MAIN_DSI-Database` as the topic name, but ingest created it under the wrong name; see `MAIN_DSI-Wiki` Known Issues for the mechanism gap that allowed this).
- `~/READY/DSI-Database/` is a standalone project directory — not its own git repo, nested inside one large repo rooted at `/home/user`, on branch `development`; recent commits at HEAD.
- Phase 1 of the "Ajan Simit" plan (remove Hermes as a vital DSI dependency). Replaces Dispatcher++'s 7 kanban SQLite DBs, per-task `state.json` sidecars, and `source_registry.py` locks with one consolidated SQLite schema (`databases/dispatcher/schema.sql`, WAL, 11 tables) plus a FastAPI service (`api/main.py`, "DSI-Database API", uvicorn port 9123, 8 routers + /health, no auth).
- DB layer: `databases/dispatcher/db.py`'s `DSIDatabase` class defaulting to `~/READY/DSI-Database/DATA/dsi-dispatcher.db`.
- Problem & Motivation: Replace fragmented Hermes SQLite DBs with consolidated schema.
- Configuration: `~/.hermes/config.yaml` (custom_providers), `~/.hermes/.env`.
- Usage: `python3 -m api.main` or `uvicorn api.main:app` from `~/READY/DSI-Database/`; `sqlite3 ~/READY/DSI-Database/DATA/dsi-dispatcher.db`.
- Known Issues & Limitations: API not currently listening on port 9123. Migration in progress.
- Missing Information: Full router details, authentication plan, migration status per Dispatcher++ board.""",
    'minified': """DSI-Database (`~/READY/DSI-Database/`, nested in the /home/user repo, branch `development`) is Phase 1 of the "Ajan Simit" plan to remove Hermes as a core DSI dependency: it replaces Dispatcher++'s 7 kanban SQLite DBs, per-task `state.json` sidecars, and `source_registry.py` locks with one consolidated SQLite schema (`databases/dispatcher/schema.sql`, WAL, 11 tables) plus a FastAPI service (`api/main.py`, "DSI-Database API", uvicorn port 9123, 8 routers + /health, no auth). The DB layer is `databases/dispatcher/db.py`'s `DSIDatabase` class defaulting to `~/READY/DSI-Database/DATA/dsi-dispatcher.db`. Renamed 2026-07-20 from the mistakenly-titled `MAIN_DSI-Agent-Simit` (content was always correct; only the topic name was wrong — a 2026-07-18 raw note had proposed the correct name but ingest created it under the wrong one). Configuration via `~/.hermes/config.yaml` (custom_providers) and `~/.hermes/.env`. API not currently listening on port 9123; migration in progress."""
}

# 6. MAIN_DSI-Dispatcher-Plus-Plus
FIXES['MAIN_DSI-Dispatcher-Plus-Plus.md'] = {
    'llm': """D:~/READY/Dispatcher-plus-plus,~/.dispatcher-workspaces/<task_id>/,~/LLM-Wiki-BASE/raw/,~/.hermes/kanban/,dispatcher_core/,hermes_bridge/,adapters/
C:dispatcher_core/runner.py,hermes_bridge/kanban_hook.py,interpreter.py,sidecar.py,state.json,source_registry.py,events.py,adapters/logging_adapter.py,adapters/llm_wiki_adapter.py,watchdog.py,~reverse-proxy.py,DESIGN.md,RECOVERY.md,Integration_Theory_For_Dispatcher++.md
R:hermes -p <profile> -z <prompt> --cli;htask create ... --assignee god;hermes -p wiki-ingest;hermes cron list;python3 dispatcher_core/runner.py
X:port 9123 (FastAPI "DSI-Database API"; /health /keys /providers /models /profiles /tasks /executions /events /metrics; no auth) — NOT currently listening

- Actively developed. The previous `runner.py` daemon has been deleted; `the_lonely_shepherd.py` is the sole live daemon for this project, but it does not exist in the current file system as of 2026-07-23 (CORRECTED 2026-07-23, nightly fact-check).
- `the_lonely_shepherd.py:get_board_dbs()` reads active boards from DSI-Database's `kanban_boards` table.
- Polls kanban board SQLite databases every 30 seconds and executes node-graph workflows via Hermes profile subprocesses.
- Runs as `dispatcher.service` systemd unit with a separate `dispatcher-watchdog` cron job for blocked-task reconciliation.
- Two SUB_ topics (Kanban-Bridge, Task-Lifecycle) and the Task-Runner sub-page remain unscanned placeholders.
- Problem & Motivation: Workflow orchestration for DSI kanban boards via Hermes profiles.
- TEC: Architecture: polls kanban SQLite DBs every 30s, executes node-graph workflows via Hermes profile subprocesses. Key files: `dispatcher_core/runner.py` (deleted), `the_lonely_shepherd.py` (missing from FS as of 2026-07-23), `hermes_bridge/kanban_hook.py`, `interpreter.py`, `sidecar.py`, `state.json`, `source_registry.py`, `events.py`, `adapters/llm_wiki_adapter.py`, `watchdog.py`. Systemd unit: `dispatcher.service`; cron: `dispatcher-watchdog`.
- Configuration: Not covered in raw source.
- Usage: `hermes -p <profile> -z <prompt> --cli`; `htask create ... --assignee god`; `hermes -p wiki-ingest`; `hermes cron list`; `python3 dispatcher_core/runner.py`.
- Known Issues & Limitations: `runner.py` daemon deleted; `the_lonely_shepherd.py` missing from filesystem (2026-07-23 fact-check). SUB_ topics unscanned.
- Missing Information: Current daemon implementation details, SUB_ topic content, watchdog logic details.""",
    'minified': """Dispatcher++ is an actively developed workflow-orchestration system that polls kanban board SQLite databases every 30 seconds and executes node-graph workflows via Hermes profile subprocesses. The previous `runner.py` daemon has been deleted; `the_lonely_shepherd.py` was identified as the sole live daemon but a 2026-07-23 nightly fact-check confirmed it does not exist in the current file system. It runs as the `dispatcher.service` systemd unit with a separate `dispatcher-watchdog` cron job for blocked-task reconciliation. Its two SUB_ topics (Kanban-Bridge, Task-Lifecycle) and the Task-Runner sub-page remain unscanned placeholders. Configuration and current daemon implementation details are undocumented."""
}

# 7. MAIN_DSI-GVCS
FIXES['MAIN_DSI-GVCS.md'] = {
    'llm': """D:~/codebase/projects/dsi-gvcs/
R:DSI-Wiki-Source-Scanner.py

- Not