# Stage 09 — Workspace-File Surface

## 1. Goal

Introduce a second `Surface` *kind* — `workspace_file` — so the harness can
edit a file on disk that the inner agent reads at runtime, not just an
in-memory module attribute.

## 2. What changed from previous stage

- `Surface` now carries `kind: Literal["module_attr", "workspace_file"]`.
- New `workspace_override_context(workspace_root, overrides)` — a
  `@contextmanager` that backs each target file up (or records its absence
  with a `None` sentinel), writes the override, yields, and restores on
  exit.
- The calculator tool now reads `<workspace_root>/calculator_guidance.txt`
  at call time. That file lives on disk; the harness only owns it
  *during* an eval run.
- `run_variant(...)` applies both surface kinds at once: `setattr` for
  `module_attr`, the context manager for `workspace_file`.

## 3. Run it

```bash
uv run python stages_b/stage_09_workspace_file_surface.py
```

## 4. Walkthrough

The shape of `Surface` grew by exactly one field — `kind`. Everything
that follows is plumbing for that one field:

```python
@contextlib.contextmanager
def workspace_override_context(workspace_root, overrides):
    backups: dict[Path, str | None] = {}
    try:
        for relative_path, value in overrides.items():
            target = workspace_root / relative_path
            backups[target] = target.read_text() if target.exists() else None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value)
        yield
    finally:
        for target, original in backups.items():
            if original is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(original)
```

`run_variant` is the dispatch site:

```python
patch_module_attrs(attr_overrides(variant, surfaces))
with workspace_override_context(workspace_root, file_overrides(variant, surfaces)):
    return run_eval(cases, inner_agent, split=split)
```

Notice how the calculator tool reads the file every time it's called —
that's why the swap has to live on disk while the eval runs.

## 5. Why this abstraction matters

Not every editable thing is in-memory. Real harnesses have tools, config
files, middleware modules, and skill markdown files that live on disk and
must be present at the path the inner agent loads them from. The
`workspace_file` kind generalizes the surface concept to anything with a
stable on-disk address.

## 6. Tradeoffs vs simpler approach

You could just `open(...).write(...)` and never restore. That works for
one shot, but the moment you have multiple iterations or test isolation
matters, the next eval run sees a polluted workspace. The context manager
costs ten lines and pays it back in determinism.

## 7. LangChain mapping

None new. The inner agent is still `create_agent(model, tools=[...],
prompt=...)`. The new surface kind doesn't touch LangChain — it sits
entirely in the harness layer.

## 8. LangGraph mapping

None new. We're still in plain Python orchestration territory.

## 9. Aha insight

The harness can edit anything that has a stable on-disk address — not
just imported Python objects. Once you have a `kind` field, adding a
third kind (e.g. `env_var`, `git_branch`) is one new dispatch arm.

## 10. Common mistake

Using `try/finally` without recording whether the target file existed
before the swap. If you blindly delete on exit, you'll erase files the
user authored. The `None` sentinel — "this file did not exist before" —
is the fix.

## 11. Simpler alternative & why it breaks later

For a single-surface, in-process harness, `module_attr` alone is enough.
The moment one of your editable things is a real `.md` skill file, a
tool implementation file, or a piece of YAML config, you need
`workspace_file`. Stage 13's TOML config makes this obvious — the
example experiments mix `module_attr` and `workspace_file` surfaces in
the same run.

## 12. Exercise

Add a third surface — say a `system_postscript.txt` workspace file that
the calculator tool appends to its return value. Watch the dispatch
loop in `run_variant` keep working with zero changes.

## 13. What Tier B adds here

Stage 10 introduces `RunLayout`, the durable on-disk artifact tree, so
that running a multi-iteration loop produces inspectable per-iteration
records rather than ephemeral state.
