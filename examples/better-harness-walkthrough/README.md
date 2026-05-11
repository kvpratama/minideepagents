# better-harness Walkthrough

An incremental, runnable learning project that rebuilds
[`examples/better-harness/`](https://github.com/langchain-ai/deepagents/tree/main/examples/better-harness) from scratch.  Each stage
introduces exactly one new concept on top of the previous one.

## What is better-harness?

A research pattern: an **outer Deep Agent** edits the harness of an **inner
agent**, guided by a hill-climbing loop on train/holdout eval splits.

```
╭──────────────╮   evals    ╭──────────────╮  edits   ╭───────────────╮
│ Inner Agent  │──────────▶│ Outer Agent  │─────────▶│  Surface Files│
│ (target)     │  failures  │ (Deep Agent) │ proposal │ (prompt/tools)│
╰──────────────╯            ╰──────────────╯          ╰───────┬───────╯
        ▲                                                     │
        │            patch & re-eval (keep if improved)       │
        ╰─────────────────────────────────────────────────────╯
```

## Prerequisites

1. **Python 3.12+** and **[uv](https://docs.astral.sh/uv/)**.
2. Copy `.env.example` to `.env` and fill in your API key:
   ```bash
   cp .env.example .env
   # Edit .env — uncomment and set ANTHROPIC_API_KEY (or OPENAI_API_KEY)
   ```
3. Install dependencies:
   ```bash
   uv sync
   ```

## How to run

Every stage is a standalone script.  Run from the walkthrough root:

```bash
# Tier A — stages 01-08 (under stages_a/)
uv run python stages_a/stage_01_eval_harness.py        # no LLM needed
uv run python stages_a/stage_02_inner_agent.py
uv run python stages_a/stage_03_surface.py
uv run python stages_a/stage_04_patching.py
uv run python stages_a/stage_05_outer_agent.py
uv run python stages_a/stage_06_train_holdout_split.py
uv run python stages_a/stage_07_outer_loop.py
uv run python stages_a/stage_08_multi_surface.py

# Tier B — stages 09-14 (under stages_b/)
uv run python stages_b/stage_09_workspace_file_surface.py
uv run python stages_b/stage_10_run_layout.py
uv run python stages_b/stage_11_proposer_workspace.py
uv run python stages_b/stage_12_scorecard_split.py
uv run python stages_b/stage_13_toml_config_and_cli.py validate stages_b/stage_13_example.toml
uv run python stages_b/stage_14_runner_abstraction.py
```

## Stage map

### Tier A — conceptual rebuild

| # | Name | New concept | LLM? |
|---|------|-------------|------|
| 01 | `eval_harness` | What an eval is: cases → runner → pass/fail | No |
| 02 | `inner_agent` | Real LangChain agent with calculator tool | Yes |
| 03 | `surface` | `Surface` + `Variant` dataclasses | Yes |
| 04 | `patching` | Module-attr monkey-patching | Yes |
| 05 | `outer_agent` | Deep Agent editing a virtual file | Yes |
| 06 | `train_holdout_split` | Train vs holdout eval discipline | Yes |
| 07 | `outer_loop` | Hill-climbing optimization loop | Yes |
| 08 | `multi_surface` | Two editable surfaces (prompt + tool guidance) | Yes |

### Tier B — faithful single-machine

| # | Name | New concept | LLM? |
|---|------|-------------|------|
| 09 | `workspace_file_surface` | Second surface kind: real file swapped via context manager | Yes |
| 10 | `run_layout` | Durable on-disk artifact tree per run | Yes |
| 11 | `proposer_workspace` | Rich materialized context for the outer agent | Yes |
| 12 | `scorecard_split` | Optional third split, never seen by the loop | Yes |
| 13 | `toml_config_and_cli` | TOML loader + `argparse` CLI | Yes |
| 14 | `runner_abstraction` | `Runner` `Protocol` + pytest- and harbor-style backends | Yes |

## Switching models

Edit `.env` to change the model — no code edits needed:

```env
# Anthropic (default)
MODEL=anthropic:claude-sonnet-4-5-20250929

# OpenAI
MODEL=openai:gpt-4o

# Google
MODEL=google_genai:gemini-2.0-flash
```
