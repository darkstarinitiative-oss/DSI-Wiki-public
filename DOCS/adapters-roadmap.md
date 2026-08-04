# Roadmap — AI chat -> raw documentation-log adapters

Not implemented yet. Noted here per an explicit scoping decision: build it later as a Claude
plugin/extension, not as part of this repackaging pass.

## Idea

Right now, turning an AI coding-session transcript (e.g. this repo's own
`INDEP_DSI_UBUNTU_SETUP` seed note) into a `raw/<topic>.md` note is a manual step: someone reads
back over the session and writes the note by hand.

The roadmap idea is an adapter — most likely shipped as a Claude Code plugin/extension — that
watches or is handed an AI chat session and converts it into a properly-formed raw note
(respecting the `MAIN_`/`SUB_`/`INDEP_`/`OBSOLETE_` key convention, see
`DOCS/Documentation_Example_schema.md`), then drops it via `TOOLS/DSI-Wiki-Raw-Writer.py` (or
writes directly into `$WIKI_RAW_DIR`) for the ingest daemon to pick up.

## Open questions (for whenever this gets built)

- Trigger: automatic (session-end hook) vs. manual (`/wiki-log` style command)?
- Source: Claude Code's own session JSONL transcripts vs. a generic paste/export input?
- Topic naming: how does the adapter decide `MAIN_`/`SUB_`/`INDEP_` and the topic slug from an
  unstructured conversation?
