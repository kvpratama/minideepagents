# Step 4 — Delegate to a sub-agent

## What changed from Step 3
| | Step 3 | Step 4 |
|---|---|---|
| Top-level prompt | "do research yourself" | "**delegate** research; never search yourself" |
| Sub-agents | none | one (`research-agent`) |
| Built-in tool now used | — | **`task`** |

## What `subagents=[...]` actually does

`SubAgentMiddleware` reads each entry in your `subagents` list and:

1. Registers the entry's `name`, `description`, `system_prompt`, and `tools`
   internally.
2. Tells the `task` tool that the orchestrator can dispatch to it.

When the orchestrator calls `task(subagent_type="research-agent",
description="...")`, the harness:

- spawns a fresh agent loop with the sub-agent's system prompt and tools,
- runs it to completion in its **own context window**,
- returns *only* the sub-agent's final assistant message to the orchestrator.

The 5,000-token web page the sub-agent read? Never enters the orchestrator's
prompt. That's the whole point.

## Architecture

```
                 ┌──────────────────────┐
 user ─▶ orchestrator (write_todos, write_file, task)
                 └──────────┬───────────┘
                            │ task(subagent_type="research-agent", ...)
                ┌───────────┴───────────┐
                ▼                       ▼
       ┌────────────────┐      ┌────────────────┐
       │ research-agent │      │ research-agent │   ← parallel when
       │ (own context)  │      │ (own context)  │     issued in one
       │ tavily, think  │      │ tavily, think  │     orchestrator turn
       └────────────────┘      └────────────────┘
```

## Try it
```bash
uv run python steps/step4_subagent.py "Compare DuckDB vs SQLite for analytics"
```

For a comparison query like this, the orchestrator should issue **two
parallel** `task()` calls in a single turn (one per database) and merge the
results.

## Limitations remaining
The prompts here are intentionally minimal. The real `deep_research`
example has carefully tuned instructions for: planning batches, parallel
limits, iteration limits, citation consolidation, and report structure.
That's Step 5.
