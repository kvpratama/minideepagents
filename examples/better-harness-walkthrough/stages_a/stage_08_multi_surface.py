"""Stage 08 — Multi-Surface.

Demonstrate the ``Surface`` abstraction was worth building — add a second
surface (``CALCULATOR_GUIDANCE``) and let the outer agent edit both
``/current/prompt.txt`` and ``/current/calculator_guidance.txt`` in one
iteration.

Run::

    uv run python stages_a/stage_08_multi_surface.py
"""

from __future__ import annotations

import importlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.tools import tool, BaseTool

from config import get_model, get_outer_model

# ── Data model ───────────────────────────────────────────────────────────────

MAX_ITERATIONS = 3


@dataclass
class EvalCase:
    """One eval case."""

    question: str
    expected: str
    split: Literal["train", "holdout"]


@dataclass(frozen=True)
class Surface:
    """One editable surface in the harness."""

    name: str
    target: str
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


@dataclass
class IterationRecord:
    """One iteration's outcome."""

    iteration: int
    candidate_label: str
    changed_surfaces: list[str]
    train_passed: int
    train_total: int
    holdout_passed: int
    holdout_total: int
    combined: int
    accepted: bool
    reason: str


# ── Eval suite ───────────────────────────────────────────────────────────────

CASES = [
    EvalCase(
        "A bakery sells 3 cakes at $12 each. What is the total revenue?", "36", "train"
    ),
    EvalCase("If you divide 144 by 12, what do you get?", "12", "train"),
    EvalCase(
        "A train travels at 60 mph for 2.5 hours. How many miles does it cover?",
        "150",
        "train",
    ),
    EvalCase("What is 15% of 200?", "30", "holdout"),
    EvalCase(
        "A recipe needs 2/3 cup of sugar. If you triple the recipe, how many cups of sugar do you need?",
        "2",
        "holdout",
    ),
]


# ── Surfaces (two!) ─────────────────────────────────────────────────────────

BASE_PROMPT = "You are a helpful assistant."

CALCULATOR_GUIDANCE = "Use this tool for arithmetic."

SURFACES = [
    Surface(
        name="prompt",
        target=f"{__name__}:BASE_PROMPT",
        base_value=BASE_PROMPT,
        filename="prompt.txt",
    ),
    Surface(
        name="calculator_guidance",
        target=f"{__name__}:CALCULATOR_GUIDANCE",
        base_value=CALCULATOR_GUIDANCE,
        filename="calculator_guidance.txt",
    ),
]


def baseline_variant(surfaces: list[Surface]) -> Variant:
    """Build the baseline variant."""
    return Variant(label="baseline", values={s.name: s.base_value for s in surfaces})


# ── Patching ─────────────────────────────────────────────────────────────────


def patch_module_attrs(overrides: dict[str, str]) -> None:
    """Apply module:attribute → value overrides."""
    for target, value in overrides.items():
        module_name, separator, attribute = target.partition(":")
        if not separator:
            msg = f"invalid target {target!r}; expected module:attribute"
            raise ValueError(msg)
        module = importlib.import_module(module_name)
        setattr(module, attribute, value)


def apply_variant(variant: Variant, surfaces: list[Surface]) -> None:
    """Patch all surfaces from a variant."""
    overrides = {s.target: variant.values[s.name] for s in surfaces}
    patch_module_attrs(overrides)


