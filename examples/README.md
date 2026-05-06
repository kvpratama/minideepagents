# Examples

Independent, runnable mini-projects that use `create_deep_agent()` (and
related harness patterns) to demonstrate specific end-to-end agent setups.
Each example mirrors or rebuilds an upstream
[Deep Agents example](https://github.com/langchain-ai/deepagents/tree/main/examples)
in a staged, walkthrough style.

## Available examples

| Example | Stages | What you build | Key concepts |
|---------|--------|----------------|--------------|
| [`deep_research_walkthrough/`](deep_research_walkthrough/) | 5 | A multi-agent deep-research assistant | `create_agent` → `create_deep_agent`, think tool, subagents, orchestrator prompts |
| [`text-to-sql-agent-walkthrough/`](text-to-sql-agent-walkthrough/) | 9 | A text-to-SQL agent over the Chinook database | Raw SQL → LLM one-shot → ReAct loop → `create_agent` → `create_deep_agent`, AGENTS.md, skills, filesystem backend |

## How the walkthroughs work

Every walkthrough follows the same pattern:

1. **Staged files** — each `stages/stage_NN_<name>.py` is one runnable graph
   that adds exactly one new concept on top of the previous stage.
2. **Paired explainers** — each `.py` has a matching `.md` that covers what
   changed, what to read, the tradeoff, and an exercise.
3. **Studio-ready** — each example ships its own `langgraph.json` so you can
   `uv run langgraph dev` inside the directory and inspect any stage in
   LangGraph Studio.
4. **CLI-ready** — every stage can also be run directly from the terminal.

See each example's own `README.md` for setup, credentials, and the exact
commands to run a stage.

## Adding a new example

1. Create a new directory under `examples/`.
2. Give it its own `pyproject.toml`, `langgraph.json`, and `.env.example`.
3. Organise stages as `stages/stage_NN_<name>.py` + `.md` pairs.
4. Add an entry to the table above.
