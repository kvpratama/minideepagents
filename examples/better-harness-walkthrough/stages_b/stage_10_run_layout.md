# Stage 10 — Run Layout

## 1. Goal

Introduce `RunLayout` — a class that owns the on-disk artifact tree for one
experiment run, so a crashed iteration leaves enough behind to debug.

## 2. What changed from previous stage

- New `RunLayout` class with `variants_dir`, `iteration_dir(i)`,
  `write_manifest`, `write_variant`, `write_decision`, `write_report`.
- New `IterationDecision` and `RunReport` dataclasses; both serialize to
  JSON and Markdown.
- `Variant` carries `changed_surfaces`; `build_variant(label, values)`
  computes it by diffing against base values.
- The loop calls `layout.write_*` at the end of every iteration — not
  only at the end of the run.
- `report.json` and `report.md` are written when the loop completes.

## 3. Run it

```bash
uv run python stages_b/stage_10_run_layout.py
```

## 4. Walkthrough

`RunLayout` is just a path policy with a few writers:

```python
class RunLayout:
    def variant_path(self, label: str) -> Path:
        return self.variants_dir / f"{label}.json"

    def iteration_dir(self, iteration: int) -> Path:
        return self.root / "iterations" / f"{iteration:03d}"

    def write_decision(self, decision: IterationDecision) -> None:
        d = self.iteration_dir(decision.iteration)
        d.mkdir(parents=True, exist_ok=True)
        (d / "decision.json").write_text(...)
        (d / "decision.md").write_text(...)
```

The loop pays a tiny tax — a few `layout.write_*` calls per iteration —
in exchange for a fully inspectable run tree:

```text
<root>/
  manifest.json
  variants/
    baseline.json
    iter-000.json
  iterations/
    000/decision.json
    000/decision.md
  report.json
  report.md
```

## 5. Why this abstraction matters

Durability. A run that crashes in iteration 7 must leave behind enough to
post-mortem. In-memory state alone can't do that. Once the layout exists,
you can also resume runs (skip iterations whose `decision.json` already
exists) and diff two runs against each other.

## 6. Tradeoffs vs simpler approach

You could `print(...)` everything to stdout and call it a day. That works
for the demo but loses every byte the moment the process exits. The
layout adds maybe twenty lines and turns the run into something you can
`grep`, `jq`, and inspect days later.

## 7. LangChain mapping

None new. The inner and outer agents are unchanged.

## 8. LangGraph mapping

None new. The loop is still a Python `for` loop. LangGraph would buy us
checkpointing if the loop itself needed to resume — it doesn't here
because the harness owns the persistence.

## 9. Aha insight

Every interesting agent system eventually grows into a filesystem layout.
Design that layout deliberately — paths, file names, and serialization
formats — and you've built half the debugger before any bug happens.

## 10. Common mistake

Writing artifacts only at the end of the run. If the process dies in
iteration 5 of 10, you have nothing to inspect. Per-iteration writes
are the point.

## 11. Simpler alternative & why it breaks later

A single `pickle.dump(...)` at the end is one line and fails the moment
you change a dataclass shape. JSON + Markdown per iteration is more code
but resilient to schema drift and human-readable.

## 12. Exercise

Add a `--resume` flag to `main()` that skips iterations whose
`decision.json` already exists, treating the most recent accepted
variant as `current`.

## 13. What Tier B adds here

Stage 11 turns the proposer's tempdir into a richly materialized
workspace (`/task.md`, `/train_cases/`, `/history/`,
`surface_manifest.json`) so the outer agent has structured context to
work from.
