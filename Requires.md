# Requires

## Docker path (primary)

- Docker Engine + the Compose plugin (`docker compose`, not the standalone `docker-compose`).
- A local Ollama reachable from the containers as `host.docker.internal:11434` (bridge network,
  `extra_hosts: host.docker.internal:host-gateway` — the containers do NOT run Ollama
  themselves, it stays on the host).
- The `qwen3:4b` model pulled on that host Ollama (`ollama pull qwen3:4b`) — this is the code's
  real default (`LLM_WIKI_OLLAMA_MODEL`); check with `ollama list` before assuming it's there.

## Non-Docker / systemd path (fallback)

- Python 3.12+.
- `pip install -r requirements.txt` (`uvicorn`, `starlette`, `mcp<2` — pinned below 2.0, which
  moved `FastMCP` out of `mcp.server.fastmcp`; unpinned installs will break `CODE/mcpserver/`).
- On distros with `PEP 668` externally-managed Python (e.g. `/usr/lib/python3.*/EXTERNALLY-MANAGED`
  present): either a venv, or `pip install --break-system-packages -r requirements.txt`.
- `systemd --user` (for `SERVICES/dsi-wiki-ingest.service` / `dsi-wiki-http.service`, both
  `WantedBy=zulfikar.target` — a custom user target, itself `WantedBy=default.target`).
- Same Ollama + `qwen3:4b` requirement as above, reachable at `localhost:11434` (no
  `host.docker.internal` needed outside a container).

## Either path

- Network access from wherever DSI-Wiki runs to the Ollama host on port `11434`.
- Write access to the raw/archive/base directories configured in `.env` (see
  `SERVICES/.env.example`).
