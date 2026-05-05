# Stage 08 — Skills (progressive disclosure)

## What's new

```diff
+ skills=[str(SKILLS_DIR)],
```

Two `SKILL.md` files appear under `stages/skills/`:

- [`skills/query-writing/SKILL.md`](skills/query-writing/SKILL.md) — how to write good SQL.
- [`skills/schema-exploration/SKILL.md`](skills/schema-exploration/SKILL.md) — how to discover structure and relationships.

Each starts with YAML frontmatter:

```yaml
---
name: query-writing
description: Writes and executes SQL queries from simple SELECTs to complex multi-table JOINs...
---
```

## What to read first

1. The two `SKILL.md` files. Note that they're long — far longer than `AGENTS.md`.
2. The frontmatter `description` on each — that's what the agent sees up front.
3. The single new line in `build_graph()`.

## Tradeoff vs. stage 07

| | Stage 07 | Stage 08 |
|---|----------|----------|
| What's in the prompt at turn 1 | Full `AGENTS.md` | Full `AGENTS.md` + skill *descriptions only* |
| Detailed workflow loaded? | No | Only when relevant — agent fetches it via `read_skill` |
| Tokens for simple Qs | Same | Same |
| Tokens for complex Qs | Same | Slightly more (skill body fetched) |
| Specialised expertise | Inline in `AGENTS.md` | Modular per-task |
| Adding a new specialty | Edit `AGENTS.md` (it grows) | Add a new `skills/<name>/SKILL.md` |

## Alternative we did not take

**Cram every workflow into `AGENTS.md`.** It works for two skills. It breaks for twenty: every irrelevant workflow burns tokens for every query. Skills exist precisely to defer that load. The decision is identical to *eager loading vs. lazy loading* in any other software system — and the right answer is the same: **eager-load identity, lazy-load expertise.**

## Aha insights

> `AGENTS.md` answers *who am I and what are my non-negotiables*. `SKILL.md` answers *how do I do this specific job*. The first is identity; the second is expertise. Both are versioned text files — but they live at different layers of the prompt because they get used at different frequencies.

> Skills look like RAG, but they aren't: there's no embedding, no vector store, no similarity search. The agent picks a skill by reading short descriptions in its prompt, the same way it picks a tool. **A skill is a tool that returns Markdown documentation.**

## Studio observation

Run a question that triggers a skill, e.g. *"Walk me through how to find revenue by artist."* In the trace, look for a tool call that fetches the `schema-exploration` skill. Then run *"How many customers from Canada?"* and notice that **no skill is fetched** — the agent decided it didn't need one.

## Exercise

Add a third skill at `stages/skills/answer-formatting/SKILL.md` whose description is something like *"Formats query results as a Markdown table or as a one-line summary depending on result size."* Write the body so the agent learns when to use a table vs. a sentence. Re-run a few queries and watch the skill get fetched at the right time.

> **Pro tip:** the skill's `description` is what determines whether it gets selected. Short, action-oriented, and specific beats long and abstract every time.
