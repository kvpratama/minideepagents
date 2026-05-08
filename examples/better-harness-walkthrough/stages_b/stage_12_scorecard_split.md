# Stage 12 — Scorecard Split

## 1. Goal

Introduce an optional third split — `scorecard` — that the outer loop
*never* sees during optimization, so the final number you report is not
the same number you optimized against.

## 2. What changed from previous stage

- `EvalCase.split` widened to `Literal["train", "holdout", "scorecard"]`.
- New module-level `OPTIMIZATION_SPLITS = {"train", "holdout"}`; the
  loop only ever runs those two during iterations.
- After the loop ends, `run_eval(..., split="scorecard")` runs once on
  the baseline and once on the final variant, and the result is part of
  the report only.
- Added two scorecard cases (rectangle area, square minus cube) so the
  metric is meaningful but isolated.

## 3. Run it

```bash
uv run python stages_b/stage_12_scorecard_split.py
```

## 4. Walkthrough

The split set defines the contract:

```python
Split = Literal["train", "holdout", "scorecard"]
OPTIMIZATION_SPLITS: set[Split] = {"train", "holdout"}
```

Inside the loop, the candidate is scored only on `train` and `holdout`:

```python
cand_train = run_eval(candidate, split="train")
cand_holdout = run_eval(candidate, split="holdout")
accepted = cand_train.passed + cand_holdout.passed > current_combined
```

After the loop, scorecard is scored exactly twice:

```python
base_score = run_eval(baseline, split="scorecard")
final_score = run_eval(final, split="scorecard")
```

That's the entire change. The discipline is in *not* sneaking scorecard
into the accept rule.

## 5. Why this abstraction matters

If you optimize against a metric, you can no longer trust it as a clean
report number — the optimizer's job is to maximize it, by any means
including memorization of the cases it sees. Holdout protects against
memorizing train; scorecard protects against memorizing train + holdout.

## 6. Tradeoffs vs simpler approach

You could just declare "we trust the holdout number." That works until
the outer agent's edits start touching the holdout failure modes
specifically — at which point you've turned holdout into a second train
set with no replacement. Scorecard is the replacement, kept clean by
construction.

## 7. LangChain mapping

None new.

## 8. LangGraph mapping

None new — the loop is still a plain Python `for`.

## 9. Aha insight

The metric you optimize and the metric you report should not be the
same metric. Naming the third split makes that discipline visible in
the type signature, not just in someone's head.

## 10. Common mistake

Adding scorecard as a fallback: "if train + holdout don't differ, break
the tie with scorecard." The moment the loop reads scorecard, you've
contaminated it. The split is value-only because contact is the
contamination.

## 11. Simpler alternative & why it breaks later

For a one-off run, `train + holdout` is enough. The moment you re-run
the harness on the same eval suite many times — say, sweeping models or
trying different proposer prompts — the holdout number starts drifting
upward without genuinely getting better. Scorecard lets you notice that.

## 12. Exercise

Add a second scorecard case that the inner agent reliably gets *wrong*.
Run the stage twice and see whether the final scorecard number actually
moves with the train + holdout improvements, or whether it's stuck.

## 13. What Tier B adds here

Stage 13 lifts the experiment definition out of Python and into a TOML
file with a `validate` / `run` / `inspect` CLI, so swapping the eval
suite, model, or surfaces stops requiring code edits.
