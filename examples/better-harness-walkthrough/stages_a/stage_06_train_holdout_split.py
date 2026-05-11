"""Stage 06 — Train / Holdout Split.

Introduce the split.  The outer agent only sees train failures; we measure
on both train and holdout.  Without a holdout, the outer agent can overfit
by hardcoding train answers into the prompt.

Run::

    uv run python stages_a/stage_06_train_holdout_split.py
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

from config import get_outer_model, get_model

# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class EvalCase:
    """One eval case with a question, expected answer, and split tag."""

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
    """A frozen snapshot of all surface values plus a label."""

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
    # ── Train (visible to the outer agent) ──
    EvalCase(
        question="A bakery sells 3 cakes at $12 each. What is the total revenue?",
        expected="38",
        split="train",
    ),
    EvalCase(
        question="If you divide 144 by 12, what do you get?",
        expected="14",
        split="train",
    ),
    EvalCase(
        question="A train travels at 60 mph for 2.5 hours. How many miles does it cover?",
        expected="152",
        split="train",
    ),
    # ── Holdout (private — the outer agent never sees these) ──
    EvalCase(
        question="What is 15% of 200?",
        expected="32",
        split="holdout",
    ),
    EvalCase(
        question="A recipe needs 2/3 cup of sugar. If you triple the recipe, how many cups of sugar do you need?",
        expected="4",
        split="holdout",
    ),
]


# ── System prompt ────────────────────────────────────────────────────────────

BASE_PROMPT = "You are a helpful assistant."

PROMPT_SURFACE = Surface(
    name="prompt",
    target=f"{__name__}:BASE_PROMPT",
    base_value=BASE_PROMPT,
)

SURFACES = [PROMPT_SURFACE]


def baseline_variant(surfaces: list[Surface]) -> Variant:
    """Build the baseline variant."""
    return Variant(
        label="baseline",
        values={s.name: s.base_value for s in surfaces},
    )


# ── Patching ─────────────────────────────────────────────────────────────────


def patch_module_attrs(overrides: dict[str, str]) -> None:
    """Apply module:attribute → value overrides via setattr."""
    for target, value in overrides.items():
        module_name, separator, attribute = target.partition(":")
        if not separator:
            msg = f"invalid target {target!r}; expected module:attribute"
            raise ValueError(msg)
        module = importlib.import_module(module_name)
        setattr(module, attribute, value)


def apply_variant(variant: Variant, surfaces: list[Surface]) -> None:
    """Patch all surfaces from a variant's values."""
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
    return create_agent(model, tools=[calculator], system_prompt=BASE_PROMPT)


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
    """Run cases through an agent, optionally filtering by split.

    Args:
        cases: All eval cases.
        agent: Callable that takes a question and returns an answer.
        split: If set, only run cases with this split tag.

    Returns:
        A SplitResult with pass count and failure descriptions.
    """
    filtered = [c for c in cases if split is None or c.split == split]
    passed = 0
    failures: list[str] = []
    for case in filtered:
        answer = agent(case.question)  # ty:ignore[call-non-callable]
        if normalize(answer) == normalize(case.expected):
            passed += 1
            print(f"  ✓ [{case.split}] {case.question[:45]}…  →  {normalize(answer)}")
        else:
            failures.append(
                f"Q: {case.question}  Got: {normalize(answer)}  Expected: {normalize(case.expected)}"
            )
            print(
                f"  ✗ [{case.split}] {case.question[:45]}…  →  {normalize(answer)}  "
                f"(expected {normalize(case.expected)})"
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


def propose(current_prompt: str, train_failures: list[str]) -> str:
    """Run the outer Deep Agent once, showing only train failures.

    The outer agent NEVER sees holdout cases — that's the whole point.

    Args:
        current_prompt: The current system prompt text.
        train_failures: Descriptions of failing *train* cases only.

    Returns:
        The proposed prompt text.
    """
    workspace = Path(tempfile.mkdtemp(prefix="better_harness_"))
    current_dir = workspace / "current"
    current_dir.mkdir()
    (current_dir / "prompt.txt").write_text(current_prompt)

    task_lines = [
        "# Task",
        "",
        "Improve the system prompt in `/current/prompt.txt` so the inner agent",
        "passes more math eval cases.  The inner agent has a `calculator` tool.",
        "",
        "## Failing train cases (visible to you)",
        "",
    ]
    for failure in train_failures:
        task_lines.append(f"- {failure}")
    if not train_failures:
        task_lines.append("- None (all passing)")
    task_lines.extend([
        "",
        "Note: there are also holdout cases that you cannot see.",
        "Your improvements must generalize beyond these specific failures.",
    ])
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
                        "Read /task.md first.  Then edit /current/prompt.txt "
                        "with an improved prompt.  Stop when done."
                    ),
                }
            ]
        },
        config={"recursion_limit": 50},
    )

    return (current_dir / "prompt.txt").read_text().strip()


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> None:
    print("Stage 06 — Train / Holdout Split\n")

    baseline = baseline_variant(SURFACES)

    # 1. Baseline on both splits
    print("=== Baseline — Train ===\n")
    baseline_train = run_eval(CASES, inner_agent, split="train")
    print(f"\nTrain: {baseline_train.passed}/{baseline_train.total}")

    print("\n=== Baseline — Holdout ===\n")
    baseline_holdout = run_eval(CASES, inner_agent, split="holdout")
    print(f"\nHoldout: {baseline_holdout.passed}/{baseline_holdout.total}")

    # 2. Propose (outer agent only sees train failures)
    print("\n=== Outer agent proposing (sees only train failures)… ===\n")
    proposed_prompt = propose(baseline.values["prompt"], baseline_train.failures)
    print(f"Proposed prompt:\n{proposed_prompt}\n")

    # 3. Patch and re-eval on both splits
    proposed = Variant(label="proposed", values={"prompt": proposed_prompt})
    apply_variant(proposed, SURFACES)

    print("=== Proposed — Train ===\n")
    proposed_train = run_eval(CASES, inner_agent, split="train")
    print(f"\nTrain: {proposed_train.passed}/{proposed_train.total}")

    print("\n=== Proposed — Holdout ===\n")
    proposed_holdout = run_eval(CASES, inner_agent, split="holdout")
    print(f"\nHoldout: {proposed_holdout.passed}/{proposed_holdout.total}")

    # 4. Restore baseline
    apply_variant(baseline, SURFACES)

    # 5. Summary
    baseline_combined = baseline_train.passed + baseline_holdout.passed
    proposed_combined = proposed_train.passed + proposed_holdout.passed
    print("\n=== Summary ===")
    print(f"  Baseline:  train {baseline_train.passed}/{baseline_train.total}  "
          f"holdout {baseline_holdout.passed}/{baseline_holdout.total}  "
          f"combined {baseline_combined}")
    print(f"  Proposed:  train {proposed_train.passed}/{proposed_train.total}  "
          f"holdout {proposed_holdout.passed}/{proposed_holdout.total}  "
          f"combined {proposed_combined}")


if __name__ == "__main__":
    main()
