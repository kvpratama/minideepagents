# minideepagents

A pedagogical mini-implementation of the [langchain deepagents](https://github.com/langchain-ai/deepagents/)
harness. The goal is to understand the
real harness by building a scale model of it.

## The three-step arc

1. **`step_01_walkthrough/`** — Bare LangGraph. Seven numbered files, one
   capability per file (`03b_backends` introduces the backend Protocol seam
   that later steps depend on). Build intuition incrementally.
2. **`step_02_tiny_harness/`** — Bare LangGraph. All capabilities collapsed into
   one ~400-line `create_deep_agent()` entrypoint. The synthesis artifact.
3. **`step_03_mini_clone/`** — `create_agent` + `AgentMiddleware`. Same
   entrypoint, mirrors the real deepagents directory layout. The transfer
   artifact.

## Setup

```bash
cd minideepagents
uv sync
cp .env.example .env  # then edit .env
```

Each script loads `.env` via `python-dotenv` automatically.

## Running

```bash
# Walkthrough — each file is a standalone demo
uv run python step_01_walkthrough/01_loop.py
uv run python step_01_walkthrough/02_todos.py
uv run python step_01_walkthrough/03_filesystem.py
uv run python step_01_walkthrough/03b_backends.py
uv run python step_01_walkthrough/04_subagents.py
uv run python step_01_walkthrough/05_permissions.py
uv run python step_01_walkthrough/06_skills.py

# Tiny harness
uv run python step_02_tiny_harness/example.py
```

## LangGraph Studio

All seven walkthrough graphs are exposed in `langgraph.json`. Launch the
studio and dev server with:

```bash
uv run langgraph dev
```

This opens a browser-based UI where you can pick any graph from the
dropdown, send messages, inspect state, and step through interrupts (handy
for `05_permissions`).

## Capabilities covered

Loop · Todos · Virtual filesystem · Backend protocol · Subagents · Permissions (HITL) · Skills

## Out of scope (deliberately)

The walkthrough teaches harness *concepts*, not every real-harness feature.
The following are intentionally omitted from `step_01_walkthrough/`:

- **async** — every demo is synchronous for readability
- **Persistent `Store`** — demonstrated as a backend swap in `step_02_tiny_harness/`
- **`Sandbox`** — demonstrated as a backend swap in `step_02_tiny_harness/`
- **summarization** — orthogonal middleware, easy to bolt on later
- **profiles** — model-vendor accommodations (OpenAI strict tools, etc.)
- **`patch_tool_calls`** — defensive shim that repairs malformed tool calls
- **`local_shell` / bash tool** — a tool, not a concept; trivial once the
  backend protocol is in place
- **LangSmith telemetry** — observability layer; outside the kernel
