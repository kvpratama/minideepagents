"""Stage 11 — Proposer Workspace.

Materialize a rich workspace for the outer Deep Agent: ``/current/<file>``,
``/task.md`` (the brief), ``/train_cases/<id>.md`` (per failing case
context), ``/history/<iter>.md`` (prior decisions), ``surface_manifest.json``
(how files map back to targets), and ``/proposal.md`` (where the agent
writes its summary).

Run::

    uv run python stages_b/stage_11_proposer_workspace.py
"""

from __future__ import annotations

import contextlib
import importlib
import json
import re
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.tools import tool

from config import get_model, get_settings

MAX_ITERATIONS = 2

# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class EvalCase:
    """One eval case."""

    case_id: str
    question: str
    expected: str
    split: Literal["train", "holdout"]


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
    changed_surfaces: tuple[str, ...] = ()


@dataclass
class CaseOutcome:
    """One case-level outcome."""

    case_id: str
    question: str
    passed: bool
    actual: str
    expected: str


@dataclass
class SplitResult:
    """Result of running one split."""

    split: str
    variant: str
    passed: int
    total: int
    outcomes: list[CaseOutcome] = field(default_factory=list)

    def failing(self) -> list[CaseOutcome]:
        return [o for o in self.outcomes if not o.passed]


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
    proposal_summary: str


# ── Eval suite + surfaces ────────────────────────────────────────────────────

CASES = [
    EvalCase("bakery", "A bakery sells 3 cakes at $12 each. What is the total revenue?", "36", "train"),
    EvalCase("divide", "If you divide 144 by 12, what do you get?", "12", "train"),
    EvalCase("speed", "A train travels at 60 mph for 2.5 hours. How many miles does it cover?", "150", "train"),
    EvalCase("percent", "What is 15% of 200?", "30", "holdout"),
    EvalCase("recipe", "A recipe needs 2/3 cup of sugar. If you triple the recipe, how many cups of sugar do you need?", "2", "holdout"),
]

BASE_PROMPT = "You are a helpful assistant."
WORKSPACE_ROOT: Path | None = None
GUIDANCE_FILENAME = "calculator_guidance.txt"
GUIDANCE_BASE = "Use this tool for arithmetic."

