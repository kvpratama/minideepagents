# Stage 07 — ingest review / apply

## Stage summary

* **Current limitation:** ingest still writes immediately. A bad
  ingest pass can mangle many canonical pages in one go.
* **Naive fix that fails:** "just be careful with the prompt." The
  blast radius doesn't get smaller; observability does, slightly.
* **Right fix:** opt-in two-phase ingest. A read-only review phase
  produces a plan; an operator approves; a write phase applies it
  with the plan in-context.
* **New abstraction:** review-only permission profile + operator
  confirmation gate + plan-in-context for the apply phase.

## What changed vs. stage 06

* `review_permissions()` mirrors stage 06's read-only profile but
  is now used for *ingest* planning.
* `confirm()` is the interactive gate. The original repo injects
  this via the `CliDeps.ask_user` dependency so tests can stub it.
* `ingest_apply_prompt(..., review_summary)` feeds the approved
  plan back into the apply pass so the model doesn't replan.

The two-phase shape itself is structurally identical to stage 06's
query flow. That's not coincidence — the same operational pressure
(don't perform destructive work without preview) produces the same
shape. The difference is who confirms: a regex marker for query
(the model decides), an interactive prompt for ingest (the human
decides).

## Failure demonstration

Run the script. Two ingest passes happen:

1. `review=False` — direct apply, matches stage 05 behavior.
2. `review=True` — review pass runs first, plan is shown, the
   stub `ask` returns `"y"`, then apply runs.

Flip the `ask` lambda to return `"n"` and the apply phase
short-circuits. No writes, no permission escalation. The original
repo additionally appends an `ingest.apply | outcome=canceled`
entry to `log.md` (stage 04 machinery) so the audit trail still
records the *attempted* ingest. We're omitting that line here for
brevity but the hook is the same `append_log_entry()` from stage
04.

## Why simpler fixes fail later

* **Dry-run flag that prints diffs.** Diffs of what? The agent
  hasn't decided what to write until it writes. To preview, you
  need a planning step — which is exactly the review phase.
* **Snapshot + roll back on operator dislike.** The runner can
  `git stash` the wiki and restore on rejection. Plausible, but
  you've now done the work, paid the tokens, *and* polluted the
  audit trail. Plan-first is cheaper.
* **Approve in a UI after the fact.** Same problem: the work is
  already done. Plus you've added a UI.

## Tradeoffs introduced

* Two LLM calls per `--review` ingest. The review pass tends to be
  shorter (planning, no editing), but it's still real cost.
* The runner now embeds dependency injection (`ask`) for
  testability — the production path uses `input`, tests pass a
  callable that returns canned strings. The original repo
  formalizes this with the `CliDeps` dataclass.
* The review prompt and apply prompt have to stay in lockstep. If
  the review's output schema drifts, the apply's expectation of
  "approved plan" drifts too. The original repo handles this by
  keeping both prompt builders in `ingest.py` next to each other.

## LangChain + LangGraph mapping

* This is the first place where *graph orchestration would help*:
  a conditional edge from `review` to `apply` keyed on
  human-in-the-loop approval is exactly what LangGraph's
  `interrupt`/`Command(resume=…)` flow models. See the
  `langgraph-human-in-the-loop` skill.
* The original repo *doesn't* use it. Why: the operator gate is
  a plain blocking `input()` in a CLI, not a long-running
  durable interrupt across a web request. Adding a graph here
  would add ceremony without solving any problem the CLI shape
  doesn't already solve.

## Mentor mode

* **Aha:** the same architectural pattern (two-phase with
  conditional escalation) shows up in both query and ingest
  because they share an underlying constraint — "don't mutate
  durable state without a separable plan step". When you see the
  shape twice, you know it's load-bearing.
* **Common mistake:** building the review phase as a tool call
  *inside* a single agent invocation ("`propose_plan`"). The
  problem isn't generating the plan; it's *not having writes
  available* during planning. That needs to be a separate
  invocation with a different permission profile.
* **Tempting alternative:** skip review and trust the model.
  Works for a week. Then the model hallucinates a contradiction
  resolution and quietly inverts a canonical page. By the time
  you notice, the source-of-truth is unrecoverable.
