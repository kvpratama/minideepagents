# Stage 07 — `AGENTS.md` (always-loaded memory)

## What's new

```diff
+ memory=[str(AGENTS_MD)],
- system_prompt=SYSTEM_PROMPT,
```

The hand-tuned `SYSTEM_PROMPT` string from stage 06 has moved into a versioned Markdown file: [`AGENTS.md`](AGENTS.md). The Deep Agent reads it on every invocation and prepends it to the system prompt.

## What to read first

1. [`AGENTS.md`](AGENTS.md) — open it side-by-side with the file. Notice it has a **Role**, **Database Information**, **Query Guidelines**, **Safety Rules**, and a **Planning** section. This is the agent's job description.
2. The `memory=[str(AGENTS_MD)]` line — that's the only code change.

## Tradeoff vs. stage 06

| | Stage 06 | Stage 07 |
|---|----------|----------|
| Where instructions live | Python string literal | Markdown file in repo |
| Reviewable in PRs? | Yes, but as code | Yes, as docs (clearer diffs) |
| Editable by non-engineers? | Painful | Yes |
| Multiple environments share it? | Copy-paste | Same file referenced everywhere |
| Tokens loaded every turn | Same | Same (it's in the system prompt either way) |

## Alternative we did not take

**Inline the prompt** the way stage 06 did — it works for a 5-line prompt. AGENTS.md earns its keep when (a) the prompt is non-trivial, (b) you want PMs/SMEs to edit it, or (c) you want it to evolve in version control alongside the code. For this walkthrough, the file is short — but the pattern is what matters.

## Aha insight

> The same shift happens here as in stage 03: a string literal becomes a *file*. Stage 03: hardcoded schema → introspected schema. Stage 07: hardcoded prompt → versioned doc. **Every "agentic" upgrade in this walkthrough is replacing a hardcoded thing with a discoverable thing.** Keep watching for it in stages 08 and 09.

## Studio observation

Open the trace for any question. Look at the system message. You'll see:

- The Deep Agents middleware boilerplate.
- The contents of `AGENTS.md`.
- The tool descriptions.

Edit `AGENTS.md` (e.g. change `LIMIT 5` to `LIMIT 3`). Re-run the same question. The behavior changes without touching Python.

## Exercise

Add a section to `AGENTS.md`:

```markdown
## Output Format

When presenting query results, format them as a Markdown table.
```

Re-run a question. The agent should now produce Markdown tables. **You just shipped a behavior change with zero code edits** — that's the point of `AGENTS.md`.
