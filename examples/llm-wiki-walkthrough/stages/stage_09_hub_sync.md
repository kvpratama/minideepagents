# Stage 09 — Context Hub pull / push

## Stage summary

* **Current limitation:** the wiki lives on one operator's laptop.
  No sharing, no atomic versioning, no concurrent-edit safety.
* **Naive fix that fails:** put the workspace in a shared
  Dropbox folder. Race conditions, partial writes during sync,
  hidden binary file uploads, file lock churn.
* **Right fix:** treat the wiki as a *Context Hub repo*. Every
  modifying mode follows pull → mutate → push, with the workspace
  living in a tempdir for the duration of the call.
* **New abstraction:** the pull-modify-push lifecycle wrapped
  around the mode dispatch. `init` is a one-off bootstrap.

## What changed vs. stage 08

* Wrapping any modifying mode is now:

  ```python
  with tempdir() as workspace:
      hub.pull(repo, workspace)
      ensure_scaffold(workspace, topic)
      run_mode(workspace, mode, ...)
      hub.push(repo, workspace)
  ```

* The workspace directory is **ephemeral**. Stages 02–08 stored
  the workspace under `_stageNN_workspace`; from now on it's
  always a `tempfile.TemporaryDirectory()` whose lifecycle equals
  one invocation.
* `init` is a separate workflow that bootstraps the hub repo with
  `source=internal` and then pushes the freshly-scaffolded
  workspace.
* Push-side validation rejects symlinks and non-text files. This
  is the v1 text-only contract the original repo enforces in
  `_validate_text_only_directory`.

## Why shell out to `langsmith hub`, not import an SDK?

The original repo invokes `langsmith hub pull/push` via subprocess
even though `langsmith` is a Python package. This looks ugly but
buys real things:

* The CLI is the *stable contract*. SDK internals churn; CLI
  flags don't. Pinning to `--type agent --dir <path>` shields the
  runner from refactors.
* The CLI handles auth, retries, partial uploads. Reimplementing
  that against the SDK duplicates well-tested code.
* It lets the runner shell out to **any future hub backend** that
  ships a compatible CLI without code changes.

The cost is `subprocess.run` plumbing and error-translation
(`_run_langsmith_cli` in the real `helpers.py`). The walkthrough
swaps in `FakeHub` for runnability; the production code path is
the same shape — `deps.run_langsmith_cli([...])`.

## Failure demonstration

Run the script. The fake hub starts empty; `init_workflow` creates
the repo; two `pull_modify_push` calls simulate an `ingest` and a
`lint`. The hub-side wiki ends up with both mutations applied,
even though the local workspace was thrown away each time.

Flip `(workspace / "raw" / "ada.md").write_text(b"\x00...")` to
write binary into the workspace before push, and `FakeHub.push`
rejects it — same shape as the real text-only validation.

## Why simpler fixes fail later

* **`git push` from the workspace.** Forces every operator to
  have credentials, decide on a remote, and resolve merge
  conflicts. The push step is now an interactive operation.
* **Object store + manifest file.** You'll reinvent a third of
  Context Hub poorly. The whole point of the hub abstraction is
  that it owns the durability + versioning semantics.
* **Keep the workspace persistent across runs.** Saves a pull,
  costs you "what if another teammate pushed in between?". The
  tempdir pattern makes "always start from hub HEAD" the
  default.

## Tradeoffs introduced

* Every modifying run pays a pull + push round-trip. For chunky
  wikis this is noticeable. The original repo doesn't optimize
  this; it bets on hub being fast enough.
* The text-only contract bans images and binary attachments.
  That's a v1 simplification, not a fundamental limit.
* The runner now has *two* places that build a scaffold: `init`
  (first push) and every pull-then-mutate (in case the hub repo
  is missing `wiki/index.md`, `log.md`, etc). The original repo
  factors this into a single `_ensure_scaffold` helper.

## LangChain + LangGraph mapping

* Hub I/O lives entirely outside the agent. The agent sees only
  the workspace filesystem; whether the workspace came from a
  tempdir + pull or a persistent local checkout is invisible to
  it.
* This is also the first place where the `CliDeps` injection
  pattern in the real repo pays off:
  `deps.run_langsmith_cli` and `deps.tempdir_factory` are both
  injectable so the integration tests can run the full pull /
  mutate / push lifecycle against a `FakeHub` exactly like the
  one above.

## Mentor mode

* **Aha:** the tempdir-per-invocation pattern is what makes
  "always start from canonical truth" the default behavior. If
  the workspace lived between runs, you'd be racing against
  other operators every time you forgot to pull.
* **Common mistake:** running the agent against the hub
  directly (some imaginary "hub-backed backend"). The hub is a
  versioned blob store; the agent needs a filesystem.
  Pull / push is the impedance match.
* **Tempting alternative:** wrap pull/push in a context manager
  decorator. Cleaner-looking; loses error context when something
  in the middle fails (which mode? which hub op?). The original
  repo keeps it as inline procedure for a reason.
