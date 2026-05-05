# Stage 04 — Hand-rolled ReAct loop

## What's new

We stop pre-loading the schema into the prompt. Instead the LLM **fetches** it:

- Three `@tool`-decorated functions: `list_tables`, `get_schema`, `run_query`.
- An `agent_node` that binds those tools to the LLM and lets it choose.
- A `tools` node that executes the chosen tool (using LangGraph's prebuilt `ToolNode`).
- A conditional edge from `agent` that loops back through `tools` until the model stops calling tools.

The graph now has a real shape:

```diagram
   ╭───────╮     ╭─────────╮ tool calls? ╭───────╮
   │ START │────▶│  agent  │────────────▶│ tools │
   ╰───────╯     ╰────┬────╯             ╰───┬───╯
                      │ ▲                    │
       no tool calls  │ ╰────────────────────╯
                      ▼      (always)
                    ╭─────╮
                    │ END │
                    ╰─────╯
```

## What to read first

1. The three `@tool` functions — note how `run_query` enforces SELECT-only by inspection.
2. `agent_node` — `bind_tools(TOOLS)` is what makes the LLM aware of the tool schema.
3. `should_continue` — the entire control flow boils down to "did the model emit a tool call?".
4. The `builder.add_conditional_edges(...)` line — this is the loop.

## Tradeoff vs. stage 03

| | Stage 03 | Stage 04 |
|---|----------|----------|
| Schema delivery | Whole schema in prompt | Fetched per-table on demand |
| LLM calls per question | 1 | 2–6 (typical) |
| Scales to 500-table DB? | No | Yes |
| Self-correcting on bad SQL? | No (single shot) | Yes (sees error, retries) |
| Code complexity | One node | Loop + tool node + routing |

## Alternative we did not take

**`langchain.agents.create_agent`** would shrink this whole file to ~10 lines. We hand-rolled the loop because the entire pedagogical point of stage 04 is to *see* the loop. Stage 05 then earns the right to hide it.

## Aha insights

> An "agent" is a `while not done: pick_tool(); execute_tool()` loop with an LLM as the picker. There is nothing more to it. Every fancy framework — LangChain, AutoGen, CrewAI — is decorating this loop.

> The ReAct trace IS the agent's reasoning. Open Studio, run a complex question, and watch the model: list → schema(Customer) → schema(Invoice) → run_query → final answer. **You can read its mind.** That's the gift of agentic systems over one-shot calls.

## Failure to provoke (try this!)

Ask `"Which employee generated the most revenue by country?"`. Expect 4–6 tool calls. Now compare to stage 03 where the same question must succeed in a single shot — it often will, but only because Chinook is small.

## Exercise

Add a fourth tool `query_checker(sql: str) -> str` that uses the LLM to spot common SQL mistakes before execution. Update `SYSTEM_PROMPT` to require a check before `run_query`. Run a complex question and observe the new node in the trace.

> *Hint:* this tool already exists in `SQLDatabaseToolkit` — you'll meet it in stage 05.
