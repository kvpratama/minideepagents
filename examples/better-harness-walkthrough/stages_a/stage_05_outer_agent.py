"""Stage 05 — Outer Agent.

Introduce the outer Deep Agent.  It reads a virtual workspace, edits
``/current/prompt.txt``, and proposes an improved prompt.  No loop yet —
exactly one proposal, then read the result back.

Run::

    uv run python stages_a/stage_05_outer_agent.py
"""

from __future__ import annotations

import importlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
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
        expected="38",
    ),
    EvalCase(
        question="If you divide 144 by 12, what do you get?",
        expected="14",
    ),
    EvalCase(
        question="A train travels at 60 mph for 2.5 hours. How many miles does it cover?",
        expected="152",
    ),
    # EvalCase(
    #     question="What is 15% of 200?",
    #     expected="30",
    # ),
    # EvalCase(
    #     question="A recipe needs 2/3 cup of sugar. If you triple the recipe, how many cups of sugar do you need?",
    #     expected="2",
    # ),
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
) -> tuple[int, int, list[str]]:
    """Run cases and return (passed, total, failure_descriptions)."""
    passed = 0
    failures: list[str] = []
    for case in cases:
        answer = agent(case.question)  # ty:ignore[call-non-callable]
        if normalize(answer) == normalize(case.expected):
            passed += 1
            print(f"  ✓ {case.question[:50]}…  →  {normalize(answer)}")
        else:
            failures.append(
                f"Q: {case.question}  Got: {normalize(answer)}  Expected: {normalize(case.expected)}"
            )
            print(
                f"  ✗ {case.question[:50]}…  →  {normalize(answer)}  "
                f"(expected {normalize(case.expected)})"
            )
    return passed, len(cases), failures


# ── Outer agent (the new concept) ────────────────────────────────────────────

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
"""


def propose(current_prompt: str, failures: list[str]) -> str:
    """Run the outer Deep Agent once and return the proposed prompt.

    Args:
        current_prompt: The current system prompt text.
        failures: Descriptions of failing eval cases.

    Returns:
        The proposed prompt text read back from the workspace.
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
        f"Current score: {len(failures)} failures out of {len(CASES)} cases.",
        "",
        "## Failing cases",
        "",
    ]
    for failure in failures:
        task_lines.append(f"- {failure}")
    if not failures:
        task_lines.append("- None (all passing)")
    (workspace / "task.md").write_text("\n".join(task_lines) + "\n")

    backend = FilesystemBackend(root_dir=str(workspace), virtual_mode=True)
    agent = create_deep_agent(
        model=get_model(),
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
    print("Stage 05 — Outer Agent (one proposal, no loop)\n")

    # 1. Baseline
    baseline = baseline_variant(SURFACES)
    print("=== Baseline ===\n")
    baseline_passed, total, failures = run_eval(CASES, inner_agent)
    print(f"\nBaseline: {baseline_passed}/{total}")

    # 2. Propose
    print("\n=== Outer agent proposing… ===\n")
    proposed_prompt = propose(baseline.values["prompt"], failures)
    print(f"Proposed prompt:\n{proposed_prompt}\n")

    # 3. Patch and re-eval
    proposed = Variant(label="proposed", values={"prompt": proposed_prompt})
    apply_variant(proposed, SURFACES)
    print("=== Proposed variant ===\n")
    proposed_passed, total, _ = run_eval(CASES, inner_agent)
    print(f"\nProposed: {proposed_passed}/{total}")

    # 4. Restore baseline
    apply_variant(baseline, SURFACES)

    # 5. Summary
    delta = proposed_passed - baseline_passed
    direction = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
    print(f"\nDelta: {direction} {abs(delta)} (baseline {baseline_passed}/{total} → proposed {proposed_passed}/{total})")


if __name__ == "__main__":
    main()
