# Stage 03 — `raw/` vs `wiki/` and the permission policy

## Stage summary

* **Current limitation:** stage 02 had one global namespace, so a wide
  edit could destroy evidence the agent needed to recover.
* **Naive fix that fails:** "say so in the prompt" — works until the
  model is having a bad day, gets a stray instruction in a source file,
  or is run by a different prompt revision.
* **Right fix:** physical namespace split (`/raw/`, `/wiki/`) **and**
  middleware enforcement (`FilesystemPermission(deny /raw/**)`).
* **New abstraction:** `FilesystemPermission`.

## What changed vs. stage 02

Two minimal additions:

```python
(workspace / "raw").mkdir(...)
(workspace / "wiki").mkdir(...)

permissions = [
    FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
]
agent = create_deep_agent(..., backend=backend, permissions=permissions)
```

The folder structure is convention. The `permissions` list is what
makes the convention enforceable.

## Failure demonstration

`show_failure_without_permissions` mutates `/raw/ada.md` directly via
the filesystem (simulating an agent that ignored the prompt) and prints
the corrupted state. After permissions are wired in, that same write
attempted through the agent's tool surface raises a denial — the
evidence is structurally safe.

## Why simpler fixes fail later

* **Prompt-only protection** is one model regression away from a
  destroyed wiki, and there's no audit trail showing *why* a fact
  vanished.
* **Filesystem permissions at the OS layer (`chmod`)** would protect
  evidence from the agent, but also from the runner that needs to drop
  in new source files at the start of each ingest. The agent and the
  runner share a process and a uid; the boundary has to be inside the
  agent's tool layer, not below it.
* **A side-database for evidence** (Postgres, S3) decouples it from
  `/raw/` but also from `grep` and `read_file`. The whole reason the
  agent works well is that evidence is co-resident with synthesis on
  the same virtual filesystem. Adding a query API would force prompt
  changes for no architectural win.

## Tradeoffs introduced

* The permission list is policy code, not data — every new restricted
  area is a new entry. By stage 05 we'll have three of these (deny
  raw, deny log, deny AGENTS.md) and they will start to feel like a
  small policy DSL.
* The agent gets a tool-call error when it tries a denied write. That
  error becomes part of the trajectory and the model has to recover.
  In practice this is fine; the prompt steers it elsewhere. But it
  raises the bar for prompt clarity.

## LangChain + LangGraph mapping

* `FilesystemPermission` is a `FilesystemMiddleware` concern — it's a
  middleware hook on the agent's filesystem tools, not a separate
  graph node. The model still sees `write_file`, `edit_file`, etc.;
  the middleware short-circuits the actual call when the path matches
  a `deny` rule.
* LangGraph is *still* over-spec'd. We have not yet introduced phases
  that justify graph orchestration.

## Mentor mode

* **Aha:** prompt rules and policy enforcement are two different
  things. Anything you can express in the prompt as "never X" should
  also be expressed as `FilesystemPermission(deny X)`. Belt and
  suspenders, because models drift.
* **Common mistake:** putting the deny rule on `*/raw/*` instead of
  `/raw/**`. The original repo uses the rooted `/raw/**` glob because
  the virtual filesystem is rooted at `/`, not relative to wherever
  the agent thinks "raw" is.
* **Tempting alternative:** read-only mount, copy-on-write overlay,
  fancy sandboxing. Save it. Real isolation comes in stage 10 once
  we know what we actually need to isolate.
