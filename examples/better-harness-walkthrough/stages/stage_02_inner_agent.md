# Stage 02 — Inner Agent

## Goal

Replace the scripted inner stub with a real LangChain agent, so we have
something *worth* improving.

## What changed from previous stage

- `inner_agent()` is now a real LLM call via `create_agent()`.
- A `calculator` tool lets the agent evaluate math expressions.
- `BASE_PROMPT` is a deliberately vague system prompt
  (`"You are a helpful assistant."`) — vague on purpose so the baseline
  score is imperfect.
- `build_inner_agent()` re-constructs the agent each time it's called.
  This matters in stage 04 when we patch `BASE_PROMPT` at the module level.

## Run it

```bash
uv run python stages/stage_02_inner_agent.py
```

Expected output: a mixed score — the agent will get some problems right
(especially easy arithmetic) but miss others because the prompt doesn't
tell it to always use the calculator.

## Walkthrough

1. **`BASE_PROMPT`** — a module-level string.  It's not a constant buried
   in a function; it's an attribute that the harness can read and replace.
   Stage 03 formalizes this as a `Surface`.
2. **`calculator()`** — a `@tool`-decorated function.  Input is a math
   expression string; output is the numeric result.  The restricted
   character set prevents arbitrary code execution.
3. **`build_inner_agent()`** — calls `create_agent(model, tools, prompt)`.
   Returns a compiled graph.
4. **`inner_agent(question)`** — invokes the agent and returns the last
   message's content.  This is the callable that `run_eval()` calls.
5. **`run_eval()` and `normalize()`** — copied from stage 01 (no
   cross-stage imports).

## Why this abstraction matters

The agent is the *unit under test*.  Everything we build from here — surfaces,
patching, the outer agent — exists to change how this agent is configured and
then measure whether the change helped.

## Tradeoffs vs simpler approach

We could use a raw `model.invoke()` call without tools.  That would work for
pure-text questions, but math word problems need a calculator to avoid mental
arithmetic errors — which is exactly the failure mode we want to expose and fix.

## LangChain mapping

- `create_agent` — builds a ReAct-style tool-calling agent.
- `@tool` decorator — registers `calculator` as a tool the agent can call.
- `init_chat_model` (in `config.py`) — routes `provider:model` strings to
  the right LangChain chat model class.

## LangGraph mapping

`create_agent` returns a compiled `StateGraph` under the hood — but at this
stage you don't need to think about it.  The graph has nodes for the LLM call
and tool execution, and edges that loop until the LLM stops calling tools.

## Aha insight

> The same eval harness can score any callable that takes a string and
> returns a string.

## Common mistake

Hardcoding the model inside `build_inner_agent()` instead of reading from
`config.get_model()`.  That makes it impossible to switch providers via `.env`.

## Simpler alternative & why it breaks later

You could inline the agent construction in `inner_agent()` and avoid the
`build_inner_agent()` wrapper.  That breaks in stage 04, which needs to patch
`BASE_PROMPT` *before* construction — so construction must be a separate,
re-callable step.

## Exercise

Change `BASE_PROMPT` to `"Always use the calculator tool for any math."` and
re-run.  Does the score improve?  (Spoiler: yes — and that's exactly what
the outer agent will learn to do in stage 05.)

## What Tier B adds here

Stage 09 (`workspace_file_surface`) introduces a second surface kind
(`workspace_file`) so the harness can swap real files on disk, not just
module attributes.
