---
name: dsi-wiki-read
description: Read the DSI wiki from the shell — list topics, get a topic's content, or search — via local CLIs (no MCP, no HTTP). This is the standard internal access path; MCP is external-only.
---

# DSI Wiki Read (get / topics / search)

Internal consumers (Claude sessions, dispatcher tasks, services, workers) read the wiki with
these CLIs instead of `mcp__llm-wiki__*` calls. They import `HTTPService/api_app.py` functions
directly — pure file reads, no server round-trip.

## Usage

```
DSI-wiki-topics [--instance Cain-the-elder] [--layer minified]
DSI-wiki-get <topic> [--instance Cain-the-elder] [--layer minified]
DSI-wiki-search <query> [--instance Cain-the-elder] [--layer all]
```

- `DSI-wiki-topics` — one topic per line.
- `DSI-wiki-get` — topic content to stdout; exit 1 if not found.
- `DSI-wiki-search` — `<layer>/<topic>: <excerpt>` per hit; exit 1 if no results.
- Unknown instance → exit 2. Layers: raw, documentation, llm, minified, changelog, devlog.

## Session bootstrap

`~/.claude/CLAUDE.md` uses these for every conversation:
`DSI-wiki-topics` + `DSI-wiki-get <relevant topic>` + `DSI-wiki-get INDEP_LLM_RULES`.

## Files
- Sources: `~/BASE/MAIN/DSI-Wiki/SKILLS/cli/wiki_get.py`, `wiki_topics.py`, `wiki_search.py`
- Wrappers: `~/.local/bin/DSI-wiki-get`, `DSI-wiki-topics`, `DSI-wiki-search`

## Status
Built by dispatcher task t_1201192c, all three verified live 2026-07-22.
