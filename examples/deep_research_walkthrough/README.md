# Deep Research — Walkthrough

A step-by-step rebuild of [`deep_research`](https://github.com/langchain-ai/deepagents/tree/main/examples/deep_research),
broken into five small runnable graphs so you can feel exactly what each
piece of the Deep Agents harness does.

## How it's organised

```
deep_research_walkthrough/
├── config.py              # Pydantic Settings + get_model() helper
├── langgraph.json         # registers all 5 graphs for `langgraph dev`
└── steps/
    ├── step1_basic_agent.py        + .md   # bare LangChain create_agent
    ├── step2_thinking_tool.py      + .md   # + think_tool, system prompt
    ├── step3_deep_agent.py         + .md   # → create_deep_agent
    ├── step4_subagent.py           + .md   # + research-agent sub-agent
    └── step5_full_orchestrator.py  + .md   # full real-example prompts
```

Each `stepN_*.py` exports a module-level `agent` graph **and** has a CLI
entry point. Each `.md` next to it is the lesson for that step.

## Setup

```bash
cd examples/deep_research_walkthrough
uv sync
cp .env.example .env       # then fill in API_KEY and TAVILY_API_KEY
```

## Run a single step

```bash
uv run python steps/step1_basic_agent.py "What is LangGraph?"
uv run python steps/step3_deep_agent.py  "Research how Tavily ranks results"
uv run python steps/step5_full_orchestrator.py "Compare DuckDB vs SQLite"
```

## Trace any step in Studio

```bash
langgraph dev
```

Studio's graph dropdown lists `step1_basic_agent` through
`step5_full_orchestrator`. Pick any one to run and inspect.

## Reading order

1. Run step 1 once. Read [`step1_basic_agent.md`](steps/step1_basic_agent.md).
2. Run step 2. Read [`step2_thinking_tool.md`](steps/step2_thinking_tool.md).
3. Continue through step 5.

Each lesson opens with a "What changed from step N-1" table so you only
focus on the new piece.

## How this maps to the real example

After step 5, diff `steps/step5_full_orchestrator.py` against
[`deep_research`](https://github.com/langchain-ai/deepagents/tree/main/examples/deep_research) example. The differences are:

- `model` is built from `.env` via `config.py` instead of being hardcoded.
- The three prompt blocks are vendored inline (vs imported from
  `research_agent/prompts.py`).

Architecturally they're the same agent.
