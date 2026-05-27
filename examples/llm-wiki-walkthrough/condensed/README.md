# LLM Wiki Architecture Walkthrough — Condensed Cut

> This is the **condensed cut** of the walkthrough, paired with the
> 10-stage "archaeology" cut one level up at
> [`../README.md`](../README.md). It assumes the same LangChain /
> LangGraph fluency as the outer cut and shares its Mentor-Mode
> framing, but compresses the 10 stages into 4 broader chapters and
> adds explicit, stage-by-stage discussion of when each pressure
> makes LangGraph preferable to a script-first loop. The outer
> version is the canonical reference and stays in lockstep with
> [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki).

This repository is an incremental, step-by-step reconstruction of the [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki) repository in `langchain-ai/deepagents`.

Rather than just presenting the final codebase as a static product, this project frames the architecture as a historical engineering journey. Each stage represents a natural evolution step, showing what breaks at scale, why naive fixes fail, and how the abstractions in the final repository resolve those specific pains.

## Evolutionary Journey Overview

The system evolves through 4 core stages:

1. **[Stage 1: The Naive Script (Zero-Orchestration Agent)](stages/stage_01_naive_writer.md)**
   - **Pain Point**: No isolation, context explosion, fragile filesystem boundaries.
   - **Resolution**: Let's build a basic model interaction loop.
2. **[Stage 2: Sandbox Isolation and Failsafe Permissions](stages/stage_02_sandbox_permissions.md)**
   - **Pain Point**: LLM reasoning drift leading to data corruption/deletion; lack of index scaling.
   - **Resolution**: Introduce virtualized backends, file-level permissions, and an automated catalog (`wiki/index.md`).
3. **[Stage 3: Two-Phase Ingestion & Temporal Audit Logs](stages/stage_03_auditable_review.md)**
   - **Pain Point**: Destructive operations without approval; sequential runs lacking historical memory.
   - **Resolution**: Introduce read-only `review` vs. write `apply` phases, with host-managed append-only ledger (`log.md`).
4. **[Stage 4: Self-Filing Queries and Self-Healing Linting](stages/stage_04_query_lint_orchestration.md)**
   - **Pain Point**: RAG search is too slow/expensive; duplicated answers; stale and orphaned page drift.
   - **Resolution**: Self-filing query routing (`query.py`) and single-pass self-healing linting (`lint.py`), mapping the script-first orchestration to Graph-based architectures (LangGraph).

## Structure of the Walkthrough

* `/shared/`: Common structures (e.g., dataclasses, formatting) shared across stages.
* `/stages/`: Python files containing runnable stages and Markdown files explaining the engineering context, trade-offs, and LangChain/LangGraph mapping.
* `/final_compare/`: Analysis comparing the fully evolved Stage 4 code to the final [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki) repository.

## Running the Stages

To run any of the stages, you can execute them directly:
```bash
# Setup environment (from root of monorepo)
uv sync --project examples/llm-wiki-walkthrough

# Run Stage 1 Ingest
uv run python stages/stage_01_naive_writer.py --mode ingest --repo my-wiki --source ./notes/speech.md
```
Each stage requires a valid `LANGSMITH_API_KEY` for its agent execution tasks.
