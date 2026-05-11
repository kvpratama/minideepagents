# Stage 06 — Train / Holdout Split

## Goal

Introduce the split.  The outer agent only sees train failures; we measure
on both train and holdout.

## What changed from previous stage

- **`EvalCase.split`** — a `Literal["train", "holdout"]` tag on each case.
- Three cases tagged `train` (visible), two tagged `holdout` (private).
- **`run_eval(..., split=)`** — optional filter by split.
- **`SplitResult`** — structured result with `passed`, `total`, `failures`.
- **`propose()`** now receives only train failures — the outer agent never
  sees holdout questions or answers.
- The task file tells the outer agent that holdout cases exist, but not what
  they are.

## Run it

```bash
uv run python stages_a/stage_06_train_holdout_split.py
```

Expected output: baseline and proposed scores on both train and holdout.

## Walkthrough

1. **Split tags** — each `EvalCase` is tagged `"train"` or `"holdout"`.
   Train cases are what the outer agent optimizes against.  Holdout cases
   test whether improvements generalize.
2. **Filtered eval** — `run_eval(..., split="train")` only runs train
   cases.  The outer agent's failures list comes from this call.
3. **Task file** — tells the outer agent about the failing train cases
   and warns that holdout cases exist without revealing them.
4. **Dual eval** — after the proposal, we eval on *both* splits to check
   generalization.

## Why this abstraction matters

Without a holdout, the outer agent can trivially overfit by encoding train
answers directly into the prompt.  The holdout is the guard against that.
This is the same train/test discipline as in machine learning.

## Tradeoffs vs simpler approach

We could show the outer agent all cases.  That maximizes information but
invites memorization.  The split trades some information for a reliable
generalization signal.

## LangChain mapping

None new — the split is data tagging, not a framework feature.

## LangGraph mapping

None new.

## Aha insight

> This is the same train/test discipline as ML — the agent can cheat if
> you let it see everything.

## Common mistake

**Showing the outer agent the *expected answers* of train cases.**  If the
outer agent sees "Q: ... Expected: 36", it can just hardcode
`"The answer is 36"` into the prompt.  Show the question and what the inner
agent got wrong, but *not* the ground-truth answer.

## Simpler alternative & why it breaks later

You could skip the holdout and just maximize train score.  That works until
the outer agent starts encoding specific answers — then train score rises
but real-world accuracy doesn't.  Stage 07's accept rule uses
`train + holdout` combined, which only works if holdout exists.

## Exercise

Move one train case to holdout and vice versa.  Does the proposed prompt
still generalize?  If not, the prompt was overfitting to the original train
cases.

## What Tier B adds here

Stage 12 (`scorecard_split`) adds a third split that runs only on baseline
and final — separating the optimization signal from the reporting metric.
