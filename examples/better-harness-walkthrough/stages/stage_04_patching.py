"""Stage 04 — Patching.

Apply a ``Variant`` to the live inner agent via ``patch_module_attrs()``.
This is the bridge from "we have a Variant object" to "the inner agent
actually uses the new values."

Run::

    uv run python stages/stage_04_patching.py
"""

from __future__ import annotations

import importlib
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
    """One editable surface in the harness."""

    name: str
    target: str
    base_value: str


@dataclass(frozen=True)
class Variant:
    """A frozen snapshot of all surface values plus a label."""

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


# ── System prompt (module-level — patchable) ─────────────────────────────────

BASE_PROMPT = "You are a helpful assistant."

PROMPT_SURFACE = Surface(
    name="prompt",
    target=f"{__name__}:BASE_PROMPT",
    base_value=BASE_PROMPT,
)

SURFACES = [PROMPT_SURFACE]


def baseline_variant(surfaces: list[Surface]) -> Variant:
    """Build the baseline variant from declared surfaces."""
    return Variant(
        label="baseline",
        values={s.name: s.base_value for s in surfaces},
    )


# ── Patching ─────────────────────────────────────────────────────────────────


def patch_module_attrs(overrides: dict[str, str]) -> None:
    """Apply module:attribute → value overrides via setattr.

    Each key in *overrides* must be a ``"module.path:ATTRIBUTE"`` string.
    The module is imported and the attribute is set to the given value.

    Args:
        overrides: Mapping of ``module:attribute`` targets to new values.
    """
    for target, value in overrides.items():
        module_name, separator, attribute = target.partition(":")
        if not separator:
            msg = f"invalid target {target!r}; expected module:attribute"
            raise ValueError(msg)
        module = importlib.import_module(module_name)
        setattr(module, attribute, value)


def apply_variant(variant: Variant, surfaces: list[Surface]) -> None:
    """Patch all surfaces from a variant's values."""
    overrides = {surface.target: variant.values[surface.name] for surface in surfaces}
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
    """Build the inner agent using the current (possibly patched) BASE_PROMPT."""
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

IMPROVED_PROMPT = """\
You are a math assistant.  You have a calculator tool.

Rules:
- ALWAYS use the calculator tool for ANY arithmetic — never do mental math.
- Extract the mathematical expression from the word problem.
- Call the calculator with the expression.
- Return only the final numeric answer.
"""


def main() -> None:
    print("Stage 04 — Patching\n")

    # 1. Baseline eval
    baseline = baseline_variant(SURFACES)
    print(f"=== Baseline (prompt: {baseline.values['prompt']!r}) ===\n")
    baseline_passed, total = run_eval(CASES, inner_agent)
    print(f"\nBaseline: {baseline_passed}/{total}")

    import time; time.sleep(15)
    # 2. Apply the hand-crafted improved variant
    #    KEY ORDER: patch FIRST, then build and invoke the agent.
    improved = Variant(label="improved", values={"prompt": IMPROVED_PROMPT})
    apply_variant(improved, SURFACES)
    print("\n=== Improved (prompt patched) ===")
    print(f"Current BASE_PROMPT: {BASE_PROMPT!r}\n")
    improved_passed, total = run_eval(CASES, inner_agent)
    print(f"\nImproved: {improved_passed}/{total}")

    # 3. Restore baseline
    apply_variant(baseline, SURFACES)
    print(f"\nRestored BASE_PROMPT: {BASE_PROMPT!r}")

    # 4. Summary
    delta = improved_passed - baseline_passed
    direction = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
    print(
        f"\nDelta: {direction} {abs(delta)} (baseline {baseline_passed}/{total} → improved {improved_passed}/{total})"
    )


if __name__ == "__main__":
    main()
