"""Stage 09 — Workspace-File Surface.

Introduce the second surface kind: ``workspace_file``.  Where ``module_attr``
patches a Python attribute, ``workspace_file`` swaps a real file in the inner
agent's workspace for one eval run, then restores it on exit.

Run::

    uv run python stages_b/stage_09_workspace_file_surface.py
"""

from __future__ import annotations

import contextlib
import importlib
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain.agents import create_agent
from langchain.tools import tool

from config import get_model

# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class EvalCase:
    """One eval case."""

    question: str
    expected: str
    split: Literal["train", "holdout"]


@dataclass(frozen=True)
class Surface:
    """One editable surface in the harness.

    A ``module_attr`` surface is patched in-process via ``setattr``.
    A ``workspace_file`` surface is a file on disk that the inner agent reads
    at runtime; the harness swaps its contents and restores the original on
    exit.
    """

    name: str
    kind: Literal["module_attr", "workspace_file"]
    target: str  # "module:attr" for module_attr; relative file path for workspace_file
    base_value: str
    filename: str


@dataclass(frozen=True)
class Variant:
    """A frozen snapshot of surface values."""

    label: str
    values: dict[str, str]


@dataclass
class SplitResult:
    """Result of running one split."""

    split: str
    passed: int
    total: int
    failures: list[str]


# ── Eval suite ───────────────────────────────────────────────────────────────

CASES = [
    EvalCase("A bakery sells 3 cakes at $12 each. What is the total revenue?", "36", "train"),
    EvalCase("If you divide 144 by 12, what do you get?", "12", "train"),
    EvalCase("A train travels at 60 mph for 2.5 hours. How many miles does it cover?", "150", "train"),
    EvalCase("What is 15% of 200?", "30", "holdout"),
    EvalCase("A recipe needs 2/3 cup of sugar. If you triple the recipe, how many cups of sugar do you need?", "2", "holdout"),
]


# ── Surfaces (one module_attr + one workspace_file) ─────────────────────────

BASE_PROMPT = "You are a helpful assistant."

# The on-disk surface lives at <WORKSPACE_ROOT>/calculator_guidance.txt.
# WORKSPACE_ROOT is set in main() so the calculator tool can find it.
WORKSPACE_ROOT: Path | None = None
GUIDANCE_FILENAME = "calculator_guidance.txt"
GUIDANCE_BASE = "Use this tool for arithmetic."

SURFACES = [
    Surface(
        name="prompt",
        kind="module_attr",
        target="stages_b.stage_09_workspace_file_surface:BASE_PROMPT",
        base_value=BASE_PROMPT,
        filename="prompt.txt",
    ),
    Surface(
        name="calculator_guidance",
        kind="workspace_file",
        target=GUIDANCE_FILENAME,
        base_value=GUIDANCE_BASE,
        filename=GUIDANCE_FILENAME,
    ),
]


def baseline_variant(surfaces: list[Surface]) -> Variant:
    """Build the baseline variant from the surface base values."""
    return Variant(label="baseline", values={s.name: s.base_value for s in surfaces})


# ── Patching ─────────────────────────────────────────────────────────────────


def patch_module_attrs(overrides: dict[str, str]) -> None:
    """Apply ``module:attribute`` overrides via ``setattr``."""
    for target, value in overrides.items():
        module_name, separator, attribute = target.partition(":")
        if not separator:
            msg = f"invalid module_attr target {target!r}; expected module:attribute"
            raise ValueError(msg)
        module = importlib.import_module(module_name)
        setattr(module, attribute, value)


@contextlib.contextmanager
def workspace_override_context(
    workspace_root: Path,
    overrides: dict[str, str],
) -> Iterator[None]:
    """Temporarily replace files in the target workspace.

    Records each target's prior content (or ``None`` if it didn't exist),
    writes the override, yields, then restores on exit — including via
    exceptions.

    Args:
        workspace_root: Directory containing the workspace files.
        overrides: Mapping of relative file path → new content.
    """
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


def attr_overrides(variant: Variant, surfaces: list[Surface]) -> dict[str, str]:
    """Return module_attr overrides keyed by ``module:attribute`` target."""
    return {
        s.target: variant.values[s.name]
        for s in surfaces
        if s.kind == "module_attr"
    }


def file_overrides(variant: Variant, surfaces: list[Surface]) -> dict[str, str]:
    """Return workspace_file overrides keyed by relative file path."""
    return {
        s.target: variant.values[s.name]
        for s in surfaces
        if s.kind == "workspace_file"
    }


