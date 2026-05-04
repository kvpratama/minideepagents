# Step 03 — Mini-clone

Same core `create_deep_agent()` signature as Step 02, re-implemented on
`langchain.agents.create_agent` + a curated stack of `AgentMiddleware`
subclasses. The whole point: *deepagents is `create_agent` + a curated
middleware stack.*

## Layout

| File | Responsibility |
|------|---------------|
| `graph.py` | `create_deep_agent()` assembles the middleware list and calls `create_agent`. |
| `backends/protocol.py` | `FilesystemBackend` ABC. |
| `backends/state.py` | `StateBackend` — files live in agent state. |
| `middleware/todos.py` | `TodosMiddleware` — `write_todos` tool, `todos` state channel. |
| `middleware/filesystem.py` | `FilesystemMiddleware` — `ls`/`read_file`/`write_file`/`edit_file` tools, `files` state channel. |
| `middleware/permissions.py` | `PermissionsMiddleware` — `wrap_tool_call` interrupts on dangerous tools. |
| `middleware/skills.py` | `SkillsMiddleware` — `load_skill` tool, system prompt suffix via `wrap_model_call`. |
| `middleware/subagents.py` | `SubagentsMiddleware` — `task` tool spawns a child `create_agent`. |

## Run the tests

```bash
cd minideepagents
uv run --group test pytest step_03_mini_clone/tests -v
```

## Try it in Studio

```bash
cd minideepagents
uv run langgraph dev
```

then open `03_mini` in the browser.
