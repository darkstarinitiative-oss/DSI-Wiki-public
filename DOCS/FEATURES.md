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

**Pluggable LLM backend (HTTP side)**
- `common/ollama_lock.py`'s `call_ollama()` and the ingest daemon's `run_llm()` both read an
  optional `LLM_WIKI_OLLAMA_API_KEY` and send `Authorization: Bearer <key>` when set — so Ollama
  Cloud, a Hugging Face OpenAI-compatible endpoint, or a self-hosted router in front of multiple
  backends is a `.env` change, not a code change. See `DOCS/llm-backend-roadmap.md`.
- Covered by an automated test (`TESTS/run_full_test_suite.sh`'s "Pluggable backend" check —
  verifies the header actually gets sent when the key is set).

**Testing / release process**
- `TESTS/run_full_test_suite.sh` — 19 automated checks: every `/api/*` endpoint, both `/http/*`
  UI pages, all CLI proxies, an MCP round-trip, the pluggable-backend header check, and 5 live
  health checks (containers, Ollama, cloudflared, fact-check timer). Exit 0 iff everything passes.
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
  (`SERVICES/DSI-Wiki-HTTP-Config.container.json`) has an empty `subdomain_routes: {}` — noticed
  during this session's work, not yet fixed.
- No per-instance/per-layer backend *routing* (e.g. `documentation` on a stronger cloud model
  while `minified`/`llm` stay local) — only single-backend swapping via `.env`.
- Claude API backend not implemented — Anthropic's request/response shape differs enough
  (message structure, `x-api-key` header, no `message.content` field) that it needs real adapter
  code, not just the URL/key config swap that covers Ollama Cloud/HuggingFace/a router.
- CLI-agent backends (Claude Code, OpenCode, Aider) not implemented — different integration
  shape entirely (subprocess + prompt/task, not an HTTP chat call). See
  `DOCS/llm-backend-roadmap.md`.
- AI-chat-to-raw-note adapter (turning a coding-session transcript into a `raw/<topic>.md` note
  automatically) not implemented — scoped as a future Claude Code plugin/extension, not part of
  this repackaging pass. See `DOCS/adapters-roadmap.md`.
- Multi-collaborator git workflow (MR-gated pushes, required reviewers) intentionally undefined
  — `INDEP_GIT_RULES` leaves this to each project once it actually has more than one contributor.
- `Wiki-BASE` layer-file ownership is inconsistent (some files `ozan:ozan`, some `root:root`,
  depending on whether they were last written by a host-side hand-edit or by the `ingest`
  container) — not a functional bug (the container can always write; only host-side hand-edits
  hit `EACCES` on root-owned files) but worth normalizing eventually.

## Next development session

No pending release — `v0.2.0` is on `production`, pushed to GitLab + GitHub, test run logged to
`INDEP_TEST_RESULTS`. Real open work, roughly in priority order:

1. Fix the container `subdomain_routes: {}` gap so the 4 wiki hostnames actually path-scope
   instead of all hitting the same root.
2. Decide whether the sanitized public fork (discussed, not built) is still wanted, and if so
   scope what "sanitized" means concretely (which files/paths get stripped) before building it.
3. Claude API adapter, if a cloud backend without an HTTP/Ollama-compatible wire format becomes
   worth it.
4. Normalize `Wiki-BASE` file ownership (see Known Issues above).
