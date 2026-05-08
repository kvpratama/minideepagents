"""Stage 02 — Inner Agent.

Replace the scripted stub with a real LangChain agent that has a calculator
tool.  The deliberately vague system prompt ("You are a helpful assistant.")
means the agent will sometimes do mental math instead of reaching for the
tool — giving us a baseline score to improve.

Run::

    uv run python stages/stage_02_inner_agent.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.tools import tool
from config import get_model

# ── Data model (re-introduced; no cross-stage imports) ───────────────────────


@dataclass
class EvalCase:
    """One eval case with a question and a known-good answer."""

    question: str
    expected: str


# ── Eval suite ───────────────────────────────────────────────────────────────

CASES = [
    EvalCase(
        question="A warehouse has 847 pallets, each containing 136 items. How many items total?",
        expected="115192",
    ),
    EvalCase(
        question="A factory produces 4,725 units in 7 days. If each unit costs $18, what is the total weekly revenue?",
        expected="85050",
    ),
    EvalCase(
        question="A city's population grew by 3.7% from 284,500. What is the new population?",
        expected="295026.5",
    ),
    EvalCase(
        question="You buy 23 notebooks at $4.75 each and 15 pens at $1.60 each. What is the total cost?",
        expected="133.25",
    ),
    EvalCase(
        question="If 98,765 widgets are packed into boxes of 347 each, how many full boxes are there?",
        expected="284",
    ),
]


# ── System prompt (module-level so it can be patched in later stages) ────────

BASE_PROMPT = "You are a helpful assistant."


# ── Tool ─────────────────────────────────────────────────────────────────────


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the numeric result.

    Args:
        expression: A Python-syntax math expression like ``3 * 12`` or
            ``144 / 12``.
    """
    # Restricted eval: allow only math operations.
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
    """Build the inner LangChain agent with the current BASE_PROMPT."""
    model = get_model()
    return create_agent(model, tools=[calculator], system_prompt=BASE_PROMPT)


def inner_agent(question: str) -> str:
    """Run one question through the inner agent and return the answer text."""
    agent = build_inner_agent()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
    )
    return result["messages"][-1].content


# ── Runner (re-introduced; no cross-stage imports) ───────────────────────────


def normalize(text: str) -> str:
    """Normalize an answer for comparison."""
    text = text.strip()
    text = re.sub(r",\s*", "", text)
    numbers = re.findall(r"-?\d+\.?\d*", text)
    if numbers:
        text = numbers[-1]
    text = text.rstrip(".")
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
    print("Stage 02 — Inner Agent (LangChain + calculator)\n")
    passed, total = run_eval(CASES, inner_agent)
    print(f"\nBaseline: {passed}/{total}")


if __name__ == "__main__":
    main()
