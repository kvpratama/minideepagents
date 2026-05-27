# Stage 02 — persistent files

## Stage summary

* **Current limitation:** stage 01 throws everything away.
* **Naive fix that fails:** "just add a checkpointer" — wrong axis, that
  saves trajectories, not a corpus.
* **Right fix:** swap `StateBackend` for `FilesystemBackend(root_dir=…)`
  so the agent's virtual `/` is a real directory on disk.
* **New abstraction:** `FilesystemBackend` with `virtual_mode=True`. The
  agent thinks it's writing to `/`, the host sees `./workspace/...`.

## What changed vs. stage 01

Exactly one line in `build_agent`:

```python
backend = FilesystemBackend(root_dir=wiki_dir, virtual_mode=True)
agent  = create_deep_agent(..., backend=backend)
```

Everything else is identical. This is the smallest possible change that
buys us cross-run persistence.

## Failure demonstration

`simulate_collision()` writes `notes.md` twice in a row with different
content. The second write annihilates the first. In the multi-run case,
that's two separate research sessions destroying each other's work
because they both reach for the obvious filename.

Run it:

```bash
python stages/stage_02_persistent_files.py
```

Output shows only the second set of notes survived. Multiply this by
a hundred research sessions and you have a wiki that constantly
re-rolls its own contents.

## Why simpler fixes fail later

* **"Just tell the agent in the prompt to pick unique filenames."**
  Models drift. After ten runs you have `notes.md`, `notes2.md`,
  `ada-notes.md`, `lovelace_bio.md`, all overlapping. The wiki is
  unsearchable.
* **"Just keep one canonical file per topic."** Now every ingest needs
  to read+merge+rewrite the whole file, and an off-by-one slice can
  vaporize months of synthesis. There is no protected ground truth to
  rebuild from.

Both failure modes have the same root cause: **the agent's output and
its input live in the same namespace.** A bad write trashes the
evidence it would need to recover. The next stage fixes this with a
two-namespace split (`/raw/` immutable, `/wiki/` editable) and a
permission policy that enforces it.

## LangChain + LangGraph mapping

* `FilesystemBackend` is one of `deepagents.backends`'s
  `BackendProtocol` implementations. It's still presented to the agent
  via the same virtual-filesystem tool surface that `StateBackend`
  exposes — `read_file`, `write_file`, `grep`, etc.
* LangGraph is still vastly over-spec'd for this. Everything happens
  inside one ReAct-like loop. We have not yet introduced the kind of
  *multi-phase* control flow that makes a graph nontrivial.

## Mentor mode

* **Aha:** persistence is a backend swap, not an architectural change.
  The Deep Agents abstraction over `BackendProtocol` is the reason this
  is a one-line move and not a rewrite.
* **Common mistake:** treating the filesystem as "just storage" instead
  of "the agent's actual memory model". Once writes are durable, every
  prompt is implicitly addressing a growing global state.
* **Tempting alternative:** committing each agent run as a git commit
  in the workspace. Cute, but you've now built half a sync system and
  still don't have evidence/synthesis separation. Stage 09 will pull in
  Context Hub for the real sync story; do that work once, properly.
