# DSI-WIKI — stat info + dashboard plan (2026-08-07)

Status: DSI-WIKI is the **reference implementation** for both halves of this plan — the other
four projects' plans point back here. This file documents the target state (already live) so
it's a stable reference, and lists the one real open gap.

## Stat info content (`GET /api/info`, DSI Info API Standard)

Already correct, already live. The pattern every other project should copy:

- The daemon (`CODE/ingest/DSI-Wiki-Ingest-Service-Class.py`) only persists **content** it
  alone can know — per-topic ingest outcomes into `DATA/events/ingest_events.json`
  (`_write_events()`, atomic tmp+rename, once per completed ingest). It does **not** try to
  self-report its own up/down state.
- `TOOLS/write_ingest_status.py` (host cron, every minute, deliberately outside any container)
  judges actual liveness via `docker inspect DSI-WIKI.docker.ingest`, merges that verdict with
  `ingest_events.json`'s content, writes `DATA/status/STATUS.json` (atomic tmp+rename).
- `services[]`: `DSI-Wiki Ingest Daemon` (external, from STATUS.json) + `DSI-Wiki Gateway`
  (self-reported live at request time — legitimate, since the request only exists because the
  process is currently answering).
- `feed[]`: ingest outcomes (ok/warning/error per topic, from `ingest_events.json`).
- Gateway (`CODE/gateway/api_app.py`) serves `GET /api/info` by reading `STATUS.json` off disk,
  not recomputing anything live.

**Open gap**: `DSI-WIKI-Ingest-Queue` (raw/ drop-dir depth) and the nightly fact-check
(`dsi-wiki-factcheck.timer`) aren't in `services[]` or `feed[]` yet — both are real, already
externally observable (Beholder's own `watchlist.json` tracks the queue depth and the timer
separately, duplicating what `/api/info` itself could report). Low priority.

## Dashboard content (`GET /dashboard`, `CODE/ui/DSI-Wiki-UI-Server.py`)

Already correct, already live — the pattern:

- Reads its own `GET /api/info` (not a second, separate code path) and renders it generically.
- `/http/info-viewer?url=<any DSI /api/info URL>` is the standard's own conformance-testing
  tool — **this already exists and already works for any project implementing the standard**.
  Every other project's dashboard plan below should consider whether it even needs its own
  bespoke render, or whether pointing people at `info-viewer?url=` is enough for v1.
- Topics widget: delete/fact-check actions, processed via host cron
  (`TOOLS/process_topic_ops.py`) reading `WIKI_RAW_DIR/_ops/*.json` — same "outside the
  container, judged externally" discipline as the status write.

No changes planned here. This file exists so the other four have something concrete to copy.
