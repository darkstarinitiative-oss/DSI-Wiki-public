# DSI-Wiki — feature status

Full list of what's actually done vs. still open, as of `v0.2.0` (current `production`).
Source of truth is this file + `CHANGELOG.md` (release history) + `TESTS/run_full_test_suite.sh`
(what's actually verified) — not memory, not a chat transcript.

## Completed

**Core service**
- Docker Compose deployment: `gateway` (API `/api` + MCP `/mcp` + UI `/http` on one ASGI app,
  port 8430) and `ingest` (raw-note polling, LLM-driven documentation/llm/minified/brief
  generation), from one image.
- Ollama bind-address fix (`0.0.0.0`, was `127.0.0.1`-only) so containers can reach the host GPU.
- Ollama `think:true` leak fixed — `message.thinking` and `message.content` are properly
  separated, so reasoning no longer pollutes generated layer content.
- `common/ollama_lock.py`'s hardcoded-localhost bug fixed (`LLM_WIKI_OLLAMA_URL` env-driven).
- `internal_scan.py` drift-check model (`qwen3:1.7b`) pulled and working.

**CLI / public surfaces**
- Host-side CLI proxies for the Docker deployment (`TOOLS/install-cli-proxies.sh` ->
  `DSI-wiki-topics/get/search/internal-scan/rename/delete`), reads via `gateway`, writes via
  `ingest` (the container holding the read-write `WIKI_BASE_DIR` mount).
- MCP server verified end-to-end: `initialize` -> `tools/list` -> `tools/call` round-trip
  against `wiki_list_topics`/`wiki_get`/`wiki_search`, real data confirmed.
- `/http/dashboard` — Bootstrap widgets page: health status (services, raw-queue depth,
  last-ingest timing, live GPU via Ollama's own `/api/ps`), instance-selectable MAIN_ topic
  list + create-topic form.
- Cloudflare Tunnel Connector (`cloudflared.service`) installed and active, scoped ingress
  (`wiki`/`wiki-api`/`wiki-http`/`wiki-mcp`.dsigames.com.tr -> `127.0.0.1:8430`; unrelated
  hostnames on the same shared tunnel intentionally 404 rather than proxying to a port/SSH that
  doesn't exist on this host). Installer: `SERVICES/cloudflared-install.sh`.

**DSI Info API Standard**
- Schema + rationale written up (`DOCS/info-api-standard.md`): `service`/`version`/`status`/
  `status_note`/`services[]`/`feed[]` (capped at 10, newest first), a passthrough-adapter
  contract (any URL, project's choice) rather than a `/api/status` replacement.
- DSI-Wiki's own implementation: ingest daemon tracks per-topic outcomes + a rolling feed into
  `STATUS.json`; `GET /api/info` (`CODE/gateway/api_app.py`) serves the standard shape.
- Generic conformance-test viewer: `/http/info-viewer` — points at any URL implementing the
  standard, not just DSI-Wiki's own.

**Ops / scheduling**
- Nightly Fact-Check (`CODE/ingest/DSI-Wiki-Nightly-FactCheck.py`) scoped to `MAIN_` topics only
  (was: every topic) and rescheduled 03:00 -> 06:00; installed as a native systemd timer
  (`dsi-wiki-factcheck.service`/`.timer`), active and enabled.
- `LLM_WIKI_CLAUDE_TIMEOUT` raised 300s -> 600s (covers `think:true`'s combined
  thinking+content generation time for larger notes).

**Pluggable LLM backend**
- HTTP side: `common/ollama_lock.py`'s `call_ollama()` and the ingest daemon's `run_llm()` both
  read an optional `LLM_WIKI_OLLAMA_API_KEY` and send `Authorization: Bearer <key>` when set —
  so Ollama Cloud, a Hugging Face OpenAI-compatible endpoint, or a self-hosted router in front of
  multiple backends is a `.env` change, not a code change.
- CLI-agent side: `LLM_WIKI_BACKEND=claude-code` shells out to the `claude` CLI
  (`CODE/common/claude_code_backend.py`) instead of an HTTP call. Real per-call API cost, opt-in
  only. Works wherever `run_llm()` actually executes and has `claude` on PATH + authenticated —
  **not** inside the Docker `ingest` container today (no `claude` CLI in that image).
- See `DOCS/llm-backend-roadmap.md` for what's still not covered (Claude API adapter,
  OpenCode/Aider, per-layer backend routing).
- Covered by two automated tests (`TESTS/run_full_test_suite.sh`): the API-key header check, and
  a real `claude-code` round-trip (skipped automatically if `claude` isn't on PATH).

**Container runs as a non-root user**
- The Docker image (`SERVICES/Dockerfile`) now creates and runs as a non-root user matching the
  host user's UID:GID (`APP_UID`/`APP_GID` build args, default `1000:1000`, overridable in
  `.env`) — files written into bind-mounted host directories (`Wiki-RAW`/`ARCHIVE`/`BASE`, the
  GPU lock dir) come out host-user-owned, not root. Fixes the ownership inconsistency noted
  after `v0.2.0` (some files were `root:root` from before this change; one-time
  `chown -R $APP_UID:$APP_GID` needed on any pre-existing data directories/named volumes when
  upgrading an existing deployment — not needed for a fresh install).

**Sanitization hygiene**
- `SERVICES/cloudflared-install.sh` no longer hardcodes real Cloudflare account/tunnel IDs or
  the domain — all read from `~/.env` (`CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_TUNNEL_ID`/
  `CLOUDFLARE_DNS_ZONE`) at runtime, matching `INDEP_GIT_RULES`'s secrets policy.

**Testing / release process**
- `TESTS/run_full_test_suite.sh` — up to 21 automated checks depending on environment: every
  `/api/*` endpoint, both `/http/*` UI pages, all CLI proxies, an MCP round-trip, both
  pluggable-backend checks, and 5 live health checks (containers, Ollama, cloudflared,
  fact-check timer). Exit 0 iff everything passes.
- Bug this suite caught and fixed on its first real run: `search()`'s excerpt was always the
  first 1500 chars of a file regardless of where the match actually was, so long-document hits
  could show a preview that never contained the matched term. Fixed in both `api_app.py`'s
  `search()` and the CLI's own preview truncation (`SKILLS/cli/wiki_search.py`), which had the
  same bug one level down.
- `INDEP_GIT_RULES` (wiki) now requires a passing test-suite run before any production tag, and
  logging that run's result to `INDEP_TEST_RESULTS` (wiki) — a release with no logged passing
  run for its exact commit isn't a verified release, just a tag.
- `CHANGELOG.md` (Keep a Changelog format), starting at `0.1.0`.
- `v0.1.0` (first production release) and `v0.2.0` (Info API standard, Cloudflare Tunnel,
  pluggable backend auth, search-excerpt fix) both tagged on `production`, pushed to GitLab +
  GitHub. `INDEP_TEST_RESULTS` (wiki) has both releases' passing test runs logged.
- GitHub mirror (`darkstarinitiative-oss/DSI-Wiki`) created and kept in sync with `development`/
  `production`/tags. **Private**, matching `INDEP_GIT_RULES`'s repo-visibility policy (see
  Known Issues below for why this needed a correction mid-session).

## Known Issues & Limitations

- `SERVICES/instances.container/*.json` still bakes the real `Cain-the-elder` instance name into
  the Docker image on every branch. Explicit decision: **not fixing this** — `default.json`
  already covers the real deployment need, redacting the other ~15 files isn't worth it.
- Cloudflare ingress has 4 separate wiki hostnames (`wiki`/`wiki-api`/`wiki-http`/`wiki-mcp`) but
  no path-scoping yet — all four currently route to the same Gateway root. The native config
  (`JSONS/DSI-Wiki-HTTP-Config.json`) already has host->mount rules
  (`wiki-api -> /api`, `wiki-mcp -> /mcp`, `wiki-http`/`wiki -> /http`) via
  `SubdomainDispatchMiddleware`, but the **container** config
  (`SERVICES/DSI-Wiki-HTTP-Config.container.json`) has an empty `subdomain_routes: {}`.
  Explicit decision (2026-08-05): **deferred, not urgent** — all 4 hostnames currently serve the
  full app, so nothing is broken, just not narrowed.
- No per-instance/per-layer backend *routing* (e.g. `documentation` on a stronger cloud model
  while `minified`/`llm` stay local) — only single-backend swapping via `.env`.
- Claude API backend (direct Anthropic Messages API, as opposed to the Claude Code CLI backend,
  which *is* implemented) not implemented — Anthropic's HTTP request/response shape differs
  enough (message structure, `x-api-key` header, no `message.content` field) that it needs real
  adapter code, not just the URL/key config swap that covers Ollama Cloud/HuggingFace/a router.
  Low priority now that Claude Code CLI covers the same underlying model via a different path.
- OpenCode, Aider backends not implemented — same CLI-agent shape as Claude Code (now
  implemented), just not built for these two yet. See `DOCS/llm-backend-roadmap.md`.
- AI-chat-to-raw-note adapter (turning a coding-session transcript into a `raw/<topic>.md` note
  automatically) not implemented — scoped as a future Claude Code plugin/extension, not part of
  this repackaging pass. See `DOCS/adapters-roadmap.md`.
- Multi-collaborator git workflow (MR-gated pushes, required reviewers) intentionally undefined
  — `INDEP_GIT_RULES` leaves this to each project once it actually has more than one contributor.
- Sanitized public fork still not built — only the policy (`INDEP_GIT_RULES`) and a first
  cleanup pass (`cloudflared-install.sh`, above) exist. `SERVICES/DEPLOY.md` and
  `DOCS/GTX1070-Deployment-Plan.md` still contain this real deployment's hostname/LAN IP — that's
  correct for the private repo (it's a real deployment record) but would need a generic rewrite
  for a public fork.

## Next development session

No pending release — `v0.2.0` is on `production`, pushed to GitLab + GitHub, test run logged to
`INDEP_TEST_RESULTS`. Real open work, roughly in priority order:

1. Sanitized public fork, if still wanted — scope concretely which files need a generic rewrite
   (`DEPLOY.md`/`GTX1070-Deployment-Plan.md` real host/IP identified above) vs. which stay as-is.
2. Container `subdomain_routes: {}` path-scoping (deferred, see Known Issues).
3. OpenCode/Aider backends, or a direct Claude API adapter, if either becomes worth it.
