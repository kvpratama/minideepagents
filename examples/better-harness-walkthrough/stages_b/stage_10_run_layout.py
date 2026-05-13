"""Stage 10 — Run Layout.

Introduce ``RunLayout`` — a class that owns the on-disk artifact tree for
one experiment run.  Every variant gets a JSON snapshot, every iteration
gets a ``decision.{json,md}``, and the final report is written as
``report.{json,md}``.

Run::

    uv run python stages_b/stage_10_run_layout.py
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.tools import tool

from config import get_model, get_outer_model

MAX_ITERATIONS = 2

# ── Data model ───────────────────────────────────────────────────────────────


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
    kind: Literal["module_attr", "workspace_file"]
    target: str
    base_value: str
    filename: str


@dataclass(frozen=True)
class Variant:
    """A frozen snapshot of surface values."""

    label: str
    values: dict[str, str]
    changed_surfaces: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "values": self.values,
            "changed_surfaces": list(self.changed_surfaces),
        }


@dataclass
class SplitResult:
    """Result of running one split."""

    split: str
    variant: str
    passed: int
    total: int
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IterationDecision:
    """One iteration's accept/reject decision."""

    iteration: int
    starting_variant: str
    candidate_variant: str
    changed_surfaces: list[str]
    train_passed: int
    train_total: int
    holdout_passed: int
    holdout_total: int
    combined: int
    accepted: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunReport:
    """Final report for one run."""

    created_at: str
    baseline: Variant
    final: Variant
    baseline_train: SplitResult
    baseline_holdout: SplitResult
    final_train: SplitResult
    final_holdout: SplitResult
    decisions: list[IterationDecision]

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "baseline": self.baseline.to_dict(),
            "final": self.final.to_dict(),
            "baseline_train": self.baseline_train.to_dict(),
            "baseline_holdout": self.baseline_holdout.to_dict(),
            "final_train": self.final_train.to_dict(),
            "final_holdout": self.final_holdout.to_dict(),
            "decisions": [d.to_dict() for d in self.decisions],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Run report",
            "",
            f"- Created at: `{self.created_at}`",
            f"- Final changed surfaces: `{', '.join(self.final.changed_surfaces) or 'none'}`",
            "",
            "| Split | Baseline | Final |",
            "| --- | --- | --- |",
            f"| Train | `{self.baseline_train.passed}/{self.baseline_train.total}` | `{self.final_train.passed}/{self.final_train.total}` |",
            f"| Holdout | `{self.baseline_holdout.passed}/{self.baseline_holdout.total}` | `{self.final_holdout.passed}/{self.final_holdout.total}` |",
            "",
            "## Iterations",
            "",
        ]
        for d in self.decisions:
            verdict = "accepted" if d.accepted else "rejected"
            lines.append(
                f"- Iteration {d.iteration}: {verdict} `{d.candidate_variant}` "
                f"(train {d.train_passed}/{d.train_total}, "
                f"holdout {d.holdout_passed}/{d.holdout_total}, "
                f"changed {d.changed_surfaces or ['none']})"
            )
        return "\n".join(lines) + "\n"


# ── RunLayout ────────────────────────────────────────────────────────────────


