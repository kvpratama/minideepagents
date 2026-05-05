# Stage 03 — Dynamic schema introspection

## What's new

- `HARDCODED_SCHEMA` is gone. Replaced by `get_schema_description()`.
- We use `langchain_community.utilities.SQLDatabase`, which wraps SQLAlchemy reflection.
- `sample_rows_in_table_info=3` adds three real rows per table to the prompt — concrete examples beat abstract types.

## What to read first

1. `get_schema_description()` — three lines, but it does the heavy lifting.
2. `build_system_prompt()` — same shape as stage 02, but the schema is now generated.

## Tradeoff vs. stage 02

| | Stage 02 | Stage 03 |
|---|----------|----------|
| Schema source | Hand-written string | Live introspection |
| Stays in sync with DB? | No, must edit by hand | Yes, automatic |
| Handles new tables? | No | Yes |
| Prompt size | Small | Larger (full DDL + samples) |
| New failure mode | Wrong description | Token bloat on big DBs |

## Alternative we did not take

**Cache the schema.** Calling `get_table_info()` on every invocation hits SQLAlchemy reflection each time. For a 200-table production DB, you'd cache the string in module scope or a Redis key. We omit it here because (a) Chinook is tiny, and (b) caching is a distraction from the *aha* of "we no longer hand-write schemas".

## Aha insight

> Stage 02's prompt was a string. Stage 03's prompt is a **function of the database**. That single shift — from static text to introspected context — is the seed of every "agentic" pattern that follows. The next stage takes it further: instead of dumping the entire schema upfront, the agent will *fetch only the parts it needs*.

## Why this still has a ceiling

Try this on a hypothetical 500-table DB:

```python
prompt_tokens = len(get_schema_description()) // 4   # rough
```

You'll blow the context window. **The fix isn't a longer context window** — it's letting the model *ask* for tables one at a time. That's stage 04.

## Exercise

Look at the full `get_schema_description()` output:

```bash
uv run python -c "from stages.stage_03_schema_introspection import get_schema_description; print(get_schema_description())"
```

Count roughly how many tokens it is (~chars / 4). Imagine multiplying that by 50 tables. **That's the wall stage 04 climbs.**
