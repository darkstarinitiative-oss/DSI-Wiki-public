---
name: dsi-wiki-internal-scan
description: "[BROKEN — rebuild pending] Compare documentation vs minified layers of DSI-Wiki topics with a local LLM (Bonsai) to detect factual drift. Do not rely on this skill until rebuilt."
---

# DSI-Wiki Internal Consistency Scanner

## Status: BROKEN (2026-07-22)

A dispatcher worker task (t_8adcc404) gutted `internal_scan.py` down to a 14-line stub while
"fixing" unrelated files; the original scanner body is lost (the `cli/` directory was not yet
under git). The wrapper `~/.local/bin/DSI-wiki-internal-scan` has been re-pointed to the correct
target but the script itself needs a rebuild before this skill works.

## Intended usage (once rebuilt)

```
DSI-wiki-internal-scan --topic INDEP_LLM_RULES
DSI-wiki-internal-scan --instance Cain-the-elder --all
```

- Compares factual claims (model names, paths, ports, commands, statuses) between the
  documentation and minified layers of each topic.
- Report output: `~/CLEANUP/MAIN/DSI-Wiki/reports/internal-scan-YYYYMMDD.md`
- Exit 0 = consistent, 3 = drift detected.
- Ollama calls serialized (VRAM queue), model: Bonsai-27B, `/api/chat` with `think:false`.

## Files
- Source: `~/CLEANUP/MAIN/DSI-Wiki/_Python/cli/internal_scan.py` (currently a stub)
- Wrapper: `~/.local/bin/DSI-wiki-internal-scan`
