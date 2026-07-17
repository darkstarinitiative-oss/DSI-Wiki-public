"""LLM ingest prompt'ları. Her katman için bir fonksiyon."""

PROJECT_DOC_TEMPLATE = """# {name}

> <One sentence: what it does, what problem it solves>

## Status
- Phase: <phase>
- Board: <board slug>
- Last updated: <date>

## Problem & Motivation
<What problem this solves. Why the previous approach was insufficient.>

## Architecture
<Components, responsibilities, flow. ASCII diagram if applicable.>

## File & Directory Structure
| File | Responsibility |
|---|---|

## Configuration
<Environment variables, config files, requirements>

## Usage
```bash
<Example commands>
```

## Known Issues & Limitations
<Active bugs, missing features, workarounds>

## Changelog (append-only)
| Date | Change |
|---|---|
"""


def is_project_topic(raw_content: str) -> bool:
    for line in raw_content.splitlines()[:10]:
        if line.lower().startswith("tags:") and "project" in line.lower():
            return True
    return False


def doc_prompt(base_name: str, raw_content: str, prev_doc: str) -> str:
    if is_project_topic(raw_content):
        return f"""You are a technical documentation editor. Using the template below, produce a structured project document in English.
Required sections (in order): Status, Problem & Motivation, Architecture, File & Directory Structure, Configuration, Usage, Known Issues & Limitations, Changelog.

***!!!DO NOT WRITE ANYTHING THAT CANNOT BE VERIFIED FROM THE RAW RECORDS!!!***

Template:
{PROJECT_DOC_TEMPLATE.format(name=base_name)}

Existing document (most recent section):
{prev_doc[-4000:] if len(prev_doc) > 4000 else prev_doc or "(none)"}

New raw source ({base_name}):
{raw_content[:2000]}

Output: only the updated full document, in English."""
    else:
        return f"""You are a technical documentation editor. Update the existing document with the new information (append-only, add UPDATE notes for contradictions). Write in English, detailed and reasoned.

***!!!DO NOT WRITE ANYTHING THAT CANNOT BE VERIFIED FROM THE RAW RECORDS!!!***

EXISTING (recent):
{prev_doc[-6000:] if len(prev_doc) > 6000 else prev_doc or "(none)"}

NEW RAW ({base_name}):
{raw_content[:8000]}

Output: only the updated full document."""


def llm_prompt(doc_output: str) -> str:
    return f"""Condense this document for LLM context windows. Keep all facts, relationships, status. Bullet points ok. Same language as input.

***!!!DO NOT WRITE ANYTHING THAT CANNOT BE VERIFIED FROM THE RAW RECORDS!!!***

DOCUMENT:
{doc_output}

Output: condensed text only."""


def minified_prompt(llm_output: str) -> str:
    return f"""Optimally compress the following into the minimum information needed to use this service from the outside. Plan for minimum token cost — every word must earn its place. Current status only, no history. Same language as input.

TEXT:
{llm_output}

Output: single compressed paragraph only."""
