# Stage 07 — Outer Loop

## Goal

The hill-climbing loop.  Iterate N times.  Keep a candidate iff
`train.passed + holdout.passed` strictly improves.

## What changed from previous stage

- **`MAX_ITERATIONS = 3`** — how many proposals to try.
- **`IterationRecord`** — captures each iteration's outcome.
- **`loop(cases, surfaces)`** — the core loop: propose → patch → eval on
  both splits → accept iff combined improves → restore if rejected.
- **`print_report()`** — summary of all iterations.
- **`run_eval()`** no longer prints per-case output (keeps the loop quiet;
  the report is the output).

## Run it

```bash
uv run python stages_a/stage_07_outer_loop.py
```

Expected output: a multi-iteration run with at least one accepted candidate
on a typical run.  The final combined pass count should be `>=` the
baseline's.

## Walkthrough

1. **Baseline eval** — run train and holdout before the loop starts.  This
   sets the bar.
2. **Loop body** — for each iteration:
   - `propose()` gives the outer agent the current prompt and the train
     failures.  It returns a new prompt.
   - Patch the candidate, eval on both splits.
   - **Accept rule:** `cand_combined > current_combined`.  Strictly greater
     — ties are rejected.
   - If accepted, update `current`.  If rejected, restore the old variant.
3. **Iteration records** — each iteration is logged to `records`.
4. **Report** — summarizes baseline, final, and per-iteration decisions.

## Why this abstraction matters

The loop is the control structure that turns "one-shot proposal" into
"iterative improvement."  It's the simplest possible optimization loop:
hill-climb with no branching, no parallelism, no memory beyond the current
best.

## Tradeoffs vs simpler approach

We could just run `propose()` once (stage 05).  That works if the first
proposal is good enough.  The loop gives the outer agent multiple chances
and a feedback signal — if the first attempt doesn't improve, it tries
again with updated failure information.

## LangChain mapping

None new — the loop is orchestration around agents we already have.

## LangGraph mapping

The loop *could* be a `StateGraph` with nodes `propose`, `eval_candidate`,
`decide`, and a conditional edge back to `propose` until the iteration
budget is hit.  We don't do that here because the loop is linear,
single-strategy, and has no branching policy beyond "improved? keep :
discard."

**Rule of thumb:** switch to LangGraph the moment you want parallel
candidates, HITL approval, or branching strategies.

## Aha insight

> The outer-loop pattern is just `while (eval improves): edit; re-eval`.
> That's it.  Everything else is bookkeeping.

## Common mistake

**Keeping a candidate when only train improved** (overfit classic).  If
train goes from 2/3 to 3/3 but holdout drops from 2/2 to 0/2, the
combined is the same (4 → 3) — we reject.  Using combined train+holdout is
the safer rule because it catches cases where the outer agent overfits to
the visible cases.

## Simpler alternative & why it breaks later

You could accept any candidate that improves *train* score, ignoring
holdout.  That hill-climbs faster but can converge to a prompt that
memorizes train answers.  The combined rule is slower but converges to
genuinely better prompts.

## Exercise

Change `MAX_ITERATIONS` to 5 and run again.  Does the extra budget help?
At some point the outer agent has no failures left to fix — observe that
iterations after that point get rejected (no strict improvement).

## What Tier B adds here

Stage 10 (`run_layout`) writes every iteration's decision to disk as
`decision.json` + `decision.md`, so long runs can be post-mortemed even
if they crash mid-way.
