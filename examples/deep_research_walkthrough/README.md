# Deep Research — Walkthrough

A step-by-step rebuild of [`deep_research`](https://github.com/langchain-ai/deepagents/tree/main/examples/deep_research),
broken into five small runnable graphs so you can feel exactly what each
piece of the Deep Agents harness does.

## How it's organised

```
deep_research_walkthrough/
├── config.py              # Pydantic Settings + get_model() helper
├── langgraph.json         # registers all 5 graphs for `langgraph dev`
└── stages/
    ├── stage_01_basic_agent.py        + .md   # bare LangChain create_agent
    ├── stage_02_thinking_tool.py      + .md   # + think_tool, system prompt
    ├── stage_03_deep_agent.py         + .md   # → create_deep_agent
    ├── stage_04_subagent.py           + .md   # + research-agent sub-agent
    └── stage_05_full_orchestrator.py  + .md   # full real-example prompts
```

Each `stage_NN_*.py` exports a module-level `agent` graph **and** has a CLI
entry point. Each `.md` next to it is the lesson for that stage.

## Setup

```bash
cd examples/deep_research_walkthrough
uv sync
cp .env.example .env       # then fill in API_KEY and TAVILY_API_KEY
```

## Run a single stage

```bash
uv run python stages/stage_01_basic_agent.py "What is LangGraph?"
uv run python stages/stage_03_deep_agent.py  "Research how Tavily ranks results"
uv run python stages/stage_05_full_orchestrator.py "Compare DuckDB vs SQLite"
```

## Trace any stage in Studio

```bash
uv run langgraph dev
```

Studio's graph dropdown lists `stage_01_basic_agent` through
`stage_05_full_orchestrator`. Pick any one to run and inspect.

## Reading order

1. Run stage 1 once. Read [`stage_01_basic_agent.md`](stages/stage_01_basic_agent.md).
2. Run stage 2. Read [`stage_02_thinking_tool.md`](stages/stage_02_thinking_tool.md).
3. Continue through stage 5.

Each lesson opens with a "What changed from stage N-1" table so you only
focus on the new piece.

## How this maps to the real example

After stage 5, diff `stages/stage_05_full_orchestrator.py` against
[`deep_research`](https://github.com/langchain-ai/deepagents/tree/main/examples/deep_research) example. The differences are:

- `model` is built from `.env` via `config.py` instead of being hardcoded.
- The three prompt blocks are vendored inline (vs imported from
  `research_agent/prompts.py`).

Architecturally they're the same agent.
