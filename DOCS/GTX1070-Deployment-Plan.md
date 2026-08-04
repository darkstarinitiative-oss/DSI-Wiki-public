# GTX1070 Deployment Plan

**Goal:** deploy DSI-Wiki as the first service ("first stake") on the newly-installed GPU server
`ajan-simit-gtx1070` (192.168.1.83), running fully from a fresh `git clone` — no manual copying
from the dev laptop.

## Status

**Done (dev laptop, this repo, already pushed):**

- Project restructured onto the standard `CODE/TOOLS/SKILLS/DOCS/JSONS/DATA/SERVICES/TESTS`
  schema; all stale path references fixed.
- `STATUS.json` + `Requires.md` + `DOCS/` tree written.
- Docker packaging built and verified locally: `SERVICES/Dockerfile` +
  `SERVICES/docker-compose.yml` (two services from one image — `ingest` polling daemon,
  `gateway` on `:8430`), confirmed building and serving via `TESTS/docker_test.sh`.
- Git remotes fixed and pushed:
  - `origin` → `gitlab.com/darkstarinitiative/DSI-Wiki` (existing repo, `production` branch)
  - `github` → `github.com/darkstarinitiative-oss/DSI-Wiki` (newly created, private)

**Not done here, deliberately deferred to the server:**

- The real ingest → Ollama → documentation/llm/minified/brief pipeline was **not** verified
  end-to-end on this laptop — its Ollama is CPU-only, and generation across four layers proved
  too slow to test practically. The GTX1070 has a real GPU and should be fast enough to actually
  verify this for the first time.
- `DATA/seed-notes/INDEP_DSI_UBUNTU_SETUP.md` (a planned write-up of the server's own install
  saga) was skipped — not enough reliable source material found yet.

## Execution boundary

Everything above happened in **this** session, on the dev laptop. Everything below happens in a
**separate Claude Code session running directly on the server** (192.168.1.83) — this session
does not SSH in or execute anything there. This document is the plan; the exact commands for
whoever/whatever runs on the server are in **[`../SERVICES/DEPLOY.md`](../SERVICES/DEPLOY.md)**,
which is written to be followed with no other context.

## Phase 4 — server-side steps (see DEPLOY.md for exact commands)

1. Confirm Docker Engine + Compose plugin are installed; if not, install them.
2. Confirm/install Ollama, pull `qwen3:4b`, and **fix its bind address** — a fresh Ollama install
   binds to `127.0.0.1:11434` only, which is unreachable from a container via
   `host.docker.internal`. This bit the dev-laptop verification and cost real time to diagnose;
   `DEPLOY.md` has the exact systemd override to apply it up front.
3. `git clone` the repo from GitLab (or GitHub) onto the server.
4. `cp SERVICES/.env.example SERVICES/.env`, fill in real server-local host paths and confirm the
   Ollama URL/model.
5. `docker compose -f SERVICES/docker-compose.yml up -d --build`.
6. Run `TESTS/docker_test.sh` — confirms packaging/serving/CLI without touching Ollama at all.
7. Drop a real raw note, wait for it to be picked up, and confirm **all four layers actually
   generate and the raw note archives** — the one thing this laptop couldn't prove.
8. Once confirmed: DSI-Wiki is live on the server as the first deployed service.

## Why this split

The dev laptop's job was to prove the *package* is correct — it builds, it serves, the CLI and
API work, the code is right. The GPU server's job is to prove the *pipeline* is correct at
realistic speed — something the laptop's hardware couldn't do in a reasonable amount of time.
Splitting it this way meant the server-side session gets a package that's already known-good,
and only has to verify the one thing that genuinely needed different hardware.
