# DSI-Wiki — Content Requirements for [CONTEXT] blocks

This is the actual fix for a recurring problem: documentation keeps losing detail during
ingest. It defines the minimum section checklist every `[CONTEXT]` block (MAIN_/SUB_/INDEP_,
any layer built from the `documentation` layer) must satisfy, plus the rule that keeps that
checklist from turning into hallucinated filler. This document is enforced in code —
the `layers.documentation.prompt` field of the active instance's JSON
(`JSONS/instances/<name>.json`, e.g. `Cain-the-elder.json`) is this checklist, sent to the
local Ollama model on every ingest.

## Why this exists

Two failure modes were happening at once, in opposite directions, and this checklist is the
single mechanism that fixes both:
1. **Detail loss** — a thin prompt ("Architecture / Configuration / Usage...") lets the
   ingest model summarize away specifics: actual file names, function names, config keys,
   port numbers. A vague section heading produces a vague paragraph.
2. **Hallucination** — the naive fix for #1 ("just ask for more detail") makes the model
   invent detail that was never in the raw source, to fill sections it has nothing for.

The fix isn't "more detail" or "less detail" — it's naming exactly which sections must
exist, forcing concrete facts (names, not summaries) where the raw source has them, and
giving an explicit, mandatory escape hatch for sections where it doesn't.

## CORE sections — always present, every [CONTEXT]

| # | Section | What goes here |
|---|---|---|
| 1 | Status | Current state: working / broken / in-progress / deprecated |
| 2 | Problem & Motivation | Why this exists, what it replaced or fixes |
| 3 | **TEC** | Technical: architecture, file/directory structure, key classes/functions **by name**, data flow, algorithms, running services/processes/ports. This is the detail-loss section — prefer naming actual files and functions over describing them abstractly |
| 4 | Configuration | Env vars, config files, ports, credential *locations* (never values) |
| 5 | Usage | How to run/use it, concrete examples |
| 6 | Known Issues & Limitations | What's broken, unfinished, or a known tradeoff |
| 7 | Missing Information | Anything the raw source didn't cover — see rule below |

If a CORE section has no supporting facts in the raw source, it is still written, with the
single line: `Not covered in raw source.` — never filled with invented specifics.

## CONDITIONAL modules — only if the raw source actually discusses them

Included as their own subsection, with the same "name specifics, don't summarize" standard
as TEC. **Omitted entirely** if the raw source never touches the domain — never added just
to fill a quota, and never given a "Not covered" placeholder (that rule is CORE-only).

| Module | When it applies |
|---|---|
| ART | Visual/art assets, style guides, asset pipeline (game/UI/content projects) |
| API | Exposed endpoints, request/response contracts |
| DATA | Database schema, data models |
| DEPLOYMENT | systemd services, ports, infra beyond basic Configuration |
| INTEGRATIONS | External services/APIs this depends on |

This list isn't closed — a project can introduce a new module name if its raw source
clearly has a recurring domain that doesn't fit the five above. The test is the same either
way: does the raw source actually discuss it, by name, more than once.

## The one hard rule

Every fact in every section — CORE or CONDITIONAL — must be traceable to something literally
present in the raw source. No invented function names, config values, endpoints, or numbers.
When in doubt, it goes in Missing Information, not in a confident-sounding sentence.
