# llm-wiki walkthrough — architectural archaeology

This is a **reconstruction** of [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki), not a tutorial.

The original is a ~500-line script-first Deep Agents app: a CLI that drives an
agent through `init`/`ingest`/`query`/`lint` modes against a persistent wiki
that is round-tripped through Context Hub. The final architecture uses a
`CompositeBackend` that splits compute (sandbox) from canonical files (local
FS), a runner-managed `log.md` timeline and `wiki/index.md` catalog, a
two-phase ingest with operator approval, a `FILING_DECISION` parse trick for
the query mode, and a strict filesystem-permission policy.

None of that is obvious from the final code. Everything in it is a response
to a concrete failure of a simpler design. The point of this walkthrough is
to **rebuild those failures** in order and watch each abstraction become
inevitable.

## Reading order

Each stage is one Python file plus a Markdown explanation. The Python file
is independently runnable and minimally diffs from the previous stage. The
Markdown explains the operational pressure, why naive fixes don't work, and
the tradeoffs of the abstraction introduced.

| # | Stage | New abstraction | Pressure that forced it |
|---|-------|----------------|-------------------------|
| 01 | [single shot](stages/stage_01_single_shot.md) | `create_deep_agent` + `StateBackend` | none — baseline |
| 02 | [persistent files](stages/stage_02_persistent_files.md) | `FilesystemBackend(root_dir=…)` | answers vanish between runs |
| 03 | [evidence / wiki split + permissions](stages/stage_03_raw_vs_wiki.md) | `FilesystemPermission(deny /raw/**)` | agent rewrites its own evidence |
| 04 | [runner-managed log + index](stages/stage_04_runner_artifacts.md) | derived `log.md` and `wiki/index.md` written outside the agent | agent corrupts its own audit trail; index drifts |
| 05 | [mode split: ingest vs query](stages/stage_05_mode_split.md) | `mode`-keyed prompt + permission profiles | one prompt can't do both writing and reading safely |
| 06 | [query filing decision](stages/stage_06_query_filing.md) | `FILING_DECISION:` marker + two-phase analyze→file | every query either floods the wiki or wastes durable answers |
| 07 | [ingest review / apply](stages/stage_07_ingest_review.md) | review-only permission profile + operator confirmation | destructive ingest with no preview |
| 08 | [lint reconciliation](stages/stage_08_lint.md) | single-pass `lint.apply` with `log` recency context | wiki accretes contradictions and orphans |
| 09 | [Context Hub pull / push](stages/stage_09_hub_sync.md) | tempdir workspace + `langsmith hub pull/push` wrapper | wiki is trapped on one machine |
| 10 | [sandbox + composite backend](stages/stage_10_composite_backend.md) | `CompositeBackend({default: sandbox, routes: {/raw/, /wiki/, /log.md, /AGENTS.md → local}})` | agent compute conflicts with durable file shape |

## Directory layout

```
llm-wiki-walkthrough/
├── README.md                  ← you are here
├── stages/
│   ├── stage_01_single_shot.py / .md
│   ├── …
│   └── stage_10_composite_backend.py / .md
├── shared/
│   ├── model.py               ← lazy model loader / fake fallback
│   └── sample_source.md       ← fixture used by ingest stages
├── final_compare/
│   └── mapping.md             ← which file in the original repo each stage
│                                corresponds to, line-anchored
└── condensed/                 ← parallel 4-chapter retelling with extra
                                 narrative + framework commentary (see below)
```

## How to actually run a stage

Every stage is a single file. From the repo root:

```bash
uv sync --project examples/llm-wiki-walkthrough  # reuse the example env
uv run --project examples/llm-wiki-walkthrough \
   python examples/llm-wiki-walkthrough/stages/stage_03_raw_vs_wiki.py
```

Stages that would normally invoke the model use a tiny canned fake by default
so the architectural failure (permission denial, log corruption, etc.) is
demonstrable without API keys. Set `WIKI_WALKTHROUGH_MODEL=anthropic:claude-haiku-4-5`
(plus the matching key) to run the real agent.

## Companion: the condensed cut

[`condensed/`](condensed/README.md) is a parallel retelling of the
same architecture at lower resolution. It assumes the same
LangChain / LangGraph fluency as this cut, and (like this cut) ends
each stage with a "Mentor Mode" block. What it adds on top:

* collapses the 10 stages into 4 broader chapters,
* explicitly discusses, stage by stage, *when* each pressure makes
  LangGraph preferable to a script-first loop (the outer cut takes
  that judgment as given),
* includes a Mermaid flowchart of the final mode dispatch in stage 04.

Use the condensed cut when you want the story arc in four moves;
use this one when you want the line-anchored archaeology.

## What this walkthrough is *not*

* Not a redesign. Names, abstraction boundaries, prompt shapes, log format,
  and permission policy match the original repo. When the original makes a
  deliberately ugly tradeoff (e.g. `FILING_DECISION:` markers parsed by
  regex instead of structured output), this walkthrough preserves it and
  explains why the cleaner alternative loses.
* Not a tutorial of `create_deep_agent`. Readers are assumed fluent in
  LangChain, LangGraph, and agentic orchestration.
* Not a sequence of isolated demos. Stage `N` is the working code of stage
  `N-1` plus one minimal change.

The goal is that after stage 10 the original [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki) reads like an obvious sequence of forced moves.
