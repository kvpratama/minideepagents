# Step A — Tiny Harness

All six capabilities from `01_walkthrough/` collapsed into a single file
(`mini.py`) with one entrypoint, `create_deep_agent`. Still bare LangGraph.

```bash
uv run python step_02_tiny_harness/example.py
uv run langgraph dev   # then pick "02_tiny"
```


## Backends

The harness routes every file tool call through a `Backend` (defined in
`backends.py`). Three implementations ship in this directory:

| Backend | Where files live | When to reach for it |
|---|---|---|
| `StateBackend` (default) | `state["files"]` (per-thread, ephemeral) | Default. Same semantics as `01_walkthrough/03_filesystem.py`. |
| `StoreBackend` | LangGraph `BaseStore` (cross-thread) | Files survive between threads / processes. Pair with any `BaseStore` impl (`InMemoryStore`, Postgres, etc.). |
| `FakeSandboxBackend` | In-memory dict pretending to be a remote sandbox | Pedagogical stand-in for Daytona/Docker backends. Demonstrates that the Protocol absorbs network latency without touching tool code. |

Wire a backend by passing `backend_factory=...` to `create_deep_agent`.
For `StoreBackend`, also pass `store=...` so the compiled graph receives
the same store instance that the factory closes over.

See `example_backends.py` for the same prompt run against all three.
