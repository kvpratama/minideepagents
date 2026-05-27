# Stage 10 — sandbox + local FS via `CompositeBackend`

## Stage summary

* **Current limitation:** stage 09's workspace tempdir is doing
  two jobs at once. It's *both* the agent's compute scratch
  space *and* the unit of truth that will be pushed to Context
  Hub. Those have different requirements.
* **Naive fix that fails:** "tell the agent to write scratch in
  `/tmp/`". Sometimes works; sometimes it writes scratch under
  `/wiki/scratch/` and you push it.
* **Right fix:** split at the backend layer. Default to a
  sandbox backend for everything; route the *canonical*
  paths (`/raw/`, `/wiki/`, `/log.md`, `/AGENTS.md`) to a local
  `FilesystemBackend` pointed at the workspace dir.
* **New abstraction:** `CompositeBackend(default=sandbox,
  routes={...})`.

## What changed vs. stage 09

* `build_agent` now constructs a `CompositeBackend`. Everything
  upstream of `build_agent` (the pull/push, the permissions, the
  scaffold) is unchanged.
* A `FakeSandboxBackend` substitutes for `LangSmithSandbox` so
  the stage runs without LangSmith auth. The real production
  path is:

  ```python
  with _create_langsmith_sandbox_backend() as sandbox_backend:
      workspace_backend = FilesystemBackend(root_dir=workspace_dir,
                                            virtual_mode=True)
      backend = CompositeBackend(
          default=sandbox_backend,
          routes={
              "/raw/":      workspace_backend,
              "/wiki/":     workspace_backend,
              "/log.md":    workspace_backend,
              "/AGENTS.md": workspace_backend,
          },
      )
      agent = create_deep_agent(model=..., backend=backend,
                                permissions=_permissions(),
                                system_prompt=_BASE_SYSTEM_PROMPT)
  ```

  That is the entire final-form runtime — every other stage in
  this walkthrough collapses into the inputs to this one call.

## Failure demonstration

`demonstrate_routing()` writes two files:

* `/wiki/ada-lovelace.md` — routed to the workspace dir.
* `/tmp/scratch.json` — falls through to the sandbox dir.

Listing the two directories afterward shows the split: only
canonical files made it to the workspace. The hub push (stage 09)
captures the workspace; the sandbox is destroyed when the context
manager exits.

Without `CompositeBackend`, scratch and canonical would either:

* both go to the workspace (push validator rejects binaries, or
  worse, you ship junk), or
* both go to the sandbox (canonical files vanish when the sandbox
  is torn down).

The composite backend resolves the impossible-to-prompt-around
choice by encoding it as routing.

## Why simpler fixes fail later

* **One filesystem with deny rules on `/tmp/**` for the push
  step.** Permissions block writes, not reads/scratch. You'd
  have to also enforce "agent must put scratch elsewhere", which
  is back to prompt discipline.
* **Two backends visible to the agent.** Now the model has to
  decide which filesystem to use per call. Prompts get long;
  bugs become "wrong backend chosen".
* **Per-mode backend selection.** Doesn't help — every mode
  needs both compute scratch *and* canonical access. The split
  is per-*path*, not per-*mode*.

## Tradeoffs introduced

* The route table is now real configuration. Add a new top-level
  canonical path (e.g. `/CONTRIBUTORS.md`) and you must update
  three places: the route table, the permission list, and the
  text-only validator.
* Sandbox creation has nontrivial latency. The real repo amortizes
  by reusing a named snapshot (`WIKI_SANDBOX_SNAPSHOT`) and
  letting the sandbox client create one on first miss.
* The sandbox is *new* per invocation. Anything the agent
  installs (pip packages, downloaded artifacts) is gone next
  run. The original repo accepts this — caching across runs
  would require pinning sandbox identity to the hub repo, which
  reintroduces the concurrent-edit problem the tempdir pattern
  fixed in stage 09.

## LangChain + LangGraph mapping

* `CompositeBackend` is a `BackendProtocol` implementation that
  multiplexes over other backends. It's pure infrastructure;
  the agent's tool surface is unchanged.
* The system prompt now disclaims responsibility for paths
  outside `/raw/`, `/wiki/`, `/log.md`, `/AGENTS.md`. This is
  the prompt-side mirror of the routing config. Drift between
  the two will silently lose work.
* Still no graph orchestration. After ten stages of increasing
  complexity, the actual agent is a single `create_deep_agent`
  call. All the orchestration lives in the *runner*. That's the
  big take-away: in a script-first design, the agent is a
  primitive, not the system.

## Mentor mode

* **Aha:** "where does this byte live?" is a routing decision,
  not a prompt instruction. Anything you would otherwise enforce
  via "please write X under Y" is better expressed as a route
  on the composite backend.
* **Common mistake:** routing too granularly. The real repo only
  routes the four canonical paths and lets the sandbox have
  *all* the rest. If you start adding routes for `/data/`,
  `/cache/`, etc., you've recreated the prompt-driven decision
  in code.
* **Tempting alternative:** use one big sandbox and shutil-copy
  the canonical paths back into the workspace at the end. Works
  until a mode reads a canonical page and writes it back — now
  you have to define merge semantics. The route-on-write design
  avoids that entirely.

## Closing the loop

Read [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki)`helpers.py` `_run_agent_mode` now — every
piece should be familiar:

* `CompositeBackend(default=sandbox, routes={…})` → this stage.
* `permissions=_permissions()` → stages 03–05.
* The runner wrapper that calls it → stage 09.
* The mode dispatch above it → stage 05.
* The two-phase ingest / query underneath that → stages 06–07.
* The runner-managed log/index that flank it → stage 04.
* The `FilesystemBackend` everything devolves to → stage 02.
* And one `create_deep_agent` at the bottom — stage 01.