SURFACES = [
    Surface(
        name="prompt",
        kind="module_attr",
        target="stages_b.stage_11_proposer_workspace:BASE_PROMPT",
        base_value=BASE_PROMPT,
        filename="prompt.txt",
    ),
    Surface(
        name="calculator_guidance",
        kind="workspace_file",
        target=GUIDANCE_FILENAME,
        base_value=GUIDANCE_BASE,
        filename=GUIDANCE_FILENAME,
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


@contextlib.contextmanager
def workspace_override_context(workspace_root: Path, overrides: dict[str, str]) -> Iterator[None]:
    backups: dict[Path, str | None] = {}
    try:
        for relative_path, value in overrides.items():
            target = workspace_root / relative_path
            backups[target] = target.read_text() if target.exists() else None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value)
        yield
    finally:
        for target, original in backups.items():
            if original is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(original)


def apply_module_attrs(variant: Variant) -> None:
    overrides = {s.target: variant.values[s.name] for s in SURFACES if s.kind == "module_attr"}
    patch_module_attrs(overrides)


def file_overrides(variant: Variant) -> dict[str, str]:
    return {s.target: variant.values[s.name] for s in SURFACES if s.kind == "workspace_file"}


# ── Tool + inner agent ──────────────────────────────────────────────────────


@tool
def calculator(expression: str) -> str:
    """Evaluate a Python-syntax math expression like ``3 * 12``.

    Args:
        expression: A simple arithmetic expression.
    """
    if WORKSPACE_ROOT is not None:
        guidance_path = WORKSPACE_ROOT / GUIDANCE_FILENAME
        if guidance_path.exists():
            _ = guidance_path.read_text()
    allowed = set("0123456789+-*/.() ")
    if not all(ch in allowed for ch in expression):
        return f"Error: invalid characters in expression: {expression}"
    try:
        return str(eval(expression))  # noqa: S307
    except Exception as exc:
        return f"Error: {exc}"


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


def run_eval(variant: Variant, *, split: str) -> SplitResult:
    apply_module_attrs(variant)
    outcomes: list[CaseOutcome] = []
    with workspace_override_context(WORKSPACE_ROOT, file_overrides(variant)):
        for case in [c for c in CASES if c.split == split]:
            actual = inner_agent(case.question)
            outcomes.append(
                CaseOutcome(
                    case_id=case.case_id,
                    question=case.question,
                    passed=normalize(actual) == normalize(case.expected),
                    actual=normalize(actual),
                    expected=case.expected,
                )
            )
    passed = sum(1 for o in outcomes if o.passed)
    return SplitResult(split=split, variant=variant.label, passed=passed, total=len(outcomes), outcomes=outcomes)


# ── Proposer workspace ──────────────────────────────────────────────────────


@dataclass
class ProposerWorkspace:
    """Materialized workspace handed to the outer Deep Agent."""

    root: Path
    current_dir: Path
    proposal_file: Path
    surface_files: dict[str, Path]


def build_proposer_workspace(
    *,
    current: Variant,
    train_result: SplitResult,
    decisions: list[IterationDecision],
    iteration: int,
    parent_dir: Path,
) -> ProposerWorkspace:
    """Materialize a rich workspace for the outer agent.

    Layout::

        <root>/
          task.md                  — the brief
          surface_manifest.json    — name → {kind, target, file}
          current/<filename>       — one file per editable surface
          train_cases/<id>.md      — failing train case context (no expected)
          history/<iter>.md        — prior iteration summaries
          proposal.md              — agent writes its summary here
    """
    root = parent_dir / f"iter-{iteration:03d}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    # /current/<filename>
    current_dir = root / "current"
    current_dir.mkdir()
    surface_files: dict[str, Path] = {}
    manifest: dict[str, dict[str, str]] = {}
    for surface in SURFACES:
        path = current_dir / surface.filename
        path.write_text(current.values[surface.name])
        surface_files[surface.name] = path
        manifest[surface.name] = {
            "kind": surface.kind,
            "target": surface.target,
            "file": str(path.relative_to(root)),
        }
    (root / "surface_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    # /train_cases/<id>.md — failing cases only, expected hashed out
    train_cases_dir = root / "train_cases"
    train_cases_dir.mkdir()
    for outcome in train_result.failing():
        body = (
            f"# {outcome.case_id}\n\n"
            f"## Question\n\n{outcome.question}\n\n"
            f"## Last actual answer\n\n`{outcome.actual}`\n\n"
            f"## Expected\n\n<!-- hidden — improving the harness against the expected answer overfits -->\n"
        )
        (train_cases_dir / f"{outcome.case_id}.md").write_text(body)

    # /history/<iter>.md — prior decisions
    history_dir = root / "history"
    history_dir.mkdir()
    for past in decisions:
        verdict = "accepted" if past.accepted else "rejected"
        body = (
            f"# Iteration {past.iteration}\n\n"
            f"- Decision: `{verdict}`\n"
            f"- Changed surfaces: `{', '.join(past.changed_surfaces) or 'none'}`\n"
            f"- Train: `{past.train_passed}/{past.train_total}`\n"
            f"- Holdout: `{past.holdout_passed}/{past.holdout_total}`\n"
            f"- Reason: {past.reason}\n\n"
            f"## Proposal summary\n\n{past.proposal_summary or '_none_'}\n"
        )
        (history_dir / f"{past.iteration:03d}.md").write_text(body)

    # /task.md — the brief
    task_lines = [
        "# Task",
        "",
        f"Iteration {iteration} of the optimization loop.",
        "",
        "Edit the files under `/current/` to help the inner math agent pass more eval cases.",
        "",
        "## Editable surfaces",
        "",
    ]
    for surface in SURFACES:
        task_lines.append(f"- `/current/{surface.filename}` — `{surface.name}` ({surface.kind})")
    task_lines.extend(
        [
            "",
            "## Inputs you have",
            "",
            "- `/surface_manifest.json` — how each /current/ file maps back to the inner harness",
            "- `/train_cases/<id>.md` — per failing train case context (expected hidden)",
            "- `/history/<iter>.md` — prior iterations' decisions and summaries",
            "",
            "## Output",
            "",
            "- Edit files under `/current/` to their final form (no diffs, no notes).",
            "- Write a short rationale to `/proposal.md`.",
            "- Stop when both are done.",
        ]
    )
    (root / "task.md").write_text("\n".join(task_lines) + "\n")

    proposal_file = root / "proposal.md"
    proposal_file.write_text("# Proposal\n\n- Summary:\n- Why this should help:\n- Surfaces changed:\n")

    return ProposerWorkspace(
        root=root,
        current_dir=current_dir,
        proposal_file=proposal_file,
        surface_files=surface_files,
    )


# ── Outer agent ──────────────────────────────────────────────────────────────

OUTER_SYSTEM_PROMPT = """\
You are an outer-loop Deep Agent improving an inner agent's harness.

Read /task.md, /surface_manifest.json, and the files under /train_cases/
and /history/.  Then edit the files under /current/ in place — write the
full final content, not diffs.  When done, summarize what you changed in
/proposal.md.  Stop.

Rules:
- Edit only /current/* and /proposal.md.
- Do not invent the expected answer from a train case — the hidden
  expected answers are not provided on purpose.
- Prefer general fixes over case-specific hacks.
"""


def propose(workspace: ProposerWorkspace) -> tuple[dict[str, str], str]:
    settings = get_settings()
    backend = FilesystemBackend(root_dir=str(workspace.root), virtual_mode=True)
    agent = create_deep_agent(model=settings.model, system_prompt=OUTER_SYSTEM_PROMPT, backend=backend)
    agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Read /task.md and the rest of the workspace, then edit /current/* "
                        "and write /proposal.md.  Stop when done."
                    ),
                }
            ]
        },
        config={"recursion_limit": 50},
    )
    values = {name: path.read_text().strip() for name, path in workspace.surface_files.items()}
    summary = workspace.proposal_file.read_text().strip() if workspace.proposal_file.exists() else ""
    return values, summary


# ── Loop ─────────────────────────────────────────────────────────────────────


def loop(*, max_iterations: int = MAX_ITERATIONS) -> None:
    global WORKSPACE_ROOT  # noqa: PLW0603
    WORKSPACE_ROOT = Path(tempfile.mkdtemp(prefix="bh_stage11_workspace_"))
    proposer_parent = Path(tempfile.mkdtemp(prefix="bh_stage11_proposer_"))
    print(f"Inner workspace: {WORKSPACE_ROOT}")
    print(f"Proposer workspaces: {proposer_parent}\n")

    baseline = baseline_variant()
    base_train = run_eval(baseline, split="train")
    base_holdout = run_eval(baseline, split="holdout")
    print(f"Baseline: train {base_train.passed}/{base_train.total}  holdout {base_holdout.passed}/{base_holdout.total}\n")

    current = baseline
    cur_train, cur_holdout = base_train, base_holdout
    decisions: list[IterationDecision] = []

    for i in range(max_iterations):
        print(f"── Iteration {i} ──")
        workspace = build_proposer_workspace(
            current=current,
            train_result=cur_train,
            decisions=decisions,
            iteration=i,
            parent_dir=proposer_parent,
        )
        print(f"  Workspace: {workspace.root}")
        print(f"    files: {sorted(p.name for p in workspace.root.rglob('*') if p.is_file())[:10]}…")

        values, summary = propose(workspace)
        candidate = build_variant(label=f"iter-{i:03d}", values=values)

        cand_train = run_eval(candidate, split="train")
        cand_holdout = run_eval(candidate, split="holdout")
        cand_combined = cand_train.passed + cand_holdout.passed
        cur_combined = cur_train.passed + cur_holdout.passed
        accepted = cand_combined > cur_combined
        reason = (
            f"combined {cand_combined} > {cur_combined}"
            if accepted
            else f"combined {cand_combined} <= {cur_combined}"
        )
        decisions.append(
            IterationDecision(
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
                proposal_summary=summary,
            )
        )
        print(f"  {'✓' if accepted else '✗'} {reason}\n")

        if accepted:
            current = candidate
            cur_train, cur_holdout = cand_train, cand_holdout

    print("=" * 60)
    print("Final changed surfaces:", ", ".join(current.changed_surfaces) or "none")
    for d in decisions:
        verdict = "✓" if d.accepted else "✗"
        print(f"  {verdict} iter {d.iteration}: train {d.train_passed}/{d.train_total} holdout {d.holdout_passed}/{d.holdout_total}")


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"Stage 11 — Proposer Workspace ({datetime.now(tz=UTC).isoformat(timespec='seconds')})\n")
    loop()


if __name__ == "__main__":
    # Silence unused-import warning for asdict (kept for future serialization).
    _ = asdict
    main()
