# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/) (see `INDEP_GIT_RULES` for the branch/release policy
this repo follows).

This file starts at `0.1.0` — earlier history predates the changelog and isn't reconstructed here.

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