# ── Tool ─────────────────────────────────────────────────────────────────────


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the numeric result.

    The tool also reads <WORKSPACE_ROOT>/calculator_guidance.txt at call
    time — a real on-disk file controlled by the harness.

    Args:
        expression: A Python-syntax math expression like ``3 * 12``.
    """
    if WORKSPACE_ROOT is not None:
        guidance_path = WORKSPACE_ROOT / GUIDANCE_FILENAME
        if guidance_path.exists():
            _ = guidance_path.read_text()  # read for side-effect context

    allowed = set("0123456789+-*/.() ")
    if not all(ch in allowed for ch in expression):
        return f"Error: invalid characters in expression: {expression}"
    try:
        result = eval(expression)  # noqa: S307 — restricted to digits and math ops
    except Exception as exc:
        return f"Error: {exc}"
    return str(result)


# ── Inner agent ──────────────────────────────────────────────────────────────


def build_inner_agent():
    """Build the inner agent using the current BASE_PROMPT."""
    model = get_model()
    return create_agent(model, tools=[calculator], prompt=BASE_PROMPT)


def inner_agent(question: str) -> str:
    """Run one question through the inner agent."""
    agent = build_inner_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"][-1].content


# ── Runner ───────────────────────────────────────────────────────────────────


def normalize(text: str) -> str:
    """Normalize an answer for comparison."""
    text = text.strip()
    numbers = re.findall(r"-?\d+\.?\d*", text)
    if numbers:
        text = numbers[-1]
    if text.endswith(".0"):
        text = text[:-2]
    return text


def run_eval(cases: list[EvalCase], agent, *, split: str | None = None) -> SplitResult:
    """Run cases through an agent, optionally filtering by split."""
    filtered = [c for c in cases if split is None or c.split == split]
    passed = 0
    failures: list[str] = []
    for case in filtered:
        answer = agent(case.question)
        if normalize(answer) == normalize(case.expected):
            passed += 1
        else:
            failures.append(
                f"Q: {case.question}  Got: {normalize(answer)}  Expected: {normalize(case.expected)}"
            )
    return SplitResult(split=split or "all", passed=passed, total=len(filtered), failures=failures)


def run_variant(
    variant: Variant,
    cases: list[EvalCase],
    surfaces: list[Surface],
    workspace_root: Path,
    *,
    split: str | None = None,
) -> SplitResult:
    """Apply a variant (both surface kinds) and run an eval split."""
    patch_module_attrs(attr_overrides(variant, surfaces))
    with workspace_override_context(workspace_root, file_overrides(variant, surfaces)):
        return run_eval(cases, inner_agent, split=split)


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> None:
    global WORKSPACE_ROOT  # noqa: PLW0603 — set once for the inner tool to read
    WORKSPACE_ROOT = Path(tempfile.mkdtemp(prefix="bh_stage09_workspace_"))

    print("Stage 09 — Workspace-File Surface\n")
    print(f"Workspace root: {WORKSPACE_ROOT}\n")

    # Baseline: vague prompt + vague guidance
    baseline = baseline_variant(SURFACES)
    print("Baseline values:")
    for surface in SURFACES:
        print(f"  [{surface.kind}] {surface.name} = {baseline.values[surface.name]!r}")

    base_train = run_variant(baseline, CASES, SURFACES, WORKSPACE_ROOT, split="train")
    base_holdout = run_variant(baseline, CASES, SURFACES, WORKSPACE_ROOT, split="holdout")
    print(
        f"\nBaseline: train {base_train.passed}/{base_train.total}  "
        f"holdout {base_holdout.passed}/{base_holdout.total}\n"
    )

    # Hand-crafted improved variant: edit BOTH surface kinds at once.
    improved = Variant(
        label="hand-crafted",
        values={
            "prompt": (
                "You are a careful math assistant. For ANY arithmetic, "
                "ALWAYS call the `calculator` tool. After getting the "
                "tool's numeric result, return ONLY that number."
            ),
            "calculator_guidance": (
                "Pass a single Python-syntax arithmetic expression. "
                "Examples: '3 * 12', '144 / 12', '60 * 2.5'. "
                "Never do mental math — always call this tool."
            ),
        },
    )
    print("Improved values:")
    for surface in SURFACES:
        snippet = improved.values[surface.name][:60]
        print(f"  [{surface.kind}] {surface.name} = {snippet!r}…")

    # Note: the workspace file only exists *during* the override context.
    guidance_path = WORKSPACE_ROOT / GUIDANCE_FILENAME
    print(f"\nBefore override: {GUIDANCE_FILENAME!r} exists? {guidance_path.exists()}")
    imp_train = run_variant(improved, CASES, SURFACES, WORKSPACE_ROOT, split="train")
    print(f"After  override: {GUIDANCE_FILENAME!r} exists? {guidance_path.exists()}")
    imp_holdout = run_variant(improved, CASES, SURFACES, WORKSPACE_ROOT, split="holdout")

    print(
        f"\nImproved: train {imp_train.passed}/{imp_train.total}  "
        f"holdout {imp_holdout.passed}/{imp_holdout.total}"
    )
    print("\nThe guidance file was created during the override and removed on exit.")


if __name__ == "__main__":
    main()
