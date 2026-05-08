"""Stage 12 — Scorecard Split.

Introduce an optional third split — ``scorecard`` — that the outer loop
*never* sees during optimization.  Scorecard runs only on the baseline
and the final variant.  It's the report-card metric, deliberately
separate from the train + holdout signal that drives optimization.

Run::

    uv run python stages_b/stage_12_scorecard_split.py
"""

from __future__ import annotations

import importlib
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.tools import tool

from config import get_model, get_settings

MAX_ITERATIONS = 2

Split = Literal["train", "holdout", "scorecard"]
VISIBLE_SPLITS: set[Split] = {"train"}
OPTIMIZATION_SPLITS: set[Split] = {"train", "holdout"}

# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class EvalCase:
    """One eval case."""

    question: str
    expected: str
    split: Split


@dataclass(frozen=True)
class Surface:
    """One editable surface."""

    name: str
    kind: Literal["module_attr", "workspace_file"]
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
    split: Split
    variant: str
    passed: int
    total: int
    failures: list[str]


# ── Eval suite — train / holdout / scorecard ────────────────────────────────

CASES = [
    # train: visible to the outer agent
    EvalCase("A bakery sells 3 cakes at $12 each. What is the total revenue?", "36", "train"),
    EvalCase("If you divide 144 by 12, what do you get?", "12", "train"),
    # holdout: hidden but used to score every candidate
    EvalCase("A train travels at 60 mph for 2.5 hours. How many miles does it cover?", "150", "holdout"),
    EvalCase("What is 15% of 200?", "30", "holdout"),
    # scorecard: never seen by the loop — only baseline + final are scored on it
    EvalCase("If a rectangle is 7 by 4, what is its area?", "28", "scorecard"),
    EvalCase("What is 9 squared minus 3 cubed?", "54", "scorecard"),
]

BASE_PROMPT = "You are a helpful assistant."

SURFACES = [
    Surface(
        name="prompt",
        kind="module_attr",
        target="stages_b.stage_12_scorecard_split:BASE_PROMPT",
        base_value=BASE_PROMPT,
        filename="prompt.txt",
    ),
]


def baseline_variant() -> Variant:
    return Variant(label="baseline", values={s.name: s.base_value for s in SURFACES})


# ── Patching ─────────────────────────────────────────────────────────────────


def patch_module_attrs(overrides: dict[str, str]) -> None:
    for target, value in overrides.items():
        module_name, _, attribute = target.partition(":")
        module = importlib.import_module(module_name)
        setattr(module, attribute, value)


def apply_variant(variant: Variant) -> None:
    overrides = {s.target: variant.values[s.name] for s in SURFACES if s.kind == "module_attr"}
    patch_module_attrs(overrides)


# ── Tool + inner agent ──────────────────────────────────────────────────────


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


def inner_agent(question: str) -> str:
    agent = create_agent(get_model(), tools=[calculator], prompt=BASE_PROMPT)
    return agent.invoke({"messages": [{"role": "user", "content": question}]})["messages"][-1].content


def normalize(text: str) -> str:
    text = text.strip()
    nums = re.findall(r"-?\d+\.?\d*", text)
    if nums:
        text = nums[-1]
    if text.endswith(".0"):
        text = text[:-2]
    return text


def run_eval(variant: Variant, *, split: Split) -> SplitResult:
    apply_variant(variant)
    filtered = [c for c in CASES if c.split == split]
    passed = 0
    failures: list[str] = []
    for case in filtered:
        ans = inner_agent(case.question)
        if normalize(ans) == normalize(case.expected):
            passed += 1
        else:
            failures.append(f"Q: {case.question}  Got: {normalize(ans)}  Expected: {case.expected}")
    return SplitResult(split=split, variant=variant.label, passed=passed, total=len(filtered), failures=failures)


# ── Outer agent ──────────────────────────────────────────────────────────────

