"""Stage 01 — Eval Harness.

The measurement substrate everything else depends on.  No LLM, no agent
framework — just a list of eval cases, a scripted inner "agent", and a
runner that counts pass/fail.

Run::

    uv run python stages_a/stage_01_eval_harness.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class EvalCase:
    """One eval case with a question and a known-good answer."""

    question: str
    expected: str


# ── Eval suite ───────────────────────────────────────────────────────────────

CASES = [
    EvalCase(
        question="A bakery sells 3 cakes at $12 each. What is the total revenue?",
        expected="36",
    ),
    EvalCase(
        question="If you divide 144 by 12, what do you get?",
        expected="12",
    ),
    EvalCase(
        question="A train travels at 60 mph for 2.5 hours. How many miles does it cover?",
        expected="150",
    ),
    EvalCase(
        question="What is 15% of 200?",
        expected="30",
    ),
    EvalCase(
        question="A recipe needs 2/3 cup of sugar. If you triple the recipe, how many cups of sugar do you need?",
        expected="2",
    ),
]


# ── Inner "agent" (scripted stub) ────────────────────────────────────────────


def inner_agent(question: str) -> str:
    """Scripted stub — always returns '42'.

    This is deliberately useless.  The point is to show that the eval
    harness doesn't care *how* the answer is produced — it only checks
    the output against the expected value.
    """
    _ = question  # unused
    return "42"


# ── Runner ───────────────────────────────────────────────────────────────────


def normalize(text: str) -> str:
    """Normalize an answer string for comparison.

    Strips whitespace, extracts the last number found, and drops
    trailing '.0' so that ``'36.0'`` matches ``'36'``.
    """
    text = text.strip()
    # Pull the last number out of the text (handles "The answer is 36").
    numbers = re.findall(r"-?\d+\.?\d*", text)
    if numbers:
        text = numbers[-1]
    # Drop trailing .0 for integer comparison.
    if text.endswith(".0"):
        text = text[:-2]
    return text


def run_eval(
    cases: list[EvalCase],
    agent: Callable[[str], str],
) -> tuple[int, int]:
    """Run cases through an agent callable and return (passed, total).

    Args:
        cases: Eval cases to run.
        agent: Any callable that accepts a question string and returns
            an answer string.

    Returns:
        A tuple of (number passed, total cases).
    """
    passed = 0
    for case in cases:
        answer = agent(case.question)
        if normalize(answer) == normalize(case.expected):
            passed += 1
            print(f"  ✓ {case.question[:50]}…  →  {normalize(answer)}")
        else:
            print(
                f"  ✗ {case.question[:50]}…  →  {normalize(answer)}  "
                f"(expected {normalize(case.expected)})"
            )
    return passed, len(cases)


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> None:
    print("Stage 01 — Eval Harness (scripted stub)\n")
    passed, total = run_eval(CASES, inner_agent)
    print(f"\nPassed: {passed}/{total}")


if __name__ == "__main__":
    main()
