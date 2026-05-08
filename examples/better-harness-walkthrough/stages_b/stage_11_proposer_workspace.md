# Stage 11 — Proposer Workspace

## 1. Goal

Materialize a rich, structured workspace for the outer Deep Agent so it
can propose better edits — not just one prompt file, but `task.md`,
`surface_manifest.json`, per-failing-case context, and prior-iteration
history.

## 2. What changed from previous stage

- New `build_proposer_workspace(...)` that writes a fixed layout under
  one parent directory.
- New `ProposerWorkspace` dataclass exposing `root`, `current_dir`,
  `proposal_file`, and `surface_files`.
- The outer agent's prompt now mentions `surface_manifest.json`,
  `train_cases/`, and `history/` as inputs.
- `EvalCase` gained a `case_id` field so train-case files can be named
  deterministically.
- `SplitResult` now carries `CaseOutcome` records so failing cases can be
  rendered into per-case markdown without re-running them.

## 3. Run it

```bash
uv run python stages_b/stage_11_proposer_workspace.py
```

## 4. Walkthrough

The workspace is just a directory with a fixed shape:

```text
iter-000/
  task.md
  surface_manifest.json
  current/
    prompt.txt
    calculator_guidance.txt
  train_cases/
    bakery.md
    divide.md
  history/
    000.md     # populated from iter-001 onwards
  proposal.md  # agent writes its summary here
```

The outer agent sees this as a `FilesystemBackend(virtual_mode=True)`
mounted at its root. Its system prompt directs it to read `task.md` and
the surrounding context, edit `current/*` to final form, and write a
short summary to `proposal.md`.

After the agent returns, the harness re-reads `current/<filename>` for
every surface to build the candidate `Variant`.

## 5. Why this abstraction matters

Raw failure stdout is a poor brief. With a flat tempdir of one prompt
file, the outer agent flails. With a structured workspace it can:

- read `surface_manifest.json` to know what each file maps to,
- read failing cases without ever seeing their expected answers,
- read prior decisions to avoid re-trying the same edit,
- write its rationale somewhere the harness can persist.

This is "context engineering": the agent's quality scales with the
quality of the workspace you hand it.

## 6. Tradeoffs vs simpler approach

You could keep stuffing context into the user message. That works until
the message gets too big to debug, and you can't show the agent prior
decisions without tokenizing the whole history. A filesystem layout is
random-access and free to grow.

## 7. LangChain mapping

None new. The outer agent is still a Deep Agent (LangChain under the
hood) — only the workspace it reads from changed.

## 8. LangGraph mapping

None new. We're still running one outer-agent invocation per iteration.

## 9. Aha insight

Context engineering — what the agent sees, in what shape — separates a
proposer that hill-climbs from one that thrashes. The workspace is the
agent's view of the world.

## 10. Common mistake

Writing the *expected* answer into `train_cases/<id>.md`. The outer
agent will just memorize the answers in the prompt. Hash out the
expected section explicitly, both as a guard rail and as documentation
of intent.

## 11. Simpler alternative & why it breaks later

A single `failing_cases.txt` blob is fine for two cases. With ten cases,
you want random-access by case id; with iterations, you want history
files. Once you want both, the workspace pattern is the natural fit.

## 12. Exercise

Add an `agent_log/` directory to the workspace and have the outer agent
append a one-line note before each tool call. Compare runs with and
without it.

## 13. What Tier B adds here

Stage 12 introduces the `scorecard` split — the held-out-from-the-loop
metric — so the number you optimize and the number you report stop
being the same number.