OUTER_SYSTEM_PROMPT = """\
You are an outer-loop Deep Agent that improves an inner math agent's prompt.

Read /task.md, then edit /current/prompt.txt.  Tell the inner agent to
always call the `calculator` tool for any arithmetic.  Keep it concise
and general — do not encode specific question/answer pairs.
"""


def propose(current_value: str, train_failures: list[str], iteration: int) -> str:
    workspace = Path(tempfile.mkdtemp(prefix=f"bh_stage12_iter{iteration}_"))
    (workspace / "current").mkdir()
    (workspace / "current" / "prompt.txt").write_text(current_value)
    task = ["# Task", "", f"Iteration {iteration}.", "", "## Failing train cases", ""]
    task.extend(f"- {f}" for f in train_failures) if train_failures else task.append("- None")
    (workspace / "task.md").write_text("\n".join(task) + "\n")

    settings = get_settings()
    backend = FilesystemBackend(root_dir=str(workspace), virtual_mode=True)
    agent = create_deep_agent(model=settings.model, system_prompt=OUTER_SYSTEM_PROMPT, backend=backend)
    agent.invoke(
        {"messages": [{"role": "user", "content": "Read /task.md, then improve /current/prompt.txt."}]},
        config={"recursion_limit": 50},
    )
    out = (workspace / "current" / "prompt.txt").read_text().strip()
    shutil.rmtree(workspace, ignore_errors=True)
    return out


# ── Loop — scorecard is intentionally not consulted here ────────────────────


def loop(*, max_iterations: int = MAX_ITERATIONS) -> tuple[Variant, Variant]:
    """Run the optimization loop.

    Returns ``(baseline, final)``.  Note: the loop only ever runs ``train``
    and ``holdout`` — the scorecard is held out and scored separately.
    """
    baseline = baseline_variant()
    base_train = run_eval(baseline, split="train")
    base_holdout = run_eval(baseline, split="holdout")
    print(f"Baseline: train {base_train.passed}/{base_train.total}  holdout {base_holdout.passed}/{base_holdout.total}\n")

    current = baseline
    cur_train, cur_holdout = base_train, base_holdout

    for i in range(max_iterations):
        print(f"── Iteration {i} ──")
        proposed = propose(current.values["prompt"], cur_train.failures, iteration=i)
        candidate = Variant(label=f"iter-{i:03d}", values={"prompt": proposed})

        cand_train = run_eval(candidate, split="train")
        cand_holdout = run_eval(candidate, split="holdout")
        cand_combined = cand_train.passed + cand_holdout.passed
        cur_combined = cur_train.passed + cur_holdout.passed

        accepted = cand_combined > cur_combined
        verdict = "✓" if accepted else "✗"
        print(
            f"  {verdict} train {cand_train.passed}/{cand_train.total}  "
            f"holdout {cand_holdout.passed}/{cand_holdout.total}  "
            f"combined {cand_combined} {'>' if accepted else '<='} {cur_combined}\n"
        )
        if accepted:
            current = candidate
            cur_train, cur_holdout = cand_train, cand_holdout
        else:
            apply_variant(current)

    return baseline, current


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> None:
    print("Stage 12 — Scorecard Split (held-out report-card metric)\n")
    splits = {c.split for c in CASES}
    print(f"Splits in suite: {sorted(splits)}")
    print(f"Splits the loop optimizes against: {sorted(OPTIMIZATION_SPLITS)}\n")

    baseline, final = loop()

    # Scorecard runs ONLY here — once on baseline, once on final.
    print("\n── Scorecard (run once on baseline + final, never during the loop) ──")
    base_score = run_eval(baseline, split="scorecard")
    final_score = run_eval(final, split="scorecard")

    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"Baseline scorecard: {base_score.passed}/{base_score.total}")
    print(f"Final    scorecard: {final_score.passed}/{final_score.total}")
    print()
    print("The scorecard delta is the metric you can trust as a final")
    print("report number — the loop never optimized against it.")


if __name__ == "__main__":
    main()
