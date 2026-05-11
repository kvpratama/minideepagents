# Stage 05 — Outer Agent

## Goal

Introduce the outer Deep Agent and let it edit a virtual file.  No loop
yet — exactly one proposal, then read the result back.

## What changed from previous stage

- **`propose(current_prompt, failures)`** — builds a temporary workspace
  with `/current/prompt.txt` and `/task.md`, hands it to a
  `create_deep_agent` with `FilesystemBackend(virtual_mode=True)`, invokes
  once, and reads the file back.
- **`OUTER_SYSTEM_PROMPT`** — tells the outer agent what its job is.
- **`run_eval()`** now also returns a list of failure descriptions to feed
  to the outer agent.
- The driver: baseline → propose → patch → re-eval → print delta.

## Run it

```bash
uv run python stages_a/stage_05_outer_agent.py
```

Expected output: the proposed prompt is different from the baseline.  The
score may or may not improve — the outer agent is making exactly one
attempt.

## Walkthrough

1. **Workspace setup** — a `tempfile` directory with `/current/prompt.txt`
   and `/task.md`.  This is the "proposer workspace" that the outer agent
   sees.
2. **`FilesystemBackend(virtual_mode=True)`** — gives the outer agent `ls`,
   `read_file`, `write_file`, `edit_file`, `glob`, `grep` tools scoped to
   the workspace.  `virtual_mode=True` restricts path access.
3. **`create_deep_agent()`** — builds a Deep Agent with the filesystem
   backend and a system prompt.  Under the hood, this is a LangGraph
   `StateGraph` with middleware nodes for tool execution.
4. **Invoke** — the user message tells the agent to read the task, edit the
   file, and stop.
5. **Read back** — after invocation, we read `/current/prompt.txt` from
   disk (the virtual mode writes to the real temp directory).

## Why this abstraction matters

The outer agent doesn't see the inner agent's code — it sees a *file*.
That decoupling is what lets it edit any harness, not just this one.  The
file could be a prompt, a tool definition, a middleware config — the outer
agent doesn't care.

## Tradeoffs vs simpler approach

We could use a raw `model.invoke()` call and parse the prompt from the
output text.  That works once, but the outer agent needs structured tools
(`read_file`, `write_file`) to navigate a multi-file workspace in
stage 08.  Using Deep Agents from the start means the workspace idiom is
already in place.

## LangChain mapping

The outer agent is a LangChain agent under the hood.  Deep Agents wraps it
with middleware (filesystem tools, todo tracking, subagent delegation).

## LangGraph mapping

*First stage where LangGraph genuinely matters* — `create_deep_agent`
returns a compiled `StateGraph` with middleware nodes for tool execution.
We don't need to think about the graph ourselves; that's exactly what Deep
Agents abstracts.

## Aha insight

> The outer agent doesn't see the inner agent's code — it sees a file.
> That decoupling is what lets it edit any harness, not just this one.

## Common mistake

Forgetting `virtual_mode=True` on the `FilesystemBackend`.  Without it, the
agent can read/write anywhere on the filesystem — a security risk in any
context beyond a local dev machine.

## Simpler alternative & why it breaks later

You could skip the workspace and just prompt the LLM with "here's the
current prompt, give me a better one."  That works for one surface, but
stage 08 has two files — the workspace pattern scales to arbitrary numbers
of surfaces without changing the outer agent's invocation.

## Exercise

Change the outer system prompt to forbid the word "always" in the proposed
prompt.  Does the agent comply?  Does the resulting prompt still improve
the score?

## What Tier B adds here

Stage 11 (`proposer_workspace`) adds a rich materialized context:
`/task.md`, `/train_cases/*.md`, `/history/`, `surface_manifest.json` —
giving the outer agent much more context to work with.
