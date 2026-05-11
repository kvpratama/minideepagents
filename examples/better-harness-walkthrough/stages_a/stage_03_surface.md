# Stage 03 — Surface & Variant

## Goal

Introduce `Surface` and `Variant` — the data model that makes "what is
editable" first-class.

## What changed from previous stage

- **`Surface`** dataclass: `(name, target, base_value)`.  `target` is a
  `"module:attribute"` string that says *where* to apply the value.
- **`Variant`** dataclass: `(label, values)`.  A frozen snapshot of all
  surface values.
- **`PROMPT_SURFACE`** declares `BASE_PROMPT` as the editable surface.
- **`baseline_variant()`** builds a variant from the declared surfaces.
- The eval still runs identically to stage 02 — we haven't changed how the
  agent is built, only how we *describe* what's editable.

## Run it

```bash
uv run python stages_a/stage_03_surface.py
```

Expected output: same score as stage 02 (the variant is defined but not
applied differently).

## Walkthrough

1. **`Surface`** — three fields: `name` (human label), `target` (where to
   apply), `base_value` (the default).  Frozen because surfaces are
   declarations, not mutable state.
2. **`Variant`** — `label` + `values` dict.  Also frozen — a variant is a
   snapshot, not a mutable config object.
3. **`PROMPT_SURFACE`** — one surface pointing at
   `stages.stage_03_surface:BASE_PROMPT`.  This means "the `BASE_PROMPT`
   attribute on the `stages.stage_03_surface` module."
4. **`baseline_variant()`** — builds a variant whose values are the
   surfaces' base values.  This is always iteration zero.

## Why this abstraction matters

Without `Surface`, "what the harness can edit" is implicit — it's whatever
the developer happens to patch.  Making it explicit lets the harness
enumerate editable things, show them to the outer agent, and verify that a
variant covers all of them.

## Tradeoffs vs simpler approach

A plain `dict[str, str]` mapping names to values would work for stage 03.
But it wouldn't carry *how to apply* the value (the `target`).  Stage 04
needs that information to do the actual patching.

## LangChain mapping

None — `Surface` and `Variant` are config infrastructure, not LangChain
primitives.

## LangGraph mapping

None — still pure Python dataclasses.

## Aha insight

> The agent's prompt isn't "in the code" — it's a *value* the harness
> loads.  Once that's true, the harness can swap it.

## Common mistake

Putting the surface declaration inside a function instead of at module
level.  The surface's `target` points at a module attribute; if the
attribute doesn't exist at the module level, `patch_module_attrs()` in
stage 04 will fail.

## Simpler alternative & why it breaks later

You could skip `Surface` and just use `{"prompt": "You are a helpful
assistant."}`.  That works until stage 08 adds a second surface — then you
need a way to declare *where* each value goes, and a dict of raw strings
can't carry that.

## Exercise

Add a second `Surface` pointing at a hypothetical
`stages.stage_03_surface:TEMPERATURE` attribute.  Build a variant with both
surfaces.  (You don't need to use it — just see how the variant grows.)

## What Tier B adds here

Stage 09 (`workspace_file_surface`) adds `kind: "workspace_file"` to
`Surface` so the target can be a real file on disk instead of a module
attribute.
