# DSI Info API Standard

A contract, not an implementation detail: **any DSI project exposes some URL that returns JSON
in this exact shape.** Where that URL lives (a dedicated `/api/info`, a function bolted onto an
existing router, a path under `/http`, whatever) is entirely up to the project — the only
requirement is that an external caller who knows the URL gets back JSON matching this schema.
That's what makes it possible to point one generic widget/viewer at *any* DSI project's info
endpoint and render it the same way, without project-specific code.

## Schema

```json
{
  "service": "dsi-wiki-ingest",
  "version": "0.1.0",
  "status": "warning",
  "status_note": "Consolidation slow tonight, otherwise nominal.",
  "services": [
    { "name": "DSI-Wiki Ingest Daemon", "status": "ok", "last_heartbeat": "2026-08-05T00:25:47Z" },
    { "name": "DSI-Wiki Gateway",       "status": "ok", "last_heartbeat": null }
  ],
  "feed": [
    { "ts": "2026-08-05T00:22:47Z", "icon": "warning", "title": "Consolidation retry", "note": "MAIN_DSI-WIKI llm/minified/brief hit 300s timeout, retried and succeeded." },
    { "ts": "2026-08-04T23:30:53Z", "icon": "ok", "title": "MAIN_SYSTEM ingested", "note": "documentation + consolidation, 273s total." }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `service` | string | yes | Logical service/project name. |
| `version` | string | yes | Whatever versioning the project uses (SemVer recommended, see `INDEP_GIT_RULES`). |
| `status` | `"ok"` \| `"warning"` \| `"error"` | yes | One overall status. **What drives this value is entirely project-decided** — there's no cross-project rule for what counts as "warning" vs "error". |
| `status_note` | string | yes (may be `""`) | Free text. **Content is project-decided.** |
| `services[]` | array | yes (may be `[]`) | One entry per logical component the project wants to expose. |
| `services[].name` | string | yes | Human-readable component name. |
| `services[].status` | `"ok"` \| `"warning"` \| `"error"` \| `"unknown"` | yes | |
| `services[].last_heartbeat` | ISO-8601 timestamp \| `null` | yes (key always present) | Last time this component's own loop/cycle actually ran. `null` for request-driven components with no loop of their own (e.g. a pure HTTP gateway). |
| `feed[]` | array | yes (may be `[]`) | Most recent events, **newest first, capped at 10 entries.** **Which events get recorded is entirely project-decided** — this standard only fixes the shape of each entry, not what's newsworthy. |
| `feed[].ts` | ISO-8601 timestamp | yes | |
| `feed[].icon` | `"ok"` \| `"warning"` \| `"error"` \| `"info"` | yes | Fixed vocabulary — this is what lets a generic widget render an icon without project-specific mapping logic. |
| `feed[].title` | string | yes | Short. |
| `feed[].note` | string | yes (may be `""`) | Longer, optional detail. |

All fields are required keys (use `null`/`""`/`[]` rather than omitting a key) — a generic
renderer built against this standard shouldn't need per-field existence checks.

## Why this shape

- `status`/`status_note` exist because "is this project healthy" is a judgment call every project
  makes differently — the standard doesn't try to define health, just gives it one fixed place to
  live so a dashboard doesn't need per-project logic to find it.
- `services[]` with `last_heartbeat` (not just a live "check right now" like the IETF
  `draft-inadarei-api-health-check` health-check-response-format) matters specifically for
  poll/loop-based daemons (see DSI-Wiki's own Ingest Daemon) — "did the loop run recently" is a
  meaningfully different question from "is the process alive."
- `feed[]` gives a project a place to surface recent noteworthy events (retries, slow runs,
  errors) without needing a full logging/observability stack — a rolling window of 10 is enough
  for a glance-able status widget, not a replacement for real logs.

## DSI-Wiki's own implementation

DSI-Wiki's ingest daemon (`CODE/ingest/DSI-Wiki-Ingest-Service-Class.py`) already tracked
per-topic ingest outcomes into `STATUS.json` (`_last_ingest`, added alongside the `/http/dashboard`
health widget) — extended with a capped `feed` list (`_record_feed_entry()`, newest first, oldest
dropped past 10) and a `services[]` block (Ingest Daemon's heartbeat = `last_poll_ts`; Gateway has
no loop of its own, so its `last_heartbeat` is `null` and its `status` is inferred at request time
from whether it's answering at all). Served at `GET /api/info` (`CODE/gateway/api_app.py`) — a
new endpoint, chosen instead of reshaping the existing `/api/status` passthrough so nothing that
already reads `/api/status` breaks.

## Generic info-viewer test page

`/http/info-viewer` (`CODE/ui/DSI-Wiki-UI-Server.py`) takes a `?url=` query param pointing at
*any* URL implementing this standard (not just DSI-Wiki's own `/api/info`) and renders the
`status`/`services[]`/`feed[]` generically — this is the standard's own conformance-testing tool,
usable against future DSI-* projects' info endpoints too.
