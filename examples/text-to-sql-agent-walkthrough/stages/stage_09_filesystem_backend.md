# Stage 09 — Persistent filesystem backend (final form)

## What's new

```diff
+ from deepagents.backends import FilesystemBackend
...
+ backend=FilesystemBackend(root_dir=str(STAGE_DIR)),
```

This stage matches the upstream [`text-to-sql-agent/agent.py`](../../text-to-sql-agent/agent.py) modulo cosmetic differences (CLI framing, naming).

## What to read first

1. The `backend=FilesystemBackend(...)` line — that is the whole diff against stage 08.
2. The directory after running a complex question — look for files the agent wrote (e.g. `revenue_by_employee.csv`).

## Tradeoff vs. stage 08

| | Stage 08 (default backend) | Stage 09 (filesystem) |
|---|------------------|-----------|
| `write_file` lifetime | In-memory, per-invocation | On disk, persistent |
| Inspectable from editor mid-run? | No | Yes |
| Survives across CLI invocations? | No | Yes |
| Exportable artifacts? | No | Yes |
| Risk: agent overwrites real files | None | Real (sandbox `root_dir` carefully) |
| Risk: state leaks between users | None | Real (per-user `root_dir`) |

## Alternative we did not take

**`StoreBackend`** — backed by a LangGraph `Store` (e.g. Redis, Postgres). That's the right choice for multi-user production deployments where you want per-tenant persistence without giving the agent real disk access. We use `FilesystemBackend` here because for a local walkthrough, *seeing the artifacts on disk* is the entire pedagogical point.

## Aha insights

> Stage 06 introduced an in-memory filesystem (so the agent can scratch). Stage 09 makes that filesystem **real**. The ladder is: no fs → ephemeral fs → durable fs → multi-tenant store. Each rung has a use case; pick the lowest one that solves your problem.

> A persistent backend turns a one-shot agent into a **stateful workspace**. Run the same thread twice with `--thread-id same-id` (Studio gives you that for free) and the agent can `read_file` the artifacts from the previous run. The agent now has a working memory in addition to a conversational one.

## Studio exercise

1. In Studio, pick `stage_09_filesystem_backend`.
2. Send: `"Compute revenue per employee per country and save the result as revenue_by_employee.csv."`
3. After it finishes, check `stages/revenue_by_employee.csv` in your editor.
4. Open a new thread (same graph) and ask: `"Load revenue_by_employee.csv and tell me which country has the second-highest total revenue."` Watch the agent `read_file` the artifact.

## Comparing stage 09 to the upstream agent

```bash
diff stages/stage_09_filesystem_backend.py ../text-to-sql-agent/agent.py
```

The behavioural differences are essentially zero. The structural differences:

- Upstream uses `subagents=[]` explicitly; we omit (same default).
- Upstream prints with `rich`; we use plain `print` for clarity in stage `.py` files.
- Upstream has no `graph` symbol; we expose one for Studio.

**That last point is the only meaningful enhancement.** Adding a top-level `graph = ...` to any Deep Agent makes it Studio-loadable — no other changes needed. Consider doing this for every Deep Agent you ship.

## Where to go next

- Try modifying `AGENTS.md` to add a `## Output Format` rule and re-run.
- Add a third skill (see exercise in stage 08).
- Swap `ChatAnthropic` for `init_chat_model("openai:gpt-4o")` and confirm everything still works — the agent stack is model-agnostic.
- Add a `subagents=[...]` to delegate complex JOIN questions to a focused subagent. (See the `deep-agents-orchestration` skill.)

You've finished the walkthrough. **You can now read the upstream `text-to-sql-agent/agent.py` and recognize every line.**
