"""Stage 14 — Runner Abstraction.

Introduce a ``Runner`` ``Protocol`` so the harness loop is independent of
how cases are executed.  Two backends are provided:

- ``PytestRunner`` — pass/fail per case (binary score), the default that
  mirrors a pytest-style runner.
- ``HarborRunner`` — continuous 0..1 score per case with a configurable
  ``pass_threshold``, mirroring how Harbor-style runners report rewards.

Both produce ``SplitResult`` so the loop calling ``runner.run_split(...)``
doesn't care which one is in use.

Run::

    uv run python stages_b/stage_14_runner_abstraction.py
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from langchain.agents import create_agent
from langchain.tools import tool

from config import get_model

# ── Data model ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    question: str
    expected: str
    split: Literal["train", "holdout"]


@dataclass(frozen=True)
class Surface:
    name: str
    target: str
    base_value: str


@dataclass(frozen=True)
class Variant:
    label: str
    values: dict[str, str]


@dataclass
class CaseOutcome:
    case_id: str
    score: float
    passed: bool
    failure_message: str | None = None


@dataclass
class SplitResult:
    """The runner's contract — same shape regardless of backend."""

    split: str
    variant: str
    passed: int
    total: int
    outcomes: list[CaseOutcome] = field(default_factory=list)

    def failures(self) -> list[str]:
        return [
            f"{o.case_id}: {o.failure_message or 'failed'}"
            for o in self.outcomes
            if not o.passed
        ]


@dataclass(frozen=True)
class Experiment:
    name: str
    runner: Literal["pytest", "harbor"]
    runner_config: dict[str, Any]
    surfaces: dict[str, Surface]
    cases: tuple[EvalCase, ...]

    def cases_for_split(self, split: str) -> list[EvalCase]:
        return [c for c in self.cases if c.split == split]


# ── Inner agent (shared by both runners) ────────────────────────────────────


BASE_PROMPT = "You are a helpful assistant."


@tool
def calculator(expression: str) -> str:
    """Evaluate a Python-syntax math expression like ``3 * 12``.

    Args:
        expression: A simple arithmetic expression.
    """
    allowed = set("0123456789+-*/.() ")
    if not all(ch in allowed for ch in expression):
        return f"Error: invalid characters in expression: {expression}"
    try:
        return str(eval(expression))  # noqa: S307
    except Exception as exc:
        return f"Error: {exc}"


def patch_module_attrs(overrides: dict[str, str]) -> None:
    for target, value in overrides.items():
        module_name, _, attribute = target.partition(":")
        module = importlib.import_module(module_name)
        setattr(module, attribute, value)


def apply_variant(experiment: Experiment, variant: Variant) -> None:
    overrides = {s.target: variant.values[name] for name, s in experiment.surfaces.items()}
    patch_module_attrs(overrides)


def inner_agent(question: str) -> str:
    agent = create_agent(get_model(), tools=[calculator], system_prompt=BASE_PROMPT)
    return agent.invoke({"messages": [{"role": "user", "content": question}]})["messages"][-1].content


def normalize(text: str) -> str:
    text = text.strip()
    nums = re.findall(r"-?\d+\.?\d*", text)
    if nums:
        text = nums[-1]
    if text.endswith(".0"):
        text = text[:-2]
    return text


# ── Runner Protocol ─────────────────────────────────────────────────────────


class Runner(Protocol):
    """The contract every backend implements.

    The loop only ever calls these two methods.  Anything else — pytest
    invocation, harbor task submission, subprocess management — is
    encapsulated inside the implementation.
    """

    def collect_inventory(self, experiment: Experiment) -> list[str]:
        """List the case ids this runner can execute for the experiment."""
        ...

    def run_split(
        self,
        *,
        experiment: Experiment,
        variant: Variant,
        split: str,
    ) -> SplitResult:
        """Apply the variant, run one split's cases, return aggregated results."""
        ...


# ── PytestRunner — binary pass/fail per case ────────────────────────────────


class PytestRunner:
    """A pytest-style runner: each case scores 0 or 1.

    Mirrors the behavior of an in-process pytest collection: every case
    is a test, every test passes or fails.  The full Tier C runner shells
    out to actual ``pytest`` with a ``--junitxml`` parser; this
    walkthrough version stays in-process so the lesson is the protocol,
    not the subprocess plumbing.
    """

    def collect_inventory(self, experiment: Experiment) -> list[str]:
        return [c.case_id for c in experiment.cases]

    def run_split(self, *, experiment: Experiment, variant: Variant, split: str) -> SplitResult:
        apply_variant(experiment, variant)
        outcomes: list[CaseOutcome] = []
        for case in experiment.cases_for_split(split):
            actual = inner_agent(case.question)
            ok = normalize(actual) == normalize(case.expected)
            outcomes.append(
                CaseOutcome(
                    case_id=case.case_id,
                    score=1.0 if ok else 0.0,
                    passed=ok,
                    failure_message=None if ok else f"got {normalize(actual)!r}, expected {case.expected!r}",
                )
            )
        passed = sum(1 for o in outcomes if o.passed)
        return SplitResult(
            split=split,
            variant=variant.label,
            passed=passed,
            total=len(outcomes),
            outcomes=outcomes,
        )


# ── HarborRunner — continuous score with a pass_threshold ───────────────────


