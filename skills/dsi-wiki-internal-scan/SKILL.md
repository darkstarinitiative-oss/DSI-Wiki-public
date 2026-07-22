---
name: dsi-wiki-internal-scan
description: Compare documentation vs minified layers of DSI-Wiki topics with a local LLM (Bonsai) to detect factual drift. Serialized Ollama calls, report file per day, exit code signals drift.
---

# DSI-Wiki Internal Consistency Scanner

## Usage

```
DSI-wiki-internal-scan --topic INDEP_LLM_RULES
DSI-wiki-internal-scan --instance Cain-the-elder --all
```

- Compares factual claims (model names, paths, ports, commands, statuses) between the
  documentation and minified layers of each topic.
- Report output (append mode): `~/CLEANUP/MAIN/DSI-Wiki/reports/internal-scan-YYYYMMDD.md`
- Stdout: `<topic>: <verdict first 80 chars>` per topic.
- Exit codes: 0 = consistent, 2 = bad args/instance, 3 = drift detected, 4 = Ollama unreachable.
- Ollama calls serialized (one at a time, VRAM queue), model: Bonsai-27B,
  `POST /api/chat` with `stream:false, think:false`, timeout 600s.

## Files
- Source: `~/CLEANUP/MAIN/DSI-Wiki/_Python/cli/internal_scan.py`
- Wrapper: `~/.local/bin/DSI-wiki-internal-scan`

## Status
Rebuilt 2026-07-23 (original destroyed by task t_8adcc404; rebuild finished by hand after
worker tasks t_59f50950/t_9717bb00 stalled). Verified live: `--topic INDEP_LLM_RULES`
returned a DRIFT verdict, rc=3, report written.
