# Step 1 — A plain LangChain agent

## What you'll build
The simplest possible research agent: a `create_agent` loop with **one tool**
(`tavily_search`) and nothing else. No system prompt, no planning, no
filesystem.

## Why start here
Everything Deep Agents adds is *opinionated middleware on top of this loop*.
Knowing what bare metal looks like makes each later step's contribution
obvious.

## What's happening
```
user query ──▶ LLM ──▶ (tavily_search? yes/no)
                ▲              │
                └── tool result ┘
```

The agent calls `tavily_search` zero or more times, then emits a final
assistant message.

## Try it
```bash
uv run python steps/step1_basic_agent.py "What is LangGraph?"
```

## Things to notice (limitations)
- **No plan.** The agent decides ad-hoc when to stop.
- **No reflection.** It can't pause to assess what it has.
- **No memory beyond the message list.** Every observation is in the prompt.
- **No delegation.** One agent, one context window.

These are exactly the gaps the next four steps fill in.
