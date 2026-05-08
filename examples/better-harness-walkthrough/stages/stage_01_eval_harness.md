# Stage 01 — Eval Harness

## Goal

Introduce evals as the measurement substrate everything else depends on.

## What changed from previous stage

Everything — this is the starting point:

- `EvalCase` dataclass holding a question and expected answer.
- Five math word problems with known numeric answers.
- A scripted `inner_agent()` stub that always returns `"42"`.
- `run_eval()` that feeds cases through the agent and counts pass/fail.
- `normalize()` that extracts the last number from a string for comparison.

## Run it

```bash
uv run python stages/stage_01_eval_harness.py
```

Expected output: `Passed: 0/5` (the stub always returns "42").

## Walkthrough

1. **`EvalCase`** — a frozen pair of `(question, expected)`.  Nothing more.
2. **`CASES`** — five short word problems.  Every answer is a number, which
   lets `normalize()` do reliable extraction.
3. **`inner_agent()`** — deliberately useless.  It exists so we have
   *something* to score before stage 02 introduces a real LLM.
4. **`run_eval()`** — the loop: call the agent, normalize both sides,
   compare.  Returns `(passed, total)`.
5. **`normalize()`** — strips whitespace, extracts the last number, drops
   trailing `.0`.  This is the grading contract every later stage reuses.

## Why this abstraction matters

If you can't measure quality, you can't improve it.  The eval harness gives
us a single number — pass rate — that every subsequent stage uses as its
objective.  Without it, "the agent got better" is just vibes.

## Tradeoffs vs simpler approach

We could just eyeball the agent's output.  That breaks the moment you want
to compare two variants automatically, which is the entire point of the
outer loop (stage 07).

## LangChain mapping

None — this is plain Python.

## LangGraph mapping

None — there is no graph.  Explicit non-need is part of the lesson: you
don't need a framework to define "did the agent answer correctly?"

## Aha insight

> An agent's quality is just a number on a deterministic test set.

## Common mistake

Writing eval cases with ambiguous expected answers (e.g. "about 36" vs
"36").  The `normalize()` function extracts the last number from both sides,
which sidesteps most formatting issues — but the *expected* value should
still be a clean number.

## Simpler alternative & why it breaks later

You could skip the `EvalCase` dataclass and use raw tuples.  That works
until stage 06 adds a `split` field — then you'd need to refactor every
case definition.

## Exercise

Change `inner_agent()` to return the last number from the question string
(a crude heuristic).  How many cases does it pass now?

## What Tier B adds here

Stage 10 (`run_layout`) wraps this eval output in a durable on-disk
artifact tree so crashed runs can be post-mortemed.
