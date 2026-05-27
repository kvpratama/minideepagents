# Stage 08 — lint reconciliation

## Stage summary

* **Current limitation:** ingest is forward-only, query is
  point-in-time. The corpus drifts over time — contradictions,
  stale claims, orphans, missing cross-refs — and nothing
  reconciles.
* **Naive fix that fails:** a "fix it during ingest" pass.
  Ingest's job is to integrate new evidence; folding in
  whole-wiki reconciliation makes every ingest slow, expensive,
  and prompt-soupy.
* **Right fix:** a third mode whose only job is corpus health.
* **New abstraction:** `lint.apply` — single-pass, apply
  immediately, with the *runner-managed log* as recency input.

## What changed vs. stage 07

* New mode in the dispatch.
* Lint prompt explicitly tells the model to read recent
  `/log.md` entries first. This is the first time the runner's
  audit trail becomes *agent input*.
* No review phase. Lint is intentionally apply-only.

## The shape decision: why no review

Ingest is two-phase because individual writes are dangerous and
operators may not know yet which ones they want. Lint runs
*regularly* — weekly, after every batch of ingests — and its
correctness can be assessed by reading the diff afterward. Adding
a review gate would make lint a chore people skip, which means
the corpus rots. The pressure is opposite: minimize friction.

This is the kind of asymmetry that's hard to spot until you live
with the system. The right primitive is "modes have phase
profiles", and each mode picks the profile that fits its
operational pressure — not "every mode is two-phase".

## Why simpler fixes fail later

* **Lint as a cron of small per-page agents.** Reconciling
  contradictions *requires* whole-wiki context. Sharding loses
  exactly the property the lint mode exists to provide.
* **Lint as a structured ruleset (link checker, dead-page
  detector, etc.).** Catches dead links; misses semantic
  contradictions, which are most of the value. The model is the
  only thing that can read two pages and notice they disagree.
* **Lint as a subagent invoked from ingest.** Bundles two distinct
  cadences together. Ingest happens when sources arrive; lint
  happens on a maintenance rhythm. Conflating them either makes
  ingest slow or makes lint sporadic.

## Tradeoffs introduced

* Lint reads *everything*. Token cost grows with wiki size. The
  original repo mitigates by leaning on the runner-managed
  `wiki/index.md` (stage 04) to let the model triage pages.
* Lint can rewrite a lot in one shot. Without review, the only
  recovery is the next Context Hub revision (stage 09) — which
  is the entire reason hub sync exists.
* The prompt asks for a fixed three-section report
  (`## Reconciled Changes`, `## Remaining Gaps`,
  `## Suggested Next Questions and Sources`). This format is
  cited by both the runner's log summary and operator review,
  so prompt drift here breaks the audit trail.

## LangChain + LangGraph mapping

* Single-phase mode → still no graph orchestration needed.
* The interesting LangChain piece is *prompt composition with
  audit context*: feeding `log.md` excerpts into the system
  prompt to give the model recency awareness. This is a tiny
  retrieval pattern dressed as plain file reads.

## Mentor mode

* **Aha:** not every mode wants the same phase shape. Two-phase
  is the right default when a bad apply is destructive; one-phase
  is the right default when the bad case is "skipped this week".
  Pick per mode.
* **Common mistake:** generating a lint *report* without applying
  fixes ("read-only lint that yells about problems"). Operators
  ignore reports. Applied fixes show up in diffs.
* **Tempting alternative:** building lint as a chain of
  rule-based checkers. You'll write 200 lines of code to catch
  what the model catches in one prompt, and you still won't
  handle the semantic contradictions that matter.
