# Roadmap — alternative LLM backends (remove the local-Ollama hard dependency)

Not implemented yet. Noted here per an explicit scoping decision, same as
`adapters-roadmap.md`: capture the idea, don't build it in this pass.

## Why

Every layer of DSI-Wiki (ingest, consolidation, `internal_scan.py`'s drift check, the nightly
fact-check) currently goes through one path: `common/ollama_lock.py` -> a local Ollama instance
on the host GPU (see `INDEP_WIKI-RULES` / `MAIN_SYSTEM` for this deployment's GTX 1070 specifics).
That's a hard dependency on a specific machine having a specific GPU with a model pulled and
warm. It also means ingest throughput is capped by one GPU's VRAM (see `ollama_lock.py`'s own
docstring on the queueing it had to add once a nightly job and interactive ingest started
contending for the same card).

## Idea

Make the backend pluggable behind `common/ollama_lock.py`'s `call_ollama()` interface (or a thin
wrapper around it), with the target model/endpoint selected per-instance or per-layer rather than
hardcoded. Candidate backends, roughly in order of how little new infra they'd need:

- **Ollama Cloud** — same `/api/chat`-shaped client code, different `OLLAMA_URL` pointing at a
  hosted Ollama endpoint instead of `host.docker.internal`. Smallest code change of the group
  (the wire format doesn't change), but still a per-request cost and a new secret (API key) to
  keep out of git per `INDEP_GIT_RULES`.
- **Claude API** (Anthropic Messages API) — swap the local `/api/chat` POST for an Anthropic
  API call. Removes the GPU dependency entirely; trades it for API cost + a network dependency.
  Natural fit for the `documentation`/`brief` layers where quality matters most and volume is
  lowest.
- **Hugging Face** (Inference API / Inference Endpoints) — OpenAI-compatible chat-completions
  shape for many hosted models, so the client code looks like the Claude API case; the actual
  model choice (open-weights vs. proprietary) is a separate decision from the integration itself.
- **Claude Code**, **OpenCode**, **Aider** — these are CLI coding agents, not bare chat
  endpoints: driving them means shelling out to a subprocess with a prompt/task and parsing
  whatever it prints, not a `call_ollama()`-shaped HTTP call. Worth it specifically if ingest
  ever needs actual tool-use (reading files, running verification commands) rather than today's
  single prompt-in/text-out call — e.g. the nightly fact-check's own read-only toolset
  (`CODE/ingest/DSI-Wiki-Nightly-FactCheck.py`) is a hand-rolled version of exactly this pattern,
  and one of these could plausibly replace it instead of hand-rolling more tool loops per job.
- **A self-hosted router in front of all of the above** (e.g. LiteLLM-style, OpenAI/Ollama-
  wire-compatible) — the practical unification point: if one endpoint can front local Ollama,
  Ollama Cloud, Claude, and HuggingFace behind a single OpenAI/Ollama-compatible API, then
  `call_ollama()` barely needs to change at all — just point `LLM_WIKI_OLLAMA_URL` at the router
  and let it handle backend selection/failover/cost routing. The CLI-agent backends (Claude
  Code/OpenCode/Aider) are the exception — those stay a different integration shape regardless
  of what fronts the HTTP-based backends, since they're not HTTP chat endpoints at all.
  **Setup/ownership of this router is out of scope here** — DSI-Wiki's side of the contract is
  just "one configurable base URL + model + optional API key," same as it already is for Ollama.

## Open questions (for whenever this gets built)

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
