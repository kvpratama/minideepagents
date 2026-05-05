# Stage 06 — Minimal Deep Agent

## What's new

```diff
- from langchain.agents import create_agent
+ from deepagents import create_deep_agent
...
- return create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)
+ return create_deep_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)
```

That's the entire diff against stage 05. But the resulting agent now has access to:

| Middleware | What it adds |
|---|---|
| `TodoListMiddleware` | The `write_todos` tool — the model can keep a checklist |
| `FilesystemMiddleware` | `ls` / `read_file` / `write_file` / `edit_file` / `glob` / `grep` |
| `SubAgentMiddleware` | The `task` tool — spawn a focused subagent for a sub-question |
| `SummarizationMiddleware` | Auto-compact the message history when it gets long |

## What to read first

1. The `build_graph()` function — note how short the diff actually is.
2. `SYSTEM_PROMPT` — we now hint at planning.
3. Open Studio and look at the **Tools** panel for this graph. Count them. You added zero, you got many.

## Tradeoff vs. stage 05

| | Stage 05 | Stage 06 |
|---|----------|----------|
| Tools available | 4 (SQL only) | 4 + ~10 built-ins |
| Planning tool? | No | Yes (`write_todos`) |
| Scratch storage? | No | Yes (in-memory filesystem) |
| Subagent spawning? | No | Yes (`task` tool) |
| Recursion budget needed | ~25 | ~50 (more steps possible) |
| Token cost per question | Low | Higher (longer system prompt, more tools described) |

## Alternative we did not take

**Add only the middleware you need** by calling `create_agent` and passing `middleware=[TodoListMiddleware(), FilesystemMiddleware(...)]` explicitly. This is the "à la carte" route. It's strictly more flexible — but if you find yourself wanting *most* of the middleware, `create_deep_agent` is the curated bundle, just like `SQLDatabaseToolkit` was for SQL tools in stage 05.

## Aha insights

> Deep Agents is to `create_agent` what `SQLDatabaseToolkit` was to hand-rolled `@tool` functions: a curated bundle. The pattern repeats at every level of the stack — primitives → bundles. Recognising the pattern is half the framework.

> The biggest cost upgrade in stage 06 isn't compute, it's **prompt tokens**. Every tool description is in the system prompt every turn. Test with a simple question — the answer might be cheaper in stage 05. Use Deep Agents when you need the planning + filesystem; don't pay for them otherwise.

## Studio observation

Pop open the trace for `"Which 5 artists have the most albums?"`. Now do the same for `"Which employee generated the most revenue from each country, and write the result to revenue_by_employee.csv"`. The first question barely uses the new middleware. The second one uses `write_todos`, then `write_file`. That's the upgrade earning its keep.

## Exercise

Run the same simple question (`"How many customers are from Canada?"`) against stages 05 and 06. Note the difference in **system prompt size** (look at the trace's first LLM call). Then ask: *for which class of question is stage 06 worth the extra tokens?*