class RunLayout:
    """Filesystem layout for one experiment run.

    Layout::

        <root>/
          manifest.json
          variants/
            <label>.json
          iterations/
            000/
              decision.json
              decision.md
          report.json
          report.md
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def variants_dir(self) -> Path:
        return self.root / "variants"

    def variant_path(self, label: str) -> Path:
        return self.variants_dir / f"{label}.json"

    def iteration_dir(self, iteration: int) -> Path:
        return self.root / "iterations" / f"{iteration:03d}"

    def write_manifest(self, *, surfaces: list[Surface], max_iterations: int) -> None:
        payload = {
            "created_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "max_iterations": max_iterations,
            "surfaces": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "target": s.target,
                    "filename": s.filename,
                }
                for s in surfaces
            ],
        }
        (self.root / "manifest.json").write_text(json.dumps(payload, indent=2) + "\n")

    def write_variant(self, variant: Variant) -> None:
        self.variants_dir.mkdir(parents=True, exist_ok=True)
        self.variant_path(variant.label).write_text(
            json.dumps(variant.to_dict(), indent=2, sort_keys=True) + "\n"
        )

    def write_decision(self, decision: IterationDecision) -> None:
        d = self.iteration_dir(decision.iteration)
        d.mkdir(parents=True, exist_ok=True)
        (d / "decision.json").write_text(
            json.dumps(decision.to_dict(), indent=2) + "\n"
        )
        verdict = "accepted" if decision.accepted else "rejected"
        md = (
            f"# Iteration {decision.iteration}\n\n"
            f"- Starting variant: `{decision.starting_variant}`\n"
            f"- Candidate variant: `{decision.candidate_variant}`\n"
            f"- Decision: `{verdict}`\n"
            f"- Train: `{decision.train_passed}/{decision.train_total}`\n"
            f"- Holdout: `{decision.holdout_passed}/{decision.holdout_total}`\n"
            f"- Combined: `{decision.combined}`\n"
            f"- Changed surfaces: `{', '.join(decision.changed_surfaces) or 'none'}`\n"
            f"- Reason: {decision.reason}\n"
        )
        (d / "decision.md").write_text(md)

    def write_report(self, report: RunReport) -> None:
        (self.root / "report.json").write_text(
            json.dumps(report.to_dict(), indent=2) + "\n"
        )
        (self.root / "report.md").write_text(report.to_markdown())


# ── Eval suite + surfaces ────────────────────────────────────────────────────

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

BASE_PROMPT = "You are a helpful assistant."

SURFACES = [
    Surface(
        name="prompt",
        kind="module_attr",
        target=f"{__name__}:BASE_PROMPT",
        base_value=BASE_PROMPT,
        filename="prompt.txt",
    ),
]


def baseline_variant() -> Variant:
    return Variant(label="baseline", values={s.name: s.base_value for s in SURFACES})


def build_variant(label: str, values: dict[str, str]) -> Variant:
    changed = tuple(sorted(s.name for s in SURFACES if values[s.name] != s.base_value))
    return Variant(label=label, values=values, changed_surfaces=changed)


# ── Patching ─────────────────────────────────────────────────────────────────


def patch_module_attrs(overrides: dict[str, str]) -> None:
    for target, value in overrides.items():
        module_name, _, attribute = target.partition(":")
        module = importlib.import_module(module_name)
        setattr(module, attribute, value)


def apply_variant(variant: Variant) -> None:
    overrides = {
        s.target: variant.values[s.name] for s in SURFACES if s.kind == "module_attr"
    }
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
    agent = create_agent(get_model(), tools=[calculator], system_prompt=BASE_PROMPT)
    return agent.invoke({"messages": [{"role": "user", "content": question}]})[
        "messages"
    ][-1].content


def normalize(text: str) -> str:
    text = text.strip()
    nums = re.findall(r"-?\d+\.?\d*", text)
    if nums:
        text = nums[-1]
    if text.endswith(".0"):
        text = text[:-2]
    return text


def run_eval(cases: list[EvalCase], variant: Variant, *, split: str) -> SplitResult:
    apply_variant(variant)
    filtered = [c for c in cases if c.split == split]
    passed = 0
    failures: list[str] = []
    for case in filtered:
        ans = inner_agent(case.question)
        if normalize(ans) == normalize(case.expected):
            passed += 1
        else:
            failures.append(
                f"Q: {case.question}  Got: {normalize(ans)}  Expected: {case.expected}"
            )
    return SplitResult(
        split=split,
        variant=variant.label,
        passed=passed,
        total=len(filtered),
        failures=failures,
    )


# ── Outer agent ──────────────────────────────────────────────────────────────

OUTER_SYSTEM_PROMPT = """\
You are an outer-loop Deep Agent that improves an inner agent's prompt.

