# Stage 3 — Trade `create_agent` for `create_deep_agent`

## What changed from Stage 2
| | Stage 2 | Stage 3 |
|---|---|---|
| Constructor | `create_agent` | **`create_deep_agent`** |
| Tools you wrote | `tavily_search`, `think_tool` | unchanged |
| Tools available to the model | only the two you wrote | **+ `write_todos`, `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `task`** |

## The big idea
`create_deep_agent` is a thin wrapper around the LangChain agent loop that
*pre-registers a stack of middleware*:

```
TodoListMiddleware    → write_todos
FilesystemMiddleware  → ls / read_file / write_file / edit_file / glob / grep
SubAgentMiddleware    → task
```

Your `tools=[...]` argument is **appended** to the built-ins, not replaced.
That's why we still pass `tavily_search` and `think_tool` here.

## Why this matters for research
Two new abilities the model can now choose to use:

1. **Plan**: `write_todos` lets the model scribble a multi-step plan up
   front, then check items off as it works. The plan lives in agent state
   alongside messages.
2. **Persist findings outside the prompt**: `write_file` saves arbitrary
   markdown to a *virtual* filesystem (state-backed by default). The model
   can later `read_file` selected notes instead of carrying every search
   result in the message history. This is **context engineering** — keeping
   the prompt small while keeping the agent's working memory large.

## Try it
```bash
uv run python stages/stage_03_deep_agent.py "Research how Tavily ranks results"
```

After the run, the script prints the list of files the agent wrote (you
should see `/notes.md` and/or `/final_report.md`).

## Limitations remaining
We still do everything in **one context window**. For a multi-aspect query,
the agent's prompt grows with every search result. Stage 4 fixes this with
sub-agents.
