# Stage 08 — Multi-Surface

## Goal

Demonstrate the `Surface` abstraction was worth building — add a second
surface (`CALCULATOR_GUIDANCE`) and let the outer agent edit either or both
in one iteration.

## What changed from previous stage

- **`CALCULATOR_GUIDANCE`** — a module-level string read by the calculator
  tool at call time.  This is the second surface.
- **`Surface.filename`** — new field mapping a surface to its workspace
  filename (e.g. `"calculator_guidance.txt"`).
- **`SURFACES`** now has two entries: `prompt` and `calculator_guidance`.
- **`make_calculator_with_guidance()`** — builds a calculator tool whose
  description includes the current `CALCULATOR_GUIDANCE` text.
- **`propose()`** writes *all* surfaces to the workspace and reads them all
  back.
- **`IterationRecord.changed_surfaces`** — tracks which surfaces the outer
  agent actually edited.

## Run it

```bash
uv run python stages_a/stage_08_multi_surface.py
```

Expected output: the outer agent edits both surfaces in at least one
iteration on a typical run.

## Walkthrough

1. **Two surfaces** — `prompt.txt` and `calculator_guidance.txt` both
   appear under `/current/` in the proposer workspace.
2. **Task file** — lists both editable surfaces so the outer agent knows
   what it can change.
3. **`make_calculator_with_guidance()`** — rebuilds the tool on each
   `build_inner_agent()` call so the tool description reflects the
   currently patched `CALCULATOR_GUIDANCE`.
4. **`propose()`** — iterates over `surfaces` to write files and read them
   back.  Adding a third surface would be one new `Surface` entry and zero
   changes to `propose()`.
5. **`changed_surfaces`** — after reading back, we compare each surface's
   value to the current variant to see what the outer agent actually
   touched.

## Why this abstraction matters

This is the moment all the dataclass scaffolding from stage 03 pays off.
If `Surface`/`Variant` were plain dicts, adding a second editable thing
would touch every function that reads or writes surfaces.  With them, it's
one new entry in `SURFACES`.

## Tradeoffs vs simpler approach

We could have two separate `propose_prompt()` and `propose_guidance()`
functions.  That works for two surfaces but doesn't scale to ten.  The
surface abstraction makes `propose()` surface-count-agnostic.

## LangChain mapping

None new.

## LangGraph mapping

None new.

## Aha insight

> The surface abstraction is what made adding a second editable surface
> a one-line change instead of a refactor.

## Common mistake

Forgetting to rebuild the tool when `CALCULATOR_GUIDANCE` is patched.
Because the tool description is set at construction time, you must call
`make_calculator_with_guidance()` *after* patching — just like `BASE_PROMPT`
must be patched *before* building the agent.

## Simpler alternative & why it breaks later

You could hardcode both file paths in `propose()` instead of iterating over
surfaces.  That works today but means every new surface requires editing
the proposer, the patcher, the evaluator, and the report.  The surface
list keeps changes to one place.

## Exercise

Add a third surface: a `RESPONSE_FORMAT` string that instructs the inner
agent how to format its final answer (e.g. `"Return only the number."`).
See how the outer agent uses all three surfaces.

## What Tier B adds here

Stage 11 (`proposer_workspace`) enriches the workspace with
`surface_manifest.json`, `/train_cases/*.md`, and `/history/` — giving the
outer agent structured context about each surface and prior iterations.