class HarborRunner:
    """A Harbor-style runner: each case gets a continuous 0..1 score.

    The runner config carries a ``pass_threshold`` — scores at or above
    pass; scores below fail.  Useful when an eval rewards near-misses
    differently from total misses.
    """

    def collect_inventory(self, experiment: Experiment) -> list[str]:
        return [c.case_id for c in experiment.cases]

    def run_split(self, *, experiment: Experiment, variant: Variant, split: str) -> SplitResult:
        apply_variant(experiment, variant)
        threshold = float(experiment.runner_config.get("pass_threshold", 1.0))
        outcomes: list[CaseOutcome] = []
        for case in experiment.cases_for_split(split):
            actual = inner_agent(case.question)
            score = _similarity_score(normalize(actual), normalize(case.expected))
            ok = score >= threshold
            outcomes.append(
                CaseOutcome(
                    case_id=case.case_id,
                    score=score,
                    passed=ok,
                    failure_message=None if ok else f"score {score:.2f} < threshold {threshold:.2f}",
                )
            )
        passed = sum(1 for o in outcomes if o.passed)
        return SplitResult(
            split=split,
            variant=variant.label,
            passed=passed,
            total=len(outcomes),
            outcomes=outcomes,
        )


def _similarity_score(actual: str, expected: str) -> float:
    """Toy 0..1 similarity score for the walkthrough.

    1.0 if the strings match exactly; 0.5 if the integer part matches;
    0.0 otherwise.  Real Harbor runners use task-specific rewards.
    """
    if actual == expected:
        return 1.0
    actual_int = re.findall(r"-?\d+", actual)
    expected_int = re.findall(r"-?\d+", expected)
    if actual_int and expected_int and actual_int[-1] == expected_int[-1]:
        return 0.5
    return 0.0


# ── Factory ─────────────────────────────────────────────────────────────────


def build_runner(experiment: Experiment) -> Runner:
    """Build the configured runner."""
    if experiment.runner == "pytest":
        return PytestRunner()
    if experiment.runner == "harbor":
        return HarborRunner()
    msg = f"unknown runner {experiment.runner!r}"
    raise ValueError(msg)


# ── Demo experiments — same loop, two runners ───────────────────────────────


def baseline_variant(experiment: Experiment) -> Variant:
    return Variant(
        label="baseline",
        values={name: s.base_value for name, s in experiment.surfaces.items()},
    )


def hand_crafted_variant(experiment: Experiment) -> Variant:
    return Variant(
        label="improved",
        values={
            name: (
                "You are a careful math assistant. ALWAYS call the calculator "
                "tool for any arithmetic, then return ONLY the final number."
            )
            for name in experiment.surfaces
        },
    )


SHARED_CASES = (
    EvalCase("bakery", "A bakery sells 3 cakes at $12 each. What is the total revenue?", "36", "train"),
    EvalCase("divide", "If you divide 144 by 12, what do you get?", "12", "train"),
    EvalCase("speed", "A train travels at 60 mph for 2.5 hours. How many miles does it cover?", "150", "holdout"),
    EvalCase("percent", "What is 15% of 200?", "30", "holdout"),
)

SHARED_SURFACES = {
    "prompt": Surface(
        name="prompt",
        target="stages_b.stage_14_runner_abstraction:BASE_PROMPT",
        base_value=BASE_PROMPT,
    ),
}


def make_pytest_experiment() -> Experiment:
    return Experiment(
        name="math-pytest",
        runner="pytest",
        runner_config={},
        surfaces=SHARED_SURFACES,
        cases=SHARED_CASES,
    )


def make_harbor_experiment() -> Experiment:
    return Experiment(
        name="math-harbor",
        runner="harbor",
        runner_config={"pass_threshold": 1.0},
        surfaces=SHARED_SURFACES,
        cases=SHARED_CASES,
    )


def demo(experiment: Experiment) -> None:
    runner = build_runner(experiment)
    print(f"\n── Runner: {type(runner).__name__} (config={experiment.runner_config}) ──")
    print(f"Inventory: {runner.collect_inventory(experiment)}")

    baseline = baseline_variant(experiment)
    base_train = runner.run_split(experiment=experiment, variant=baseline, split="train")
    base_hold = runner.run_split(experiment=experiment, variant=baseline, split="holdout")
    print(
        f"  baseline → train {base_train.passed}/{base_train.total} "
        f"holdout {base_hold.passed}/{base_hold.total}"
    )

    improved = hand_crafted_variant(experiment)
    imp_train = runner.run_split(experiment=experiment, variant=improved, split="train")
    imp_hold = runner.run_split(experiment=experiment, variant=improved, split="holdout")
    print(
        f"  improved → train {imp_train.passed}/{imp_train.total} "
        f"holdout {imp_hold.passed}/{imp_hold.total}"
    )

    # Show that the loop's contract is identical for both runners:
    for outcome in imp_train.outcomes:
        verdict = "✓" if outcome.passed else "✗"
        print(f"    {verdict} {outcome.case_id}: score={outcome.score:.2f}")


def main() -> None:
    print("Stage 14 — Runner Abstraction\n")
    print("Two runners, one harness — the loop calls runner.run_split() and")
    print("never asks which backend it got.\n")
    print(f"Path: {Path(__file__)}")

    demo(make_pytest_experiment())
    demo(make_harbor_experiment())

    print("\n" + "=" * 60)
    print("Both runners returned SplitResult — that's the only thing the")
    print("hill-climbing loop actually depends on.")


if __name__ == "__main__":
    main()
