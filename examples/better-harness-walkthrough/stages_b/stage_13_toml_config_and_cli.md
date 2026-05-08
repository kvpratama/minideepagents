# Stage 13 — TOML Config + CLI

## 1. Goal

Move experiment definition out of Python literals and into a TOML file
loaded by a small CLI (`validate` / `run` / `inspect`), so swapping
surfaces, cases, models, or iteration counts stops requiring code edits.

## 2. What changed from previous stage

- New `Experiment` dataclass that holds everything the loop needs.
- New `load_experiment(path) -> Experiment` parser:
  - `${ENV_VAR}` substitution in path-shaped values via `expand_env`.
  - Surface validation: `kind` must be valid; exactly one of
    `base_value` or `base_file` must be set.
  - Train + holdout must each include at least one case.
- New `argparse` CLI with three subcommands: `validate`, `run`,
  `inspect`.
- New `stages_b/stage_13_example.toml` worked example.

## 3. Run it

```bash
# 1. Validate the example config
uv run python stages_b/stage_13_toml_config_and_cli.py \
    validate stages_b/stage_13_example.toml

# 2. Run the optimization loop
uv run python stages_b/stage_13_toml_config_and_cli.py \
    run stages_b/stage_13_example.toml

# 3. Pretty-print a previous run's report
uv run python stages_b/stage_13_toml_config_and_cli.py \
    inspect <output_dir_printed_by_run>
```

## 4. Walkthrough

The TOML schema is the contract:

```toml
[experiment]
name = "..."
max_iterations = 2

[surfaces.prompt]
kind = "module_attr"
target = "stages_b.stage_13_toml_config_and_cli:BASE_PROMPT"
filename = "prompt.txt"
base_value = "..."          # OR base_file = "..."

[[cases]]
question = "..."
expected = "..."
split = "train"             # train | holdout | scorecard
```

`load_experiment` does three things:

1. Parses `tomllib`-loaded dict into typed dataclasses.
2. Expands `${ENV_VAR}` references and resolves relative paths against
   the config file's directory.
3. Validates structural invariants up front, so a bad config fails on
   `validate`, not deep into the optimization loop.

The CLI is one `argparse` subparser per command:

```python
{"validate": cmd_validate, "run": cmd_run, "inspect": cmd_inspect}[args.command](args)
```

## 5. Why this abstraction matters

Running the same harness against multiple experiments — different
models, different eval suites, different surface sets — is the expected
workflow. Code-as-config doesn't scale to that: every experiment becomes
a fork. With TOML, one harness binary serves N experiment files in a
directory.

## 6. Tradeoffs vs simpler approach

You could keep the experiment in Python literals. That works for the
walkthrough's one-eval-per-stage shape but breaks the moment you want
to A/B two prompts or sweep five models — each becomes a code change.

Pydantic Settings would also work, with richer validation. TOML +
plain dataclasses is intentionally minimal for the walkthrough; Tier B's
goal is to teach the *shape*, not the schema library.

## 7. LangChain mapping

None new. The inner and outer agents are unchanged.

## 8. LangGraph mapping

None new. The CLI orchestrates the same Python `for` loop from earlier
stages.

## 9. Aha insight

The harness is a *program*; the experiment is *data*. Once they're
separated, you can keep many experiments alongside one harness and
share the harness across teams without forking it.

## 10. Common mistake

Allowing both `base_value` and `base_file` on a surface, or neither.
The exclusive-one-of validation is the difference between "config
loaded fine and silently used the wrong source" and "fail fast at
validate-time with a clear error".

## 11. Simpler alternative & why it breaks later

YAML is more permissive but has anchors, merge keys, and multiple
parsers with subtly different semantics. TOML is in the standard
library (`tomllib`) since 3.11 and has exactly one shape. For
experiment configs, less is more.

## 12. Exercise

Add a second `[surfaces.calculator_guidance]` of `kind = "workspace_file"`
to `stage_13_example.toml`. Run `validate` first to confirm the schema
accepts it; then update `apply_variant` to dispatch on `kind` (mirroring
stage 09) and run `run`.

## 13. What Tier B adds here

Stage 14 introduces the `Runner` `Protocol` and a second backend
(`harbor`-style) so the loop's contract becomes "Variant in,
SplitResult out" — independent of which eval system actually executes
the cases.
