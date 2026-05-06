# Text-to-SQL Walkthrough

A 9-stage rebuild of the [`text-to-sql-agent`](https://github.com/langchain-ai/deepagents/blob/main/examples/text-to-sql-agent) example, designed as a hands-on learning path. Each stage is **one runnable Python file** paired with **one Markdown explainer**. Every stage is wired into LangGraph Studio so you can experiment, trace, and inspect — and every stage is also runnable from the CLI.

## What you will build

You will start from raw `sqlite3` and end at the full Deep Agent (with `AGENTS.md`, skills, planning, and a filesystem backend). Each stage adds **exactly one new concept** on top of the previous file so the diff is small and the "aha" is obvious.

```diagram
   PRIMITIVES PHASE                AGENT PHASE             DEEP-AGENT PHASE
╭────────────────────────╮     ╭──────────────────╮     ╭──────────────────╮
│ 01 raw_sql             │     │ 04 react_loop    │     │ 06 deep_agent    │
│ 02 llm_one_shot        │ ──▶ │ 05 create_agent  │ ──▶ │ 07 agents_md     │
│ 03 schema_introspection│     │      + toolkit   │     │ 08 skills        │
╰────────────────────────╯     ╰──────────────────╯     │ 09 filesystem    │
                                                        ╰──────────────────╯
```

## Stage map

| # | File | What's new | Aha insight |
|---|------|-----------|-------------|
| 01 | [`stage_01_raw_sql.py`](stages/stage_01_raw_sql.py) | `sqlite3` + Chinook, hardcoded query | SQL is the bedrock; the agent only generates these strings. |
| 02 | [`stage_02_llm_one_shot.py`](stages/stage_02_llm_one_shot.py) | One LLM call: question + hardcoded schema → SQL → execute | An LLM can write SQL if it sees the schema. |
| 03 | [`stage_03_schema_introspection.py`](stages/stage_03_schema_introspection.py) | `SQLDatabase.get_table_info()` to feed schema dynamically | This is what the toolkit does for you under the hood. |
| 04 | [`stage_04_react_loop.py`](stages/stage_04_react_loop.py) | Hand-rolled ReAct: `list_tables` / `get_schema` / `run_query` tools + tool-calling loop | An "agent" is just a loop where the LLM picks tools. |
| 05 | [`stage_05_create_agent_toolkit.py`](stages/stage_05_create_agent_toolkit.py) | Replace loop with `create_agent` + `SQLDatabaseToolkit` | The framework removes boilerplate; mental model is unchanged. |
| 06 | [`stage_06_deep_agent_minimal.py`](stages/stage_06_deep_agent_minimal.py) | Swap `create_agent` → `create_deep_agent` (defaults only) | You inherit planning + filesystem + subagents for free. |
| 07 | [`stage_07_agents_md.py`](stages/stage_07_agents_md.py) | Add `AGENTS.md` (identity + safety rules, always loaded) | This is the "system prompt" upgraded into a versioned doc. |
| 08 | [`stage_08_skills.py`](stages/stage_08_skills.py) | Add `skills/query-writing` + `skills/schema-exploration` | Progressive disclosure keeps context lean. |
| 09 | [`stage_09_filesystem_backend.py`](stages/stage_09_filesystem_backend.py) | Add `FilesystemBackend` for scratch persistence | Multi-step analytical queries can stash intermediate results. |

Each `stage_NN_*.md` file next to the Python source covers: **what changed**, **what to read first**, **the tradeoff vs. the previous stage**, **an alternative we did not take**, and **one exercise**.

## Setup (one time)

```bash
# 1. Install dependencies
uv sync

# 2. Download the Chinook SQLite database into the repo root
uv run bash scripts/download_chinook.sh

# 3. Set your provider API key (optional for stage 01)
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY (or switch MODEL to your preferred provider)
```

### Swapping the LLM provider

All stages from 02 onwards build their model through [`stages/config.py`](stages/config.py) (Pydantic Settings). Change one line in `.env` to switch vendors — no code edits needed:

```bash
# Default
MODEL=anthropic:claude-sonnet-4-5-20250929

# Try OpenAI instead
MODEL=openai:gpt-4o

# Try Google
MODEL=google_genai:gemini-2.0-flash

# Try a self-hosted Ollama / vLLM endpoint
MODEL=openai:llama3.1:70b
BASE_URL=http://localhost:11434/v1
API_KEY=ollama
```

## Running a stage

### From the CLI

Every stage accepts a natural-language question (stage 01 ignores it and runs a fixed demo query):

```bash
uv run python stages/stage_01_raw_sql.py "any question"
uv run python stages/stage_05_create_agent_toolkit.py "Which 5 artists have the most albums?"
uv run python stages/stage_09_filesystem_backend.py "Which employee generated the most revenue by country?"
```

Or use direct `uv run` commands:

```bash
uv run python stages/stage_01_raw_sql.py "any question"
uv run python stages/stage_09_filesystem_backend.py "Which employee generated the most revenue by country?"
```

### From LangGraph Studio

Every stage is registered in [`langgraph.json`](langgraph.json) as its own graph. Launch the studio:

```bash
uv run langgraph dev
```

Then open the Studio URL and pick the graph for the stage you want to inspect. You'll see each tool call, each LLM response, and (for stages 04+) the full ReAct trace. **Compare the trace of stage 04 with stage 05** — same behavior, very different observability.

## How to use this walkthrough

1. Open `stages/stage_01_raw_sql.md` and read it first.
2. Read `stages/stage_01_raw_sql.py` end-to-end.
3. Run the stage from CLI **and** from Studio. Look at the trace.
4. Do the exercise at the end of the `.md` file (optional but recommended).
5. Move to stage 02. The `.md` will tell you exactly what changed.

> **Tip:** Every stage from 02 onward is a literal evolution of the previous file. Use `diff stages/stage_NN.py stages/stage_MM.py` to see the minimal delta — this is the fastest way to internalize what each new concept buys you.
