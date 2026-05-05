# Stage 05 — `create_agent` + `SQLDatabaseToolkit`

## What's new

Two replacements happen in the same stage because they belong together:

1. The hand-rolled ReAct graph → `langchain.agents.create_agent(...)`.
2. The hand-rolled tools → `SQLDatabaseToolkit(db=db, llm=llm).get_tools()`.

That's it. The file shrinks from ~110 lines to ~50.

## What to read first

1. `build_graph()` — the entire wiring is three lines.
2. `SQLDatabaseToolkit(...)` — note we pass `llm` because one of its tools (`sql_db_query_checker`) is itself LLM-powered.
3. `SYSTEM_PROMPT` — the workflow now references the *toolkit's* tool names: `sql_db_list_tables`, `sql_db_schema`, `sql_db_query_checker`, `sql_db_query`.

## Tradeoff vs. stage 04

| | Stage 04 | Stage 05 |
|---|----------|----------|
| Lines of code | ~110 | ~50 |
| Loop visible? | Yes (you wrote it) | No (hidden in framework) |
| `query_checker` tool? | No | Yes (free) |
| Customizable routing? | Trivial — edit the graph | Requires middleware |
| Dependency surface | langgraph + langchain-core | langchain (high-level) |

## Why `create_agent` (not something else)

`create_agent` is the entry point Deep Agents extends — stage 06 swaps `create_agent` → `create_deep_agent` and *nothing else changes*. Picking it here makes stage 06 a one-line jump rather than a rewrite.

## Aha insights

> Stage 04 → 05 is a **pure refactor**. Same loop, same tools, same behavior. The framework's job is to make the boring code disappear so the interesting code (your prompt, your tools) is what's left on the page.

> `SQLDatabaseToolkit` is a museum piece — it shows what a "production" version of stage 04's three tools looks like: input validation, query checking, error formatting, retry friendliness. Read its source if you're curious; it's short.

## Studio diff exercise

Open Studio. Run the same question against `stage_04_react_loop` and `stage_05_create_agent_toolkit`. The traces should be **structurally identical**: list → schema → checker(?) → query → final answer. **The framework is the trace, written in code.**

## Exercise

Replace `system_prompt=SYSTEM_PROMPT` with `system_prompt=None`. Run a few questions. The agent still mostly works because the tool descriptions (look at each tool's docstring) carry enough guidance. Now you understand why prompt engineering and tool design are the same activity.
