# Alternative LLM backends (remove the local-Ollama hard dependency)

**Status (2026-08-05): the HTTP-endpoint side is implemented.** `common/ollama_lock.py`'s
`call_ollama()` and the ingest daemon's `run_llm()` both now read `LLM_WIKI_OLLAMA_API_KEY`
(optional, default empty) and send it as `Authorization: Bearer <key>` — so pointing DSI-Wiki
at Ollama Cloud, a Hugging Face OpenAI-compatible endpoint, or a self-hosted router in front of
multiple backends is a `.env` change (`LLM_WIKI_OLLAMA_URL` + `LLM_WIKI_OLLAMA_MODEL` +
`LLM_WIKI_OLLAMA_API_KEY`), not a code change. Covered by
`TESTS/run_full_test_suite.sh`'s "Pluggable backend" check. **Claude Code is also implemented**
(2026-08-05) as a second, opt-in backend (`LLM_WIKI_BACKEND=claude-code`) — a different
integration shape (subprocess, not HTTP chat), see `CODE/common/claude_code_backend.py`, but not
a fundamentally harder one: `claude -p <prompt> --output-format json` returns a single JSON
result, shelled out to and parsed the same way `run_llm()` already mirrors a
`subprocess.CompletedProcess` interface for its Ollama path. Real per-call API cost — opt-in,
never the default. **Not** currently usable from the Docker `ingest` container (the image has no
`claude` CLI or its auth), only wherever `run_llm()` executes on a host that has it. OpenCode and
Aider remain unimplemented.

## Why

Every layer of DSI-Wiki (ingest, consolidation, `internal_scan.py`'s drift check, the nightly
fact-check) currently goes through one path: `common/ollama_lock.py` -> a local Ollama instance
on the host GPU (see `INDEP_WIKI-RULES` / `MAIN_SYSTEM` for this deployment's GTX 1070 specifics).
That's a hard dependency on a specific machine having a specific GPU with a model pulled and
warm. It also means ingest throughput is capped by one GPU's VRAM (see `ollama_lock.py`'s own
docstring on the queueing it had to add once a nightly job and interactive ingest started
contending for the same card).

## Idea

The backend is now pluggable behind `common/ollama_lock.py`'s `call_ollama()` interface (URL +
model + optional bearer key, all env-configured) — per-instance/per-layer backend *selection*
(different topics routed to different backends) is not built, just single-backend swapping.
Candidate/supported backends, roughly in order of how little new infra they need:

- **Ollama Cloud** — supported now (same `/api/chat`-shaped wire format, just point
  `LLM_WIKI_OLLAMA_URL` at the hosted endpoint and set `LLM_WIKI_OLLAMA_API_KEY`).
- **Hugging Face** (Inference API / Inference Endpoints, OpenAI-compatible chat-completions) —
  supported now for any HF endpoint that speaks the same `/api/chat`-equivalent shape; endpoints
  with a materially different response schema would need a small adapter, not just config.
- **A self-hosted router** (LiteLLM-style, Ollama/OpenAI-wire-compatible) fronting any mix of the
  above — supported now the same way: point `LLM_WIKI_OLLAMA_URL` at the router.
- **Claude API** (Anthropic Messages API) — **not** supported by the current config-only swap;
  Anthropic's request/response shape differs enough (message structure, `x-api-key` instead of
  `Authorization: Bearer`, no `message.content` field) that it needs real adapter code, not just
  a URL/key change. Natural fit for `documentation`/`brief` where quality matters most and volume
  is lowest, if/when that adapter gets written.
- **Claude Code** — supported now (`LLM_WIKI_BACKEND=claude-code`), for hosts where the `claude`
  CLI is on PATH and authenticated. Real API cost per call.
- **OpenCode**, **Aider** — same CLI-coding-agent shape as Claude Code, not implemented yet. Also
  worth considering for actual tool-use (reading files, running verification commands) rather
  than today's single prompt-in/text-out call — e.g. the nightly fact-check's own read-only
  toolset (`CODE/ingest/DSI-Wiki-Nightly-FactCheck.py`) is a hand-rolled version of exactly this
  pattern, and one of these could plausibly replace it instead of hand-rolling more tool loops
  per job.

Router/multi-backend ownership (picking, standing up, and operating whatever fronts these
endpoints) is out of scope for DSI-Wiki itself — its side of the contract is just "one
configurable base URL + model + optional API key," already true today.

## Open questions (remaining)

- Per-layer routing: does `JSONS/instances/<name>.json`'s `layers.<layer>` config grow a
  `backend`/`model` field, so e.g. `documentation` can use a stronger cloud model while
  `minified`/`llm` stay on the fast local one? If so, does `gpu_lock()` still need to serialize
  cloud-backed calls too, or does it become dead weight for anything that isn't local-only?
  (A router sitting in front of everything may make this moot — the lock only matters for
  contention on *this host's* GPU, not for calls a router dispatches elsewhere.)
- Cost/secrets: any cloud backend introduces an API key that must follow the same
  never-in-git rule as everything else in `INDEP_GIT_RULES`'s Configuration section.
- CLI-agent backends (Claude Code/OpenCode/Aider) need their own timeout/output-parsing story —
  they don't share `run_llm()`'s "one JSON response with a `message.content` field" shape.
