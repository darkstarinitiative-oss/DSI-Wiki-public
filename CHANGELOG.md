# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/) (see `INDEP_GIT_RULES` for the branch/release policy
this repo follows).

This file starts at `0.1.0` — earlier history predates the changelog and isn't reconstructed here.

## [0.2.0] - 2026-08-05

### Added
- DSI Info API Standard (`DOCS/info-api-standard.md`): a passthrough-adapter JSON contract
  (`service`/`version`/`status`/`status_note`/`services[]`/`last_heartbeat`/`feed[]`) for
  cross-project live monitoring. Implemented at `GET /api/info`, with a generic conformance
  viewer at `/http/info-viewer` that works against any URL implementing the standard.
- Cloudflare Tunnel Connector (`SERVICES/cloudflared-install.sh`,
  `cloudflared.service`) — public access via `wiki`/`wiki-api`/`wiki-http`/`wiki-mcp`
  `.dsigames.com.tr`, scoped so unrelated hostnames on the shared account tunnel 404 instead of
  proxying to a port/SSH not present on this host.
- Pluggable LLM backend auth: `LLM_WIKI_OLLAMA_API_KEY` (optional) sends
  `Authorization: Bearer <key>`, so Ollama Cloud / a HuggingFace OpenAI-compatible endpoint / a
  self-hosted router is a `.env` change instead of a code change (`DOCS/llm-backend-roadmap.md`).
- `TESTS/run_full_test_suite.sh` — 19 automated checks (every API endpoint, both UI pages, all
  CLI proxies, an MCP round-trip, the pluggable-backend header, 5 live health checks). Required
  to pass before any production tag (`INDEP_GIT_RULES`), with results logged to
  `INDEP_TEST_RESULTS`.
- `DOCS/FEATURES.md` — single completed/pending feature reference.

### Changed
- Nightly Fact-Check scoped to `MAIN_` topics only (was: every topic) and rescheduled
  03:00 -> 06:00; installed as an active, enabled native systemd timer.
- `INDEP_GIT_RULES`: production tags now require a passing test-suite run first, and repo
  visibility policy made explicit (primary repo private on every host; any public presence is a
  separate sanitized fork, never a visibility flip on the real repo).

### Fixed
- `search()`'s excerpt was always a file's first 1500 characters regardless of where the actual
  match was, so a hit deep in a long document could return a preview that never contained the
  matched term. Centered the excerpt on the match in both `api_app.py` and the CLI's own preview
  truncation (`SKILLS/cli/wiki_search.py`), which had the same bug one level down.

## [0.1.0] - 2026-08-05

### Added
- Docker deployment path (`SERVICES/DEPLOY.md`, `docker-compose.yml`, `Dockerfile`).
- `TOOLS/install-cli-proxies.sh` — host-side `DSI-wiki-*` CLI wrappers for Docker deployments
  (proxied through `docker compose exec`), since `setup.sh`'s native path installs real wrappers
  directly but Docker deployments had no equivalent.
- `/http/dashboard` — a widgets page with a live health panel (services, raw-note queue depth,
  last-ingest timing, GPU snapshot via Ollama's `/api/ps`) and a `MAIN_` topic list + create-topic
  form.
- Native systemd timer (`dsi-wiki-factcheck.timer`/`.service`) for the previously-unscheduled
  nightly fact-check job.
- `DOCS/llm-backend-roadmap.md` — roadmap for removing the hard local-Ollama/GPU dependency.
- `INDEP_GIT_RULES` / `INDEP_WIKI-RULES` — generic, illustrative example wiki topics for a git
  publish policy and the wiki's own key/layer conventions.

### Fixed
- Ollama `think:false` let the ingest model narrate raw chain-of-thought into layer content
  instead of using Ollama's dedicated `thinking` field; switched the default to `think:true`.
- `common/ollama_lock.py`'s `OLLAMA_URL` was a hardcoded `127.0.0.1` default, unreachable from any
  container; now reads `LLM_WIKI_OLLAMA_URL` like the ingest daemon already did.
- The `minified` layer's `LLM:` cross-reference line is now appended deterministically in code
  instead of being model-authored (the model was observed writing the wrong layer name in it).
- `development` had drifted three weeks behind `production` (a full repackaging pass was
  committed straight to `production` and never merged back); repaired via
  `git merge --allow-unrelated-histories -X theirs`, a genuine fast-forward with no history loss.

### Changed
- `LLM_WIKI_CLAUDE_TIMEOUT` default `300s` -> `600s` (`think:true` generation time covers
  thinking + content combined; larger notes were hitting the old timeout).
- `LLM_WIKI_OLLAMA_NUM_PREDICT` default `6000` -> `12000` (same reason).
