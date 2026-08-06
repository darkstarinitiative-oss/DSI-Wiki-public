# DEPLOY.md — server-side deployment playbook

For a Claude Code session (or a human) running **directly on the target server**, with no other
context than this file. Written for the first deploy onto `ajan-simit-gtx1070` (192.168.1.83),
but generic enough for any Docker-capable Linux host with a local Ollama.

This machine is expected to have an actual NVIDIA GPU (GTX1070) available to Ollama, unlike the
laptop this package was developed and smoke-tested on (CPU-only Ollama there — generation was
slow but the packaging/serving path was fully verified working). On a real GPU, Ollama generation
should be fast; if it isn't, see the timeout note in step 6.

## 0. Prerequisites check

See [`../Requires.md`](../Requires.md) for the full list. In short, you need:

- Docker Engine + the Compose plugin (`docker compose`, not standalone `docker-compose`).
- A local Ollama with `qwen3:4b` pulled, reachable from containers on `host.docker.internal:11434`.

```
docker --version && docker compose version
```

If Docker is missing, install Docker Engine + Compose plugin per your distro (e.g. on
Debian/Ubuntu, the official convenience script `curl -fsSL https://get.docker.com | sh`, or the
distro's `docker.io` + `docker-compose-plugin` packages). After install, either:

- add your user to the `docker` group (`sudo usermod -aG docker $USER`) **and start a genuinely
  fresh login session** before trusting group-less `docker` commands — a `newgrp docker` or a new
  terminal tab in an already-running desktop session is not reliably enough; verify with
  `docker ps` before relying on it — or
- just prefix every docker/compose command below with `sudo`. This is the path of least
  resistance and is what actually worked during development — don't burn time chasing group
  propagation if it's being stubborn, `sudo docker ...` bypasses the question entirely.

## 1. Ollama: install, pull the model, and fix the bind address

```
ollama --version || curl -fsSL https://ollama.com/install.sh | sh
ollama list                 # check whether qwen3:4b is already pulled
ollama pull qwen3:4b        # ~2.5GB, if not
```

**Critical, easy to miss:** Ollama's default install binds to `127.0.0.1:11434` only. A
container reaching it via `host.docker.internal` (mapped to the host's docker-bridge gateway IP,
e.g. `172.17.0.1`, NOT `127.0.0.1`) will get `Could not connect to server` — the ingest daemon
will silently retry forever (fast-fail loop, never archives any note, never errors out loudly).
This is exactly what happened during laptop development and cost real time to diagnose — fix it
up front here instead of rediscovering it:

```
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf <<< $'[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"'
sudo systemctl daemon-reload
sudo systemctl restart ollama.service
```

Verify it's actually listening on all interfaces (not just `127.0.0.1`) and that a container-side
address can reach it:

```
ss -tlnp | grep 11434                                   # expect "*:11434", not "127.0.0.1:11434"
BRIDGE_IP=$(ip -4 addr show docker0 | grep -oP 'inet \K[\d.]+')
curl -sS "http://$BRIDGE_IP:11434/api/tags"              # expect a JSON model list, not connection refused
```

If `systemctl restart` reports success but `ss` still shows only `127.0.0.1` and the same old
PID/uptime, the restart didn't actually happen (seen once during development, cause not fully
diagnosed) — re-run `sudo systemctl restart ollama.service` alone and re-check.

Binding to `0.0.0.0` exposes Ollama to the whole LAN, not just Docker — acceptable for this
deployment's threat model (private LAN), but worth knowing.

## 2. Clone the repo

```
mkdir -p ~/BASE/MAIN && cd ~/BASE/MAIN     # or wherever this server's project convention lives
git clone https://gitlab.com/darkstarinitiative/DSI-Wiki.git
cd DSI-Wiki
```

## 3. Configure

```
cp SERVICES/.env.example SERVICES/.env
```

