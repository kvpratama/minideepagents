# Step C — Walkthrough

Each numbered file adds **one** capability on top of the previous file. They
are intentionally self-contained: you can read `04_subagents.py` without
having read `03_filesystem.py` because the relevant code is duplicated
forward. The point is that you can sit with one file at a time.

| File                  | Adds                              |
|-----------------------|-----------------------------------|
| `01_loop.py`          | model ↔ tools loop (the core)     |
| `02_todos.py`         | `write_todos` planning tool       |
| `03_filesystem.py`    | virtual fs in state               |
| `03b_backends.py`     | `Backend` protocol for storage    |
| `04_subagents.py`     | `task` tool spawns child graph    |
| `05_permissions.py`   | `interrupt()` before dangerous    |
| `06_skills.py`        | `load_skill` reads `SKILL.md`     |

Run any file directly: `uv run python step_01_walkthrough/03_filesystem.py`.
Each has a `__main__` demo that prints what the agent did.

**LangGraph Studio**: All graphs are exposed in `langgraph.json`. Run `uv run langgraph dev`
to launch the studio UI, which lets you interact with any graph and step through
interrupts (especially useful for `05_permissions`).
