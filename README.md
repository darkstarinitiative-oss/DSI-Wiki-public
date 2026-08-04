# DSI-Wiki

**Version 0.1a**

Multi-layer wiki generation and serving system. Raw notes dropped into a watched directory are
turned into structured documentation layers (`documentation` / `llm` / `minified` / `brief`,
plus opt-in `changelog` / `devlog`) by a local LLM over Ollama, and served over HTTP, MCP and a
web UI from a single gateway. One ingest daemon serves any number of wiki instances.

Full architecture: [`DOCS/architecture.md`](DOCS/architecture.md). Project layout and naming
rules: [`DOCS/naming-conventions.md`](DOCS/naming-conventions.md). Prerequisites:
[`Requires.md`](Requires.md).

## Setup

**Docker (primary path):**

```
git clone <repo> && cd DSI-Wiki
cp SERVICES/.env.example SERVICES/.env   # fill in host paths + Ollama URL/model
docker compose -f SERVICES/docker-compose.yml up -d
```

See [`SERVICES/DEPLOY.md`](SERVICES/DEPLOY.md) for the full step-by-step (Docker install check,
verification, seeding the first note).

**Non-Docker / systemd (fallback):**

```
git clone <repo> && cd DSI-Wiki
./setup.sh
```

`setup.sh` interactively creates `CODE/ingest/.env` (from `SERVICES/.env.example`), your first
`JSONS/instances/<name>.json` (from `default.json`) and runs the supervisor
(`TOOLS/DSI-Wiki-Service-Supervisor.py`), which generates the routing config and
installs/starts the systemd `--user` services (`dsi-wiki-ingest.service`, `dsi-wiki-http.service`).

Manual equivalent:

1. `cp SERVICES/.env.example CODE/ingest/.env` and fill it in (`LLM_WIKI_RAW_DIR`,
   `LLM_WIKI_ARCHIVE_DIR`, `LLM_WIKI_POLL_INTERVAL`, `LLM_WIKI_ROUTES`, `SERVICE_PORT`).
2. Copy `JSONS/instances/default.json` to `JSONS/instances/<name>.json`; set `name`, `base_dir`,
   optional `keyword` / `tag`, `enabled: true`.
3. `python3 TOOLS/DSI-Wiki-Service-Supervisor.py`

## Project layout

```
CODE/       core functionality (ingest daemon, gateway, mcpserver, ui, common)
TOOLS/      admin/maintenance scripts (incl. the service supervisor)
SKILLS/     externally-exposed functionality: CLI implementations + SKILL.md defs
DOCS/       documentation tree (architecture, conventions, restored design docs)
JSONS/      instance configs + generated routing config + HTTP gateway config
DATA/       project-specific data shipped with the repo (seed notes)
SERVICES/   Dockerfile, docker-compose.yml, systemd units, DEPLOY.md
TESTS/      end-to-end smoke tests
STATUS.json externally-readable health/control data (generated, gitignored)
```

## Raw vs. base directories

- **Raw is global** — one drop directory for the whole service (`WIKI_RAW_DIR` / `LLM_WIKI_RAW_DIR`);
  after successful ingest a note moves to the archive dir.
- **Base is per-instance** — each `JSONS/instances/<name>.json` sets its own `base_dir`, under
  which that instance's layer folders (`documentation/`, `llm/`, `minified/`, `brief/`, …) are
  written.
- **Routing (raw → instance):** topic name is matched against each enabled instance's `keyword`
  (substring); a note can force-route with a `Tags: <tag>` line. No match falls back to
  `default_base_dir` in the generated `JSONS/DSI-Wiki-Multi-Server-Config.json`.
- **`JSONS/DSI-Wiki-Multi-Server-Config.json` is generated, never hand-edited** — re-run the
  supervisor after any instance change. If it is ever reset to the empty committed template,
  the ingest service will crash-loop on the first unrouted note; fix by re-running the
  supervisor.

## Layers

Defined per instance in the `layers` field of `JSONS/instances/<name>.json` — see
[`DOCS/Documentation_Content_Requirements.md`](DOCS/Documentation_Content_Requirements.md) and
[`DOCS/Documentation_Example_schema.md`](DOCS/Documentation_Example_schema.md) for the
MAIN_/SUB_/INDEP_/OBSOLETE_ key format.

## Usage

**Write:** drop a note at `raw/<topic>.md` — picked up within one poll interval, or immediately
via `SIGUSR1` to the ingest process (or `TOOLS/DSI-Wiki-Raw-Writer.py`).

**Read (internal, CLI — the standard path):**

```
DSI-wiki-topics [--instance <name>] [--layer minified]
DSI-wiki-get <topic> [--instance <name>] [--layer minified]
DSI-wiki-search <query> [--instance <name>] [--layer all]
DSI-wiki-rename <old> <new>        # across all layers
DSI-wiki-delete <topic>            # across all layers
DSI-wiki-internal-scan --topic <t> | --all   # doc-vs-minified drift report
```

(Wrappers in `~/.local/bin/` -> `SKILLS/cli/*.py`; they read the layer files directly.
Native/systemd deployments get these for free from `setup.sh`. **Docker deployments**
(`SERVICES/DEPLOY.md`) need them installed separately, since `SKILLS/cli/*.py` only exists
inside the containers: run `bash TOOLS/install-cli-proxies.sh` once, from the repo root, to
generate `~/.local/bin/DSI-wiki-*` wrappers that proxy each call through
`docker compose exec` — reads go to `gateway`, writes (`rename`/`delete`) go to `ingest`,
since `gateway`'s `WIKI_BASE_DIR` mount is read-only.)

**Read (external):** HTTP gateway on `:8430` — `GET /api/instances`,
`GET /api/topics?instance=&layer=`, `GET /api/wiki?instance=&topic=&layer=`,
`GET /api/search?instance=&q=&layer=`, `GET /api/status`; MCP at `/mcp` with the same three tools.

**Add an instance:** new JSON under `JSONS/instances/`, then re-run the supervisor.

## Branches

- `production` — running, stable code (no `TOOLS/`)
- `development` — active development
- `documentation` — full version of this README
- `LLM` — condensed bullet summary for quick context transfer
- `Mini` — single-paragraph gist
