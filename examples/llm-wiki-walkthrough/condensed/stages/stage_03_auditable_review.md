# Stage 3: Two-Phase Ingestion & Temporal Audit Logs

## Stage Summary

* **Current Limitation**: In Stage 2, the agent runs in a single-pass write-only loop. This causes two main problems:
  1. **Unmonitored Writes**: The agent applies synthesized summaries directly to wiki files without operator preview, risking loss of prior synthesis or introduction of bad formatting.
  2. **No Temporal Context**: If multiple ingests are run sequentially, the agent has no memory of *when* or *why* past modifications occurred. It only sees the final files.
* **Why the previous design breaks**: The agent modifies files immediately. If an operator wants to review the plan first, they must run a separate simulation or rollback changes. Furthermore, the lack of timeline history makes it impossible for the agent to know what was added in the latest run versus six months ago.
* **Why simpler fixes fail**: Just keeping a list of modified files in memory during script runtime doesn't persist across CLI command invocations. Feeding the entire Git commit log into the prompt is noisy, expensive, and fails to capture high-level synthesis summaries.
* **What new abstraction is introduced**:
  1. **Two-Phase Workflow (Review-then-Apply)**: The ingest command can run with `--review`. The runner invokes the agent under a *read-only* permission profile (`_review_permissions()`). The agent generates a draft changes report. The runner displays the plan and prompts the operator (`[y/N]`). If approved, the runner runs the agent again with *write-allowed* permissions (`_permissions()`) to apply the changes.
  2. **Append-Only Transaction Ledger (`log.md`)**: A structured chronological log is appended to by the runner after every step. Each entry records the mode/phase, outcome status, metadata (source count, source hint), and a concise summary. This ledger is provided to the agent on subsequent runs as recency context.

---

## Full Working Code

See the runnable script: [stage_03_auditable_review.py](file:///home/openclaw/deepagents/llm_wiki_walkthrough/stages/stage_03_auditable_review.py).

Run the initialization:
```bash
uv run python stages/stage_03_auditable_review.py --mode init --repo adacomp
```

Run an ingest using `--review` mode:
```bash
uv run python stages/stage_03_auditable_review.py --mode ingest --repo adacomp --source ./notes/ada.md --review
```

---

## Detailed Explanation

### What Changed & Why It Matters
By introducing the review/apply split, we've separated the *planning* phase from the *execution* phase:
1. During `review`, the agent runs with strict read-only settings (`deny` write to `/wiki/**`, `/raw/**`, and `/log.md`). It evaluates what needs to be changed.
2. The user validates the draft.
3. During `apply`, the agent is granted write access *only* to `/wiki/**` (not `/raw/` or `/log.md`).

The ledger `/log.md` records every transaction. Future runs read the latest headings of `/log.md` (e.g. `## [2026-05-20] ingest.apply | outcome=applied source_count=1`) to get a quick summary of recent activity without having to read every single wiki page.

### Tradeoffs Introduced
* **Operational Latency**: Splitting ingestion into review and apply requires two LLM invocations and operator waiting time. This increases run time and doubles LLM API fees.
* **HITL Blocking**: If the script is run in non-interactive CI, the interactive prompt blocks indefinitely. The runner must check if `stdin` is a TTY and default to applying directly or raising an error.

### Failure Demonstration
If a file has already been ingested, a naive script might re-ingest it, causing duplicates. With the transaction log, the agent reads `/log.md` first, recognizes the source file name in the logs as already processed, and flags it to the operator rather than performing redundant work.

---

## LangChain + LangGraph Mapping

* **LangChain**: The two-phase loop is implemented via manual state switching inside our python runner (invoking the model with different prompts and tools). In LangChain, this maps to two separate agent chains that share a common state directory.
* **LangGraph**: At this stage, a graph is still not strictly necessary because the state transitions are short and handled by standard Python branch logic. However, the operational complexity is rising: we now have conditional branches based on user inputs (`y` or `n`) and different permission configurations. This is where LangGraph's *compiled state graphs* start becoming attractive to represent this conditional routing cleaner.

---

## Mentor Mode

* **Aha Insight**: Keep logs out of LLM control. Never let the agent write to the transaction ledger (`log.md`) directly. The host runner must capture the agent's summary and append it to `log.md` with system-generated timestamps and metadata. If the agent can write to `log.md`, it can hallucinate historical logs, cover up failures, or get stuck in formatting loops.
* **Common Mistake**: Trying to parse diffs from the LLM response to apply edits. Letting the agent read files, edit them locally within the sandbox, and letting the virtual filesystem backend track write changes is far more robust than attempting to parse LLM unified diffs (which often fail on line offsets or indentation).
* **Tempting Simpler Alternative**: Simply logging the terminal output to a text file.
* **Why it fails**: Raw console outputs contain ANSI colors, agent reasoning chains, and noisy tool trace messages. It is not clean, structured, or easy for future LLM runs to parse as recency context.
