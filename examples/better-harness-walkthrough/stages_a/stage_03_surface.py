"""Stage 03 — Surface & Variant.

Introduce ``Surface`` and ``Variant`` — the data model that makes "what is
editable" first-class.  We don't *apply* a variant yet (that's stage 04);
we just declare the baseline and print it.

Run::

    uv run python stages_a/stage_03_surface.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.tools import tool

from config import get_model

# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class EvalCase:
    """One eval case with a question and a known-good answer."""

    question: str
    expected: str


@dataclass(frozen=True)
class Surface:
    """One editable surface in the harness.

    Attributes:
        name: Human-readable name (e.g. ``"prompt"``).
        target: Where to apply the value, in ``module:attribute`` format.
        base_value: The default value before any edit.
    """

    name: str
    target: str
    base_value: str


@dataclass(frozen=True)
class Variant:
    """A frozen snapshot of all surface values plus a label.

    Attributes:
        label: Human-readable identifier (e.g. ``"baseline"``).
        values: Mapping of surface name → current value.
    """

    label: str
    values: dict[str, str]


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


# ── System prompt ────────────────────────────────────────────────────────────

BASE_PROMPT = "You are a helpful assistant."


# ── Surface declaration ─────────────────────────────────────────────────────

PROMPT_SURFACE = Surface(
    name="prompt",
    target="stages.stage_03_surface:BASE_PROMPT",
    base_value=BASE_PROMPT,
)

SURFACES = [PROMPT_SURFACE]


def baseline_variant(surfaces: list[Surface]) -> Variant:
    """Build the baseline variant from the declared surfaces."""
    return Variant(
        label="baseline",
        values={s.name: s.base_value for s in surfaces},
    )


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
) -> tuple[int, int]:
    """Run cases through an agent callable and return (passed, total)."""
    passed = 0
    for case in cases:
        answer = agent(case.question)  # ty:ignore[call-non-callable]
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
    print("Stage 03 — Surface & Variant\n")

    baseline = baseline_variant(SURFACES)
    print(f"Surfaces declared: {[s.name for s in SURFACES]}")
    print(f"Baseline variant:  {baseline.label}")
    for name, value in baseline.values.items():
        print(f"  {name}: {value!r}")

    print("\nRunning eval with baseline prompt…\n")
    passed, total = run_eval(CASES, inner_agent)
    print(f"\nBaseline: {passed}/{total}")


if __name__ == "__main__":
    main()
