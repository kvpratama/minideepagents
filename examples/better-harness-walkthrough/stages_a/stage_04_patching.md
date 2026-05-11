# Stage 04 — Patching

## Goal

Apply a `Variant` to the live inner agent via `setattr` on a module
attribute.  This is the bridge from "we have a Variant object" to "the
inner agent actually uses it."

## What changed from previous stage

- **`patch_module_attrs(overrides)`** — splits `"module:attr"`, imports the
  module, and `setattr`s the new value.
- **`apply_variant(variant, surfaces)`** — builds the overrides dict from a
  variant and calls `patch_module_attrs()`.
- **`IMPROVED_PROMPT`** — a hand-crafted prompt that tells the agent to
  always use the calculator.
- The driver runs the baseline eval, patches the improved variant, re-runs
  the eval, and prints the delta.

## Run it

```bash
uv run python stages_a/stage_04_patching.py
```

Expected output: the improved variant scores strictly higher than the
baseline because the prompt now instructs calculator use.

## Walkthrough

1. **`patch_module_attrs()`** — the core primitive.  Given
   `{"stages.stage_04_patching:BASE_PROMPT": "new text"}`, it does
   `importlib.import_module("stages.stage_04_patching")` then
   `setattr(module, "BASE_PROMPT", "new text")`.
2. **`apply_variant()`** — translates from `Variant.values` (keyed by
   surface name) to the overrides dict (keyed by target string).
3. **Driver order** — *patch first, then build the agent, then invoke*.
   If you build the agent before patching, it captures the old prompt at
   construction time and the patch has no effect.
4. **Restore** — after the improved eval, the driver patches the baseline
   back.  This isn't strictly needed here but demonstrates the principle:
   patching is reversible.

## Why this abstraction matters

The prompt isn't a property on the agent object — it's whatever the agent
module *reads at construction time*.  Module-attr patching works for any
value the harness loads on import, not just prompts.  Stage 08 uses the
exact same mechanism to patch a tool-guidance string.

## Tradeoffs vs simpler approach

We could pass the prompt as an argument to `build_inner_agent()` instead of
patching a module attribute.  That works for one surface but doesn't
generalize — the inner agent's code shouldn't need to change every time the
harness adds a new editable surface.

## LangChain mapping

Still just `create_agent` for the inner agent.  Patching is pure Python; no
LangChain primitives involved.

## LangGraph mapping

None.

## Aha insight

> You don't need an SDK to swap an agent's prompt — Python is mutable.

## Common mistake

**Patching after the agent is already constructed and cached.**  If you do
`agent = build_inner_agent()` then `apply_variant(improved, SURFACES)` then
`agent.invoke(...)`, the agent still uses the old prompt.  The correct order
is: **patch → construct → invoke**.

## Simpler alternative & why it breaks later

You could skip `apply_variant()` and do `setattr` manually.  That works for
one surface, but stage 08 has two surfaces — a helper that iterates over all
surfaces keeps the driver clean.

## Exercise

Write a second hand-crafted variant with a *bad* prompt (e.g.
`"Never use tools."`) and verify the score drops.  This shows that the
patching mechanism works in both directions.

## What Tier B adds here

Stage 09 (`workspace_file_surface`) adds `workspace_override_context()` — a
context manager that swaps real files on disk instead of module attributes,
then restores them on exit.
