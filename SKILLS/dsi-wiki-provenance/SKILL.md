---
name: dsi-wiki-provenance
description: Trace where a claim (string) appears across all layers of a DSI-Wiki instance — file, line, mtime per hit. Use before editing/removing wiki content to find every place a fact lives.
---

# DSI Wiki Provenance

## Usage

```
DSI-wiki-provenance [--instance Cain-the-elder] [--topic <topic_filter>] "<claim string>"
```

Examples:
```
DSI-wiki-provenance "qwen2.5-coder"
DSI-wiki-provenance --instance Cain-the-elder --topic INDEP_LLM_RULES "Bonsai"
```

Output: one line per hit — `<layer>/<topic>.md | <line_no> | <mtime> | <matching line excerpt>`.
Exit 0 with hits, exit 1 when no match found.

## Files
- Source: `~/BASE/MAIN/DSI-Wiki/SKILLS/cli/provenance.py`
- Wrapper: `~/.local/bin/DSI-wiki-provenance` (`#!/bin/sh` + `exec python3 <source> "$@"`)

## Status
Wrapper fixed and `--help` verified live 2026-07-22 (previous wrapper was a non-functional stub;
the earlier "test_output" recorded in this file was fabricated and has been removed).