Edit `SERVICES/.env` — fill in real host paths (create the directories if they don't exist) and
confirm the Ollama settings:

```
WIKI_RAW_DIR=/home/<user>/CLEANUP/DATA/Wiki-RAW           # or this server's chosen equivalent
WIKI_ARCHIVE_DIR=/home/<user>/CLEANUP/DATA/Wiki-ARCHIVE
WIKI_BASE_DIR=/home/<user>/CLEANUP/DATA/Wiki-BASE
INSTANCES_DIR=<repo>/JSONS/instances
WIKI_LOCK_DIR=/home/<user>/CLEANUP/DATA
LLM_WIKI_OLLAMA_URL=http://host.docker.internal:11434/api/chat
LLM_WIKI_OLLAMA_MODEL=qwen3:4b
SERVICE_PORT=8430
```

Leave `LLM_WIKI_POLL_INTERVAL` and `LLM_WIKI_CLAUDE_TIMEOUT` at their `.env.example` defaults (60s
/ 300s) unless step 6's real ingest test shows the GPU needs more time per generation — the 300s
default was too short for the CPU-only dev laptop but should be generous for a GTX1070.

Only `Cain-the-elder` ships in `SERVICES/instances.container/` (baked into the image at build
time — the real, host-pathed `JSONS/instances/*.json` is gitignored and never enters the image).
If this server needs additional instances (e.g. `ihalemobil`, `witch`, both of which point at
host paths that only exist on the original dev machine), add their JSON files under
`SERVICES/instances.container/` and rebuild — don't expect them to appear from `.env` alone.

## 4. Build and start

```
docker compose -f SERVICES/docker-compose.yml --env-file SERVICES/.env up -d --build
docker compose -f SERVICES/docker-compose.yml --env-file SERVICES/.env ps
```

Expect two containers, `DSI-WIKI.docker.gateway` and `DSI-WIKI.docker.ingest` (host-wide naming
convention: `DSI-<PROJECT>.docker.<service>` — identifies it as Docker, which project, and which
service at a glance; see INDEP_DOCKER_RULES in the wiki).

## 5. Verify the package (no Ollama needed for this part)

```
sudo bash TESTS/docker_test.sh
```

This builds a throwaway single-container instance, seeds a topic directly (bypassing Ollama
entirely), and checks `/api/instances`, `/api/topics`, `/api/wiki`, the in-container CLI
(`SKILLS/cli/wiki_topics.py`), and `/api/status`. If this fails, it's a packaging/build problem,
not an Ollama/LLM problem — fix before moving to step 6.

Then sanity-check the real running stack:

```
curl -sS http://localhost:8430/api/instances     # {"instances":["Cain-the-elder"]}
curl -sS http://localhost:8430/api/status         # live status once ingest has polled at least once
curl -sS "http://localhost:8430/api/topics?instance=Cain-the-elder"   # {"topics":[]} before any real ingest
```

Or just open `http://localhost:8430/http/dashboard` in a browser — the Health widget shows the
same status live (services, raw-note queue depth, last-ingest timing, GPU), and the topic widget
lets you create a `MAIN_`/`SUB_`/`INDEP_` topic without touching a terminal.

## 6. Real ingest test (needs working Ollama connectivity from step 1)

Drop a real note into the configured `WIKI_RAW_DIR` — a topic name without `ihalemobil`/`witch`
keywords will route to `Cain-the-elder` via `default_base_dir`:

```
cat > "$WIKI_RAW_DIR/INDEP_DEPLOY_SMOKE_TEST.md" <<'EOF'
# INDEP_DEPLOY_SMOKE_TEST

This note verifies the DSI-Wiki Docker deployment on this server end-to-end: the ingest
container picks this up, calls Ollama (qwen3:4b, via host.docker.internal), generates the
documentation/llm/minified/brief layers, and archives this raw file. This is a test note, not
real project content.
EOF
```

Wait for it to be archived (polls every `LLM_WIKI_POLL_INTERVAL`, default 60s, or trigger
immediately with `SIGUSR1` to the ingest process/container):

```
until [ ! -f "$WIKI_RAW_DIR/INDEP_DEPLOY_SMOKE_TEST.md" ]; do sleep 5; done
ls "$WIKI_ARCHIVE_DIR"
find "$WIKI_BASE_DIR" -iname "*DEPLOY_SMOKE_TEST*"
curl -sS "http://localhost:8430/api/topics?instance=Cain-the-elder"
curl -sS "http://localhost:8430/api/wiki?instance=Cain-the-elder&topic=INDEP_DEPLOY_SMOKE_TEST&layer=minified"
```

If the raw file never disappears: check `docker logs <ingest-container-name> --tail 100` for
`ConnectionError`/`TimeoutError` — see step 1 (Ollama bind address) and the timeout note in step
3 first; those are the two failure modes actually seen during development.

## 7. Install the CLI proxies (recommended)

Docker deployments don't get `~/.local/bin/DSI-wiki-*` for free the way `setup.sh`'s
native/systemd path does — `SKILLS/cli/*.py` only exists inside the containers. Run once:

```
bash TOOLS/install-cli-proxies.sh
```

This generates host-side wrappers that proxy each call through `docker compose exec` (reads via
`gateway`, writes via `ingest` — see the script's comments for why). See README.md's Usage
section for the resulting command list.

## 8. Bootstrap self-documentation (recommended)

DSI-Wiki can document itself the same way it documents anything else: open a `MAIN_<ProjectName>`
topic for *this* deployment and feed it the project's own README/DOCS/architecture as raw notes
(see `INDEP_WIKI-RULES` for the exact MAIN_/SUB_/INDEP_ format once that topic exists in your
instance). Concretely, once step 6 has proven ingest works end-to-end:

```
cat DOCS/architecture.md DOCS/naming-conventions.md README.md \
    > "$WIKI_RAW_DIR/MAIN_<ProjectName>.md"
```

wait one poll interval, then confirm all four layers exist for it via `DSI-wiki-get`. This gives
any agent or teammate who later connects to this deployment a real, queryable description of the
deployment itself — not just the generic repo docs.

## 9. Done

At this point: package builds, gateway serves, CLI reads, and a real note went through ingest →
Ollama → all four layers → archive. This is the "first stake" — DSI-Wiki running as the first
service on this server, cloned straight from `gitlab.com/darkstarinitiative/DSI-Wiki`.

Next steps from here are ordinary operations, not part of this playbook: point real raw-note
sources at `$WIKI_RAW_DIR`, add real instances under `SERVICES/instances.container/` + rebuild as
needed, and consider `systemctl enable` equivalents / a reverse proxy in front of `:8430` if this
is meant to be reachable outside the LAN. For commit/branch/versioning conventions once you start
changing this deployment's code, see `INDEP_GIT_RULES`.