Read /task.md, then edit /current/prompt.txt.  Write the full improved
prompt — not a diff.  Tell the inner agent to always call the `calculator`
tool for any arithmetic.  Keep it concise and general.
"""


def propose(current_value: str, train_failures: list[str], iteration: int) -> str:
    workspace = Path(tempfile.mkdtemp(prefix=f"bh_stage10_iter{iteration}_"))
    (workspace / "current").mkdir()
    (workspace / "current" / "prompt.txt").write_text(current_value)

    task = ["# Task", "", f"Iteration {iteration}.", "", "## Failing train cases", ""]
    if train_failures:
        task.extend(f"- {f}" for f in train_failures)
    else:
        task.append("- None")
    (workspace / "task.md").write_text("\n".join(task) + "\n")

    backend = FilesystemBackend(root_dir=str(workspace), virtual_mode=True)
    agent = create_deep_agent(
        model=get_outer_model(), system_prompt=OUTER_SYSTEM_PROMPT, backend=backend
    )
    agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Read /task.md, then improve /current/prompt.txt.  Stop when done.",
                }
            ]
        },
        config={"recursion_limit": 50},
    )
    proposed = (workspace / "current" / "prompt.txt").read_text().strip()
    shutil.rmtree(workspace, ignore_errors=True)
    return proposed


# ── Loop ─────────────────────────────────────────────────────────────────────


def loop(layout: RunLayout, *, max_iterations: int = MAX_ITERATIONS) -> RunReport:
    layout.write_manifest(surfaces=SURFACES, max_iterations=max_iterations)

    baseline = baseline_variant()
    layout.write_variant(baseline)

    base_train = run_eval(CASES, baseline, split="train")
    base_holdout = run_eval(CASES, baseline, split="holdout")
    print(
        f"Baseline: train {base_train.passed}/{base_train.total}  holdout {base_holdout.passed}/{base_holdout.total}\n"
    )

    current = baseline
    cur_train, cur_holdout = base_train, base_holdout
    decisions: list[IterationDecision] = []

    for i in range(max_iterations):
        print(f"── Iteration {i} ──")
        proposed = propose(current.values["prompt"], cur_train.failures, iteration=i)
        candidate = build_variant(label=f"iter-{i:03d}", values={"prompt": proposed})
        layout.write_variant(candidate)

        cand_train = run_eval(CASES, candidate, split="train")
        cand_holdout = run_eval(CASES, candidate, split="holdout")
        cand_combined = cand_train.passed + cand_holdout.passed
        cur_combined = cur_train.passed + cur_holdout.passed

        accepted = cand_combined > cur_combined
        reason = (
            f"combined {cand_combined} > {cur_combined}"
            if accepted
            else f"combined {cand_combined} <= {cur_combined}"
        )
        decision = IterationDecision(
            iteration=i,
            starting_variant=current.label,
            candidate_variant=candidate.label,
            changed_surfaces=list(candidate.changed_surfaces),
            train_passed=cand_train.passed,
            train_total=cand_train.total,
            holdout_passed=cand_holdout.passed,
            holdout_total=cand_holdout.total,
            combined=cand_combined,
            accepted=accepted,
            reason=reason,
        )
        layout.write_decision(decision)
        decisions.append(decision)
        print(f"  {'✓' if accepted else '✗'} {reason}\n")

        if accepted:
            current = candidate
            cur_train, cur_holdout = cand_train, cand_holdout
        else:
            apply_variant(current)

    final_train = cur_train
    final_holdout = cur_holdout
    report = RunReport(
        created_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
        baseline=baseline,
        final=current,
        baseline_train=base_train,
        baseline_holdout=base_holdout,
        final_train=final_train,
        final_holdout=final_holdout,
        decisions=decisions,
    )
    layout.write_report(report)
    return report


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> None:
    print("Stage 10 — Run Layout (durable on-disk artifacts)\n")
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    root = Path(tempfile.mkdtemp(prefix=f"bh_stage10_run_{timestamp}_"))
    print(f"Run dir: {root}\n")

    layout = RunLayout(root)
    report = loop(layout)

    print("=" * 60)
    print(report.to_markdown())
    print("Artifacts written to:")
    for path in sorted(root.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(root)}")


if __name__ == "__main__":
    main()