# ── Tool ─────────────────────────────────────────────────────────────────────


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the numeric result.

    The tool reads CALCULATOR_GUIDANCE at call time for additional
    instructions on how to use it.

    Args:
        expression: A Python-syntax math expression like ``3 * 12``.
    """
    # Read guidance at call time so patching takes effect
    guidance = CALCULATOR_GUIDANCE  # noqa: F841 — read for side-effect context

    allowed = set("0123456789+-*/.() ")
    if not all(ch in allowed for ch in expression):
        return f"Error: invalid characters in expression: {expression}"
    try:
        result = eval(expression)  # noqa: S307 — restricted to digits and math ops
    except Exception as exc:
        return f"Error: {exc}"

    # Include guidance in the tool's docstring context (the LLM sees the
    # tool description, which includes the guidance text).
    return str(result)


def make_calculator_with_guidance() -> BaseTool:
    """Build a calculator tool whose description includes the current guidance."""

    @tool
    def calculator_with_guidance(expression: str) -> str:
        """Evaluate a mathematical expression.

        Args:
            expression: A Python-syntax math expression like ``3 * 12``.
        """
        allowed = set("0123456789+-*/.() ")
        if not all(ch in allowed for ch in expression):
            return f"Error: invalid characters in expression: {expression}"
        try:
            result = eval(expression)  # noqa: S307 — restricted to digits and math ops
        except Exception as exc:
            return f"Error: {exc}"
        return str(result)

    # Update the tool description to include current guidance
    calculator_with_guidance.description = (
        f"Evaluate a mathematical expression. {CALCULATOR_GUIDANCE} "
        "Input: a Python-syntax math expression like '3 * 12'."
    )
    return calculator_with_guidance


# ── Inner agent ──────────────────────────────────────────────────────────────


def build_inner_agent():
    """Build the inner agent with the current prompt and calculator guidance."""
    model = get_model()
    calc_tool = make_calculator_with_guidance()
    return create_agent(model, tools=[calc_tool], system_prompt=BASE_PROMPT)


def inner_agent(question: str) -> str:
    """Run one question through the inner agent."""
    agent = build_inner_agent()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
    )
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


def run_eval(
    cases: list[EvalCase],
    agent: object,
    *,
    split: str | None = None,
) -> SplitResult:
    """Run cases through an agent, optionally filtering by split."""
    filtered = [c for c in cases if split is None or c.split == split]
    passed = 0
    failures: list[str] = []
    for case in filtered:
        answer = agent(case.question)  # ty:ignore[call-non-callable]
        if normalize(answer) == normalize(case.expected):
            passed += 1
        else:
            failures.append(
                f"Q: {case.question}  Got: {normalize(answer)}  Expected: {normalize(case.expected)}"
            )
    return SplitResult(
        split=split or "all",
        passed=passed,
        total=len(filtered),
        failures=failures,
    )


# ── Outer agent ──────────────────────────────────────────────────────────────

OUTER_SYSTEM_PROMPT = """\
You are an outer-loop Deep Agent that improves another agent's harness.

The inner agent has two editable surfaces:
1. /current/prompt.txt — the system prompt
2. /current/calculator_guidance.txt — guidance text shown in the calculator tool's description

Your job: read /task.md, then edit one or both files to help the inner agent
pass more math eval cases.

