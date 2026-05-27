# Mapping: walkthrough stages → original [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki)

This file ties every architectural move in the walkthrough back to
the concrete file (and the relevant region) in the production
example. After reading the stages, this is the cheat sheet for
navigating the real code.

All paths are relative to [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki).

## High-level correspondence

| Stage | Concept | Lives in |
|------:|---------|----------|
| 01 | `create_deep_agent` invocation | `helpers._run_agent_mode` |
| 02 | `FilesystemBackend` rooted at a workspace dir | `helpers._run_agent_mode`, workspace_backend |
| 03 | Evidence / wiki split + `FilesystemPermission` policy | `helpers._permissions` (apply), `helpers._ensure_scaffold` |
| 04 | Runner-managed `log.md` + `wiki/index.md` | `log.append_log_entry`, `index.refresh_index`, deny rules in `helpers._permissions` |
| 05 | Mode dispatch + per-mode permission profiles | `helpers.parse_config` (mode), `helpers._permissions` vs `helpers._review_permissions` |
| 06 | Two-phase query + `FILING_DECISION` marker | `query.build_query_prompt`, `query.parse_query_decision`, `query.run_query_workspace` |
| 07 | Two-phase ingest with operator confirmation | `ingest.build_ingest_review_prompt`, `ingest.build_ingest_apply_prompt`, `ingest.confirm_ingest_apply`, `ingest.run_ingest_workspace` |
| 08 | Single-pass lint reconciliation | `lint.build_lint_prompt`, `lint.run_lint_workspace` |
| 09 | Pull → mutate → push lifecycle | `helpers._run_pull_mode`, `init.run_init`, `helpers._validate_text_only_directory`, `helpers._ensure_no_symlinks` |
| 10 | `CompositeBackend` (sandbox + local routes) | `helpers._run_agent_mode`, `helpers._create_langsmith_sandbox_backend` |

## File-by-file decomposition

### `runner.py`
A 27-line entrypoint. Maps to: README + stage 05's "the runner is
the boundary".

### `models.py`
* `RunnerConfig` is the parsed shape of stage 05's `--mode` dispatch
  plus the per-mode arguments that stages 06–08 add.
* `CliDeps` is the dependency-injection seam used by stage 07's
  `ask_user` hook and stage 09's `run_langsmith_cli` /
  `tempdir_factory`.
* `RunResult` is the return shape of every mode.

### `helpers.py`
The center of gravity. Roughly:

| Lines (approx) | Role | Stage |
|----------------|------|-------|
| `parse_config`, `_build_parser`, `_normalize_repo_and_owner` | CLI surface | 05, 09 |
| `_ensure_scaffold`, `_agents_md` | Workspace layout | 03, 04, 09 |
| `_permissions`, `_review_permissions` | Permission profiles | 03, 05, 07 |
| `_safe_write_text`, `_ensure_no_symlinks`, `_validate_text_only_directory` | Push-side safety | 09 |
| `_run_langsmith_cli`, `_hub_identifier`, `_hub_cli_repo_arg` | Hub CLI wrapper | 09 |
| `_create_langsmith_sandbox_backend` | Sandbox lifecycle | 10 |
| `_run_agent_mode`, `_run_agent_apply_mode`, `_run_agent_review_mode` | Backend composition + invoke | 02, 03, 10 |
| `_append_log_entry`, `_refresh_index` (delegations) | Runner-managed artifacts | 04 |
| `_run_pull_mode`, `run` | Lifecycle wrapper | 09 |

### `init.py`
Stage 09 init path. The flag-resolution helpers
(`_resolve_internal_source_flag_from_help`) exist because the hub
CLI's flag names have churned across releases — same pressure that
motivated shelling out instead of importing the SDK.

### `ingest.py`
Stage 07. Notable shape:
* `IngestResult.should_push` is `True` even when the operator
  declines apply, so the `ingest.apply | outcome=canceled` log
  entry still gets pushed. The audit trail must be complete.
* `_ingest_source_hint` collapses a source list into a parseable
  metadata value — a stage 04 concern (log lines need to be
  greppable).

### `query.py`
Stage 06. `_QUERY_DECISION_PATTERN` and `_QUERY_REASON_PATTERN` are
the regexes that justify the marker-over-JSON tradeoff explained
in stage 06's markdown.

### `lint.py`
Stage 08. Note the prompt mentions "external verification" with a
fallback to marking gaps as unresolved — the lint mode is the
one place external web access is contemplated, because
reconciliation is the only mode where the wiki itself isn't enough.

### `log.py`
Stage 04, the timeline side. `_LOG_HEADER_MAX_LEN` and
`_LOG_SUMMARY_MAX_LEN` are why long agent answers never blow up
the log: header detail and summary both get clamped to fixed
budgets so the file stays scannable.

### `index.py`
Stage 04, the catalog side. `_INDEX_CATEGORY_ORDER` and
`_INDEX_DIRECTORY_CATEGORIES` are the conventional sectioning —
`/wiki/query/` automatically becomes the "Queries" section
because stage 06 picked `/wiki/query/<slug>.md` as its filing
target. Naming and directory conventions are doing real work.

### `tests/`
The `CliDeps`-shaped dependency injection in the production code
exists so the test suite can drive the entire `pull → mutate →
push → log → index` lifecycle without touching real LangSmith.
That mirrors what stages 07 / 09 demonstrate with the `ask`
lambda and `FakeHub`.

## Final shape

Re-reading [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki)`helpers.py` `_run_agent_mode` and
`_run_pull_mode` after the walkthrough, the sequence should read
top-to-bottom as **stage 10 → stage 09 → stage 05 → stages 06–08
→ stage 04**, sitting on top of **stages 01–03**. Nothing in the
file is accidental; every line is a response to a pressure that
showed up in an earlier shape.
