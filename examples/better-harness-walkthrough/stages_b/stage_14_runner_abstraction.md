# Stage 14 — Runner Abstraction

## 1. Goal

Define the harness's relationship to the eval system as a `Protocol` so
the loop's only contract is "Variant in, `SplitResult` out" — and ship
two backends (`pytest`-style and `harbor`-style) behind that contract.

## 2. What changed from previous stage

- New `class Runner(Protocol)` with two methods: `collect_inventory` and
  `run_split`.
- New `PytestRunner` — binary 0/1 score per case, mirroring a
  pytest-style runner.
- New `HarborRunner` — continuous 0..1 score per case with a configurable
  `pass_threshold`, mirroring a Harbor-style runner.
- New `build_runner(experiment) -> Runner` factory that dispatches on
  `experiment.runner`.
- `SplitResult.outcomes` carries per-case `score` (float), so a binary
  runner reports 1.0 / 0.0 and a continuous runner reports anything in
  between.
- The walkthrough demo runs the same loop against both runners and
  shows the harness code never branches on which one is in use.

## 3. Run it

```bash
uv run python stages_b/stage_14_runner_abstraction.py
```

## 4. Walkthrough

The Protocol is the whole point of the stage:

```python
class Runner(Protocol):
    def collect_inventory(self, experiment: Experiment) -> list[str]: ...
    def run_split(
        self, *,
        experiment: Experiment,
        variant: Variant,
        split: str,
    ) -> SplitResult: ...
```

Each backend implements the two methods, taking different paths to the
same `SplitResult`:

```python
class PytestRunner:
    def run_split(self, *, experiment, variant, split):
        # binary score per case
        ...

class HarborRunner:
    def run_split(self, *, experiment, variant, split):
        threshold = experiment.runner_config.get("pass_threshold", 1.0)
        # continuous score, threshold to pass/fail
        ...
```

The factory routes on `experiment.runner`:

```python
def build_runner(experiment):
    if experiment.runner == "pytest":
        return PytestRunner()
    if experiment.runner == "harbor":
        return HarborRunner()
    raise ValueError(f"unknown runner {experiment.runner!r}")
```

The hill-climbing loop only ever calls `runner.run_split(...)` — it has
no idea (and no need to know) which backend executed the cases.

## 5. Why this abstraction matters

Different orgs evaluate agents in different ways. Some have pytest
suites with `--junitxml`. Others have Harbor or Inspect with continuous
rewards. Some use a custom in-house framework. The harness loop should
not care — its job is to propose, score, and keep. As long as
"propose" produces a `Variant` and "score" produces a `SplitResult`,
the loop works against anything.

## 6. Tradeoffs vs simpler approach

You could hardcode the call into `inner_agent(question)` directly,
which is what stages 09–13 did. That's fine for one runner. The
moment you want a second backend, every call site has to learn about
it. A Protocol confines the knowledge to one factory and one
implementation per backend.

## 7. LangChain mapping

None new. The inner agent is unchanged — it's just invoked by whichever
runner the experiment selects.

## 8. LangGraph mapping

None new. If you wanted parallel runners (e.g. run pytest cases in
parallel), this is where LangGraph's `Send` could help. The walkthrough
keeps it sequential.

## 9. Aha insight

The loop's contract is just `Variant in, SplitResult out`. Anything
that satisfies that contract is a valid runner. Once that's true, you
can write a `MockRunner` for tests, a `RemoteRunner` that posts to a
queue, or a `CompositeRunner` that ensembles two backends — without
touching the loop.

## 10. Common mistake

Letting runner-specific config bleed into the loop. If the loop reads
`experiment.runner_config["pass_threshold"]`, it's tied to the harbor
backend and will misbehave on pytest. Keep the config encapsulated
inside the runner that uses it.

## 11. Simpler alternative & why it breaks later

A subclass hierarchy works (`class HarborRunner(Runner):`), but
`Protocol` is structural — any class with the right methods satisfies
it, including third-party ones you can't subclass. For pluggable
backends across packages, structural typing is the better fit.

## 12. Exercise

Add a `MockRunner` that always returns `passed == total` for any
variant. Use it in a unit test that asserts the loop accepts every
candidate. (This is the test scaffolding the original
`examples/better-harness/` uses for its own tests.)

## 13. What Tier B adds here

Tier B ends here. Tier C — see the design spec — pushes the runner
across a process boundary: pytest under a real subprocess with a
`BETTER_HARNESS_VARIANT_FILE` env var handoff, a pytest plugin loaded
via `PYTEST_PLUGINS`, structured outcomes parsed from JUnit XML, the
outer Deep Agent run under a separate `uv` project, and transient-error
retry/backoff.