Rules:
- Edit only files under /current/.
- Write the full improved content — not a diff, not instructions.
- The prompt should instruct the agent to always use the calculator.
- The guidance should help the agent formulate correct math expressions.
- Keep both files concise and general — do not hardcode answers.
"""


def propose(
    current_values: dict[str, str],
    train_failures: list[str],
    surfaces: list[Surface],
    *,
    iteration: int,
) -> dict[str, str]:
    """Run the outer Deep Agent once, return proposed values for all surfaces.

    Args:
        current_values: Current surface values keyed by name.
        train_failures: Failing train case descriptions.
        surfaces: All declared surfaces.
        iteration: Current iteration number.

    Returns:
        Dict of surface name → proposed value.
    """
    workspace = Path(tempfile.mkdtemp(prefix=f"better_harness_iter{iteration}_"))
    current_dir = workspace / "current"
    current_dir.mkdir()

    # Write all surface files to the workspace
    for surface in surfaces:
        (current_dir / surface.filename).write_text(current_values[surface.name])

    task_lines = [
        "# Task",
        "",
        f"Iteration {iteration} of the optimization loop.",
        "",
        "Improve the inner agent's harness by editing files under `/current/`.",
        "The inner agent has a `calculator` tool.",
        "",
        "## Editable surfaces",
        "",
    ]
    for surface in surfaces:
        task_lines.append(f"- `/current/{surface.filename}` — {surface.name}")
    task_lines.extend(
        [
            "",
            "## Failing train cases",
            "",
        ]
    )
    for failure in train_failures:
        task_lines.append(f"- {failure}")
    if not train_failures:
        task_lines.append("- None (all passing)")
    task_lines.extend(
        [
            "",
            "Note: holdout cases exist but are not shown.",
        ]
    )
    (workspace / "task.md").write_text("\n".join(task_lines) + "\n")

    backend = FilesystemBackend(root_dir=str(workspace), virtual_mode=True)
    agent = create_deep_agent(
        model=get_outer_model(),
        system_prompt=OUTER_SYSTEM_PROMPT,
        backend=backend,
    )
    agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Read /task.md first.  Then inspect and improve the files "
                        "under /current/.  Stop when done."
                    ),
                }
            ]
        },
        config={"recursion_limit": 50},
    )

    # Read all surfaces back
    proposed: dict[str, str] = {}
    for surface in surfaces:
        proposed[surface.name] = (current_dir / surface.filename).read_text().strip()
    return proposed


# ── Hill-climbing loop ───────────────────────────────────────────────────────


def loop(
    cases: list[EvalCase],
    surfaces: list[Surface],
    *,
    max_iterations: int = MAX_ITERATIONS,
) -> tuple[Variant, list[IterationRecord]]:
    """Run the hill-climbing optimization loop with multiple surfaces.

    Args:
        cases: All eval cases.
        surfaces: All declared surfaces.
        max_iterations: Iteration budget.

    Returns:
        The best variant and the iteration records.
    """
    current = baseline_variant(surfaces)
    apply_variant(current, surfaces)

    current_train = run_eval(cases, inner_agent, split="train")
    current_holdout = run_eval(cases, inner_agent, split="holdout")
    current_combined = current_train.passed + current_holdout.passed
    records: list[IterationRecord] = []

    print(
        f"\nBaseline: train {current_train.passed}/{current_train.total}  "
        f"holdout {current_holdout.passed}/{current_holdout.total}  "
        f"combined {current_combined}\n"
    )

    for i in range(max_iterations):
        print(f"── Iteration {i} ──\n")

        # Propose (outer agent can edit ALL surfaces)
        proposed_values = propose(
            current.values,
            current_train.failures,
            surfaces,
            iteration=i,
        )

        # Identify which surfaces changed
        changed = [
            s.name
            for s in surfaces
            if proposed_values[s.name] != current.values[s.name]
        ]

        # Patch and eval
        candidate = Variant(label=f"iter-{i:03d}", values=proposed_values)
        apply_variant(candidate, surfaces)
        cand_train = run_eval(cases, inner_agent, split="train")
        cand_holdout = run_eval(cases, inner_agent, split="holdout")
        cand_combined = cand_train.passed + cand_holdout.passed

        # Accept rule
        if cand_combined > current_combined:
            reason = f"combined {cand_combined} > {current_combined}"
            current = candidate
            current_train = cand_train
            current_holdout = cand_holdout
            current_combined = cand_combined
            accepted = True
        else:
            reason = f"combined {cand_combined} <= {current_combined}"
            apply_variant(current, surfaces)
            accepted = False

        record = IterationRecord(
            iteration=i,
            candidate_label=candidate.label,
            changed_surfaces=changed,
            train_passed=cand_train.passed,
            train_total=cand_train.total,
            holdout_passed=cand_holdout.passed,
            holdout_total=cand_holdout.total,
            combined=cand_combined,
            accepted=accepted,
            reason=reason,
        )
        records.append(record)

        status = "✓ ACCEPTED" if accepted else "✗ REJECTED"
        changed_str = ", ".join(changed) if changed else "none"
        print(
            f"\n  {status}: train {cand_train.passed}/{cand_train.total}  "
            f"holdout {cand_holdout.passed}/{cand_holdout.total}  "
            f"combined {cand_combined}"
        )
        print(f"  Changed surfaces: {changed_str}")
        print(f"  Reason: {reason}\n")

    return current, records


# ── Report ───────────────────────────────────────────────────────────────────


def print_report(
    baseline: Variant,
    final: Variant,
    surfaces: list[Surface],
    records: list[IterationRecord],
) -> None:
    """Print a summary report."""
    print("=" * 60)
    print("FINAL REPORT")
    print("=" * 60)

    for surface in surfaces:
        base_val = baseline.values[surface.name]
        final_val = final.values[surface.name]
        changed = base_val != final_val
        marker = " (CHANGED)" if changed else ""
        print(f"\n[{surface.name}]{marker}")
        print(f"  Baseline: {base_val[:60]}{'…' if len(base_val) > 60 else ''}")
        print(f"  Final:    {final_val[:60]}{'…' if len(final_val) > 60 else ''}")

    print(f"\nIterations: {len(records)}")
    accepted_count = sum(1 for r in records if r.accepted)
    print(f"Accepted: {accepted_count}/{len(records)}")
    print("\nPer-iteration:")
    for r in records:
        status = "✓" if r.accepted else "✗"
        changed_str = ", ".join(r.changed_surfaces) if r.changed_surfaces else "none"
        print(
            f"  {status} iter {r.iteration}: train {r.train_passed}/{r.train_total}  "
            f"holdout {r.holdout_passed}/{r.holdout_total}  "
            f"combined {r.combined}  surfaces: {changed_str}"
        )
        print(f"      changed surfaces: {r.changed_surfaces}\n")


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> None:
    print("Stage 08 — Multi-Surface (prompt + calculator guidance)\n")

    baseline = baseline_variant(SURFACES)
    final, records = loop(CASES, SURFACES, max_iterations=MAX_ITERATIONS)
    print_report(baseline, final, SURFACES, records)


if __name__ == "__main__":
    main()
