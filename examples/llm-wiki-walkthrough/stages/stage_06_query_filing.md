# Stage 06 — query with a filing decision

## Stage summary

* **Current limitation:** stage 05's query mode is strictly read-only.
  High-value answers vanish; trying to "always file" floods the wiki.
* **Naive fix that fails:** post-hoc heuristic in the runner ("file if
  the answer is more than 200 words"). Length is not value.
* **Right fix:** ask the model. Give it a structured output marker for
  its filing decision and re-invoke with write permission only when
  the answer is durable.
* **New abstraction:**
  1. Two-phase mode with a *conditional* second phase.
  2. The `FILING_DECISION:` / `FILING_REASON:` marker convention
     parsed by a regex in the runner.

## What changed vs. stage 05

* Query becomes a *pair* of invocations: a read-only "review" pass
  and an optional write "apply" pass.
* New parser `parse_decision()` extracts the structured marker.
* The apply pass uses a *different* permission profile than the
  review pass (write allowed under `/wiki/**` only).

## Why the marker, not structured output?

The cleaner-looking alternative is `with_structured_output(Schema)`.
The original repo deliberately doesn't use it for query. Reasons:

* The agent's primary output is **prose** (the answer). Forcing the
  whole reply into JSON makes the agent worse at the actual answer.
* The marker is a *side channel*: prose first, then a one-line
  control message at the bottom. The reviewer (human or `log.md`)
  reads the prose; the runner reads the marker.
* A regex parser is dependency-free and trivial to debug. When the
  marker is missing, the runner defaults to `skip` — fail-safe.

The cost: the model occasionally omits the marker or hallucinates a
different key. The default-to-skip behavior makes that recoverable;
worst case the user re-asks with `--file`.

## Failure demonstration

Run the script. The canned response includes a `FILING_DECISION: file`
marker. The parser surfaces the decision, the runner re-invokes with
the apply permission profile, and `/wiki/query/<slug>.md` appears.

Now imagine flipping the canned `FILING_DECISION` to `skip` (or
removing it). The runner short-circuits — no second invocation, no
file written, no permissions escalated. The data path is closed by
default.

## Why simpler fixes fail later

* **Heuristic "is this answer worth filing?"** in Python: length,
  citation count, anything. All proxies, all wrong on hard cases.
* **Always file, prune later** via a separate `lint` mode (stage 08).
  Workable, but it makes query *expensive* (every run is a write)
  and pushes work into a maintenance pass that's harder to attribute.
* **Use a planner agent that decides modes.** Double the LLM calls
  for a one-bit answer; not worth it.

## Tradeoffs introduced

* Two LLM invocations per filed query. Doubles cost for the durable
  cases (the rare ones). Skipped queries stay at one call.
* The runner now has two prompts to maintain (`query_review_prompt`
  vs `query_apply_prompt`) plus a parser. The original repo keeps
  these in `query.py` and unit-tests `parse_query_decision`.
* `/wiki/query/` is a new conventional subtree. The runner-managed
  index (stage 04) already categorizes by top-level subdirectory,
  so this works automatically — `query/` becomes its own section in
  `index.md`.

## LangChain + LangGraph mapping

* The two-phase shape is *still* expressible as plain Python — two
  sequential `agent.invoke(...)` calls with an `if`. LangGraph would
  give you a graph with a conditional edge; nothing today justifies
  the extra ceremony.
* This is also the first time we see a hand-rolled control protocol
  between the runner and the model (the `FILING_DECISION:` marker).
  Whenever you find yourself building that, ask: is this a real
  multi-agent system in disguise? Here the answer is *no* — it's
  one agent, two invocations, with a tiny side-channel.

## Mentor mode

* **Aha:** orchestration is a question of who decides each branch.
  The model decides "should we file?". The runner decides "given the
  decision, who runs next, with what permissions?". That split is
  the entire shape of the workflow.
* **Common mistake:** putting the apply step *inside* the review
  agent's tool surface ("here's a `file_answer` tool"). The review
  agent has read-only permissions; giving it a write tool re-opens
  the blast radius this whole stage was about closing.
* **Tempting alternative:** parsing the answer with another LLM call.
  Don't. Markers were invented because regex never blows your token
  budget.
