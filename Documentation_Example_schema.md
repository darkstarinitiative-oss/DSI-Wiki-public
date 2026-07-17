# DSI-Wiki — Key Documentation Template (Placeholder Reference)

This file is a schema example, not real content. `{...}` fields are filled in during ingest.
For the key structure, see Wiki-Master-Plan.md → "Key Yapısı".

---

## MAIN_ Format

```
Key: MAIN_{topic_slug}
Title: {Main Title}

[CONTEXT]
{General content of the main topic — status, problem & motivation, architecture, usage}

[SUB_REFS]
- SUB_{topic_slug}_{sub_title_1_slug}
- SUB_{topic_slug}_{sub_title_2_slug}

[CHANGE_LOG]  (optional)
- {date}: {user-facing change}

[DEVLOG]  (optional)
- {date}: {decision made / mistake made} — {resolution}
```

---

## SUB_ Format

```
Key: SUB_{topic_slug}_{sub_title_slug}
Title: {Sub Title}

[MAIN]  (mandatory)
MAIN_{topic_slug}

[CONTEXT]
{Content specific to this sub-title}
```

---

## INDEP_ Format

```
Key: INDEP_{topic_slug}
Title: {Independent Topic Name}

[CONTEXT]
{Content — not tied to any MAIN/SUB; only reachable via search or explicit reference}
```

---

## OBSOLETE Note

No separate format is defined. The prefix of an existing `MAIN_` or `SUB_` key is swapped for
`OBSOLETE_` (`MAIN_{x}` → `OBSOLETE_{x}`). The original type is inferred from the presence or
absence of the `[MAIN]` block: if it originated from a SUB, the `[MAIN]` block stays; if it
originated from a MAIN, there never was one.
