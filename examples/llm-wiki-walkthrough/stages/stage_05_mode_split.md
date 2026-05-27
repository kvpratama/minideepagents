# Stage 05 — ingest vs query

## Stage summary

* **Current limitation:** stage 04 has exactly one prompt and one
  permission set for every invocation. A question and a research
  pass have completely different goals — and completely different
  blast radii.
* **Naive fix that fails:** one omni-prompt that branches internally
  ("if the user is asking a question, don't write…"). The model
  decides; sometimes it decides wrong.
* **Right fix:** the *runner* decides. A `mode` selects both the
  prompt and the permission set.
* **New abstraction:** mode-keyed prompt + permission profiles.

## What changed vs. stage 04

* `apply_permissions()` (the old default) is now joined by
  `readonly_permissions()`, which denies writes everywhere.
* `ingest_prompt()` and `query_prompt()` produce distinct prompts.
* `run_mode()` is the new dispatch boundary. The CLI argument that
  the original `runner.py` parses as `--mode` lives right here.

## Failure demonstration

Without mode separation, a stray "while you're at it, fix that
typo in /wiki/concepts.md" inside a question prompt is *valid* —
the agent has write permission, so it will do it. That single
unsupervised edit could corrupt a canonical page.

With the read-only permission profile, the same instruction
becomes a denied tool call, which the agent surfaces as "I can't
edit files in this mode". The blast radius is structurally
bounded — not prompt-bounded.

## Why simpler fixes fail later

* **"Detect intent from the user's prompt and switch internally."**
  You're asking the model to set its own privileges. This is the
  same anti-pattern as letting a web app decide its own SQL grants.
* **"Run two agents in sequence: a planner that picks the mode and
  an executor."** Plausible, but adds latency and a whole second
  reasoning loop just to set a boolean.
* **"Two distinct CLIs (`ask`, `ingest`)."** Equivalent in spirit
  to what we did, just with more boilerplate. The original
  `--mode` flag is the minimal version of this.

## Tradeoffs introduced

* Two prompt templates per mode (and soon, per *phase* within a
  mode) is real code surface. The original repo ends up with
  `ingest.py` / `query.py` / `lint.py` as files dedicated to this.
* The CLI grows a mode dimension. Argument validation has to be
  per-mode (`--question` is required for query, `--source` for
  ingest), which `helpers.parse_config()` does.
* Operators must remember which mode to pick. A bad choice is
  cheap (the permission profile catches misuse) but it slows the
  feedback loop.

## LangChain + LangGraph mapping

* The "mode" is a runner-layer concept — it doesn't appear inside
  the LangGraph state. Each mode is still a single
  `create_deep_agent(...)` invocation per call.
* This is the first place where the pressure for *graph
  orchestration* starts to be visible: by stage 06 each mode will
  have an internal "analyze → conditionally apply" two-phase
  shape, which is exactly the kind of conditional control flow
  that LangGraph state graphs handle naturally. The original repo
  resists that pressure by keeping everything as plain Python
  `if`-branches in the runner. That's a deliberate tradeoff —
  more on it in stage 06.

## Mentor mode

* **Aha:** privileges and prompts should ride together. If you
  change one, you almost always need to change the other.
* **Common mistake:** giving the query mode write permission
  "just in case it needs to fix the index". Don't. The runner
  refreshes the index after the agent returns (stage 04). The
  query agent never needs to write.
* **Tempting alternative:** modelling modes as subagents handed to
  a supervisor agent. Save it for when modes actually compose
  (they don't, in this repo — they're sibling top-level entrypoints).
