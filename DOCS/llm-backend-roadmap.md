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

- **Claude API** (Anthropic Messages API) — swap the local `/api/chat` POST for an Anthropic
  API call. Removes the GPU dependency entirely; trades it for API cost + a network dependency.
  Natural fit for the `documentation`/`brief` layers where quality matters most and volume is
  lowest.
- **Ollama Cloud** — same `/api/chat`-shaped client code, different `OLLAMA_URL` pointing at a
  hosted Ollama endpoint instead of `host.docker.internal`. Smallest code change of the three
  (the wire format doesn't change), but still a per-request cost and a new secret (API key) to
  keep out of git per `INDEP_GIT_RULES`.
- **OpenCode** — evaluate as a possible orchestration layer if ingest ever needs actual tool-use
  (file reads, running verification commands) rather than a single prompt-in/text-out call, which
  is all `call_ollama()` does today.

## Open questions (for whenever this gets built)

- Per-layer routing: does `JSONS/instances/<name>.json`'s `layers.<layer>` config grow a
  `backend`/`model` field, so e.g. `documentation` can use a stronger cloud model while
  `minified`/`llm` stay on the fast local one? If so, does `gpu_lock()` still need to serialize
  cloud-backed calls too, or does it become dead weight for anything that isn't local-only?
- Cost/secrets: any cloud backend introduces an API key that must follow the same
  never-in-git rule as everything else in `INDEP_GIT_RULES`'s Configuration section.
