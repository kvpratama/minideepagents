# Stage 2 — Reflection with `think_tool`

## What changed from Stage 1
| | Stage 1 | Stage 2 |
|---|---|---|
| Tools | `tavily_search` | `tavily_search`, **`think_tool`** |
| Prompt | (none) | research-focused system prompt with budget & stop rules |
| Architecture | unchanged — still `create_agent` | unchanged |

## The trick: a tool that does "nothing"

```python
@tool
def think_tool(reflection: str) -> str:
    return f"Reflection recorded: {reflection}"
```

`think_tool` doesn't query anything. So why use it? Because **it forces a
deliberate pause**. The system prompt requires the model to call
`think_tool` after every `tavily_search`, which:

- gets the reflection into the message history (so it's available for future
  reasoning),
- creates a checkpoint where the model evaluates "do I have enough?", and
- gives you a readable trace of *why* the agent stopped or searched again.

## Try it
```bash
uv run python stages/stage_02_thinking_tool.py "Compare uv vs poetry"
```

You should see alternating `tavily_search` → `think_tool` → `tavily_search`
calls, and a final answer with `[n]` citations.

## Limitations remaining
- Still **no planning** — the agent doesn't write down what it's going to do.
- Still **no filesystem** — research findings live only in the message list.
- Still **no delegation** — one context window for everything.

That's what `create_deep_agent` solves in Stage 3.
