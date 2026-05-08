"""Stage 07 — Outer Loop.

The hill-climbing loop.  Iterate N times.  Keep a candidate iff
``train.passed + holdout.passed`` strictly improves.

Run::

    uv run python stages/stage_07_outer_loop.py
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
from langchain.tools import tool

from config import get_model, get_settings

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
    candidate_prompt: str
    train_passed: int
    train_total: int
    holdout_passed: int
    holdout_total: int
    combined: int
    accepted: bool
    reason: str


# ── Eval suite ───────────────────────────────────────────────────────────────

CASES = [
    EvalCase("A bakery sells 3 cakes at $12 each. What is the total revenue?", "36", "train"),
    EvalCase("If you divide 144 by 12, what do you get?", "12", "train"),
    EvalCase("A train travels at 60 mph for 2.5 hours. How many miles does it cover?", "150", "train"),
    EvalCase("What is 15% of 200?", "30", "holdout"),
    EvalCase("A recipe needs 2/3 cup of sugar. If you triple the recipe, how many cups of sugar do you need?", "2", "holdout"),
]


# ── System prompt ────────────────────────────────────────────────────────────

BASE_PROMPT = "You are a helpful assistant."

PROMPT_SURFACE = Surface(
    name="prompt",
    target="stages.stage_07_outer_loop:BASE_PROMPT",
    base_value=BASE_PROMPT,
)

SURFACES = [PROMPT_SURFACE]


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


# ── Inner agent ──────────────────────────────────────────────────────────────


def build_inner_agent():
    """Build the inner agent using the current BASE_PROMPT."""
    model = get_model()
    return create_agent(model, tools=[calculator], prompt=BASE_PROMPT)


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
        answer = agent(case.question)  # type: ignore[operator]
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
You are an outer-loop Deep Agent that improves another agent's system prompt.

Your job: read /task.md, then edit /current/prompt.txt so the inner agent
passes more math eval cases.  The inner agent has a calculator tool.

Rules:
- Edit only /current/prompt.txt.
- Write the full improved prompt — not a diff, not instructions.
- The prompt should instruct the inner agent to always use the calculator
  tool for any arithmetic and return only the final numeric answer.
- Keep the prompt concise and general — do not hardcode answers.
- Do not embed specific question/answer pairs in the prompt.
"""


def propose(current_prompt: str, train_failures: list[str], *, iteration: int) -> str:
    """Run the outer Deep Agent once, showing only train failures.

    Args:
        current_prompt: The current system prompt.
        train_failures: Failing train case descriptions.
        iteration: Current iteration number (for context in the task).

    Returns:
        The proposed prompt text.
    """
    workspace = Path(tempfile.mkdtemp(prefix=f"better_harness_iter{iteration}_"))
    current_dir = workspace / "current"
    current_dir.mkdir()
    (current_dir / "prompt.txt").write_text(current_prompt)

    task_lines = [
        "# Task",
        "",
        f"Iteration {iteration} of the optimization loop.",
        "",
        "Improve the system prompt in `/current/prompt.txt` so the inner agent",
        "passes more math eval cases.  The inner agent has a `calculator` tool.",
        "",
        "## Failing train cases",
        "",
    ]
    for failure in train_failures:
        task_lines.append(f"- {failure}")
    if not train_failures:
        task_lines.append("- None (all passing)")
    task_lines.extend([
        "",
        "Note: holdout cases exist but are not shown.  Your improvements must generalize.",
    ])
    (workspace / "task.md").write_text("\n".join(task_lines) + "\n")

    settings = get_settings()
    backend = FilesystemBackend(root_dir=str(workspace), virtual_mode=True)
    agent = create_deep_agent(
        model=settings.model,
        system_prompt=OUTER_SYSTEM_PROMPT,
        backend=backend,
    )
    agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Read /task.md first.  Then edit /current/prompt.txt "
                        "with an improved prompt.  Stop when done."
                    ),
                }
            ]
        },
        config={"recursion_limit": 50},
    )

    return (current_dir / "prompt.txt").read_text().strip()


# ── Hill-climbing loop ───────────────────────────────────────────────────────


def loop(
    cases: list[EvalCase],
    surfaces: list[Surface],
    *,
    max_iterations: int = MAX_ITERATIONS,
) -> tuple[Variant, list[IterationRecord]]:
    """Run the hill-climbing optimization loop.

    Args:
        cases: All eval cases (train + holdout).
        surfaces: Declared surfaces.
        max_iterations: Number of iterations to run.

    Returns:
        The best variant and the iteration records.
    """
    current = baseline_variant(surfaces)
    apply_variant(current, surfaces)

    current_train = run_eval(cases, inner_agent, split="train")
    current_holdout = run_eval(cases, inner_agent, split="holdout")
    current_combined = current_train.passed + current_holdout.passed
    records: list[IterationRecord] = []

    print(f"\nBaseline: train {current_train.passed}/{current_train.total}  "
          f"holdout {current_holdout.passed}/{current_holdout.total}  "
          f"combined {current_combined}\n")

    for i in range(max_iterations):
        print(f"── Iteration {i} ──\n")

        # Propose
        candidate_prompt = propose(
            current.values["prompt"],
            current_train.failures,
            iteration=i,
        )

        # Patch and eval
        candidate = Variant(label=f"iter-{i:03d}", values={"prompt": candidate_prompt})
        apply_variant(candidate, surfaces)
        cand_train = run_eval(cases, inner_agent, split="train")
        cand_holdout = run_eval(cases, inner_agent, split="holdout")
        cand_combined = cand_train.passed + cand_holdout.passed

        # Accept rule: combined must strictly improve
        if cand_combined > current_combined:
            reason = f"combined {cand_combined} > {current_combined}"
            current = candidate
            current_train = cand_train
            current_holdout = cand_holdout
            current_combined = cand_combined
            accepted = True
        else:
            reason = f"combined {cand_combined} <= {current_combined}"
            # Restore current variant
            apply_variant(current, surfaces)
            accepted = False

        record = IterationRecord(
            iteration=i,
            candidate_label=candidate.label,
            candidate_prompt=candidate_prompt[:80] + "…",
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
        print(f"\n  {status}: train {cand_train.passed}/{cand_train.total}  "
              f"holdout {cand_holdout.passed}/{cand_holdout.total}  "
              f"combined {cand_combined}  ({reason})\n")

    return current, records


# ── Report ───────────────────────────────────────────────────────────────────


def print_report(
    baseline: Variant,
    final: Variant,
    records: list[IterationRecord],
) -> None:
    """Print a summary report."""
    print("=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"\nBaseline prompt: {baseline.values['prompt']!r}")
    print(f"Final prompt:    {final.values['prompt'][:80]}…" if len(final.values['prompt']) > 80 else f"Final prompt:    {final.values['prompt']!r}")
    print(f"\nIterations: {len(records)}")
    accepted_count = sum(1 for r in records if r.accepted)
    print(f"Accepted: {accepted_count}/{len(records)}")
    print("\nPer-iteration:")
    for r in records:
        status = "✓" if r.accepted else "✗"
        print(f"  {status} iter {r.iteration}: train {r.train_passed}/{r.train_total}  "
              f"holdout {r.holdout_passed}/{r.holdout_total}  combined {r.combined}")


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> None:
    print("Stage 07 — Outer Loop (hill-climbing)\n")

    baseline = baseline_variant(SURFACES)
    final, records = loop(CASES, SURFACES, max_iterations=MAX_ITERATIONS)
    print_report(baseline, final, records)


if __name__ == "__main__":
    main()
