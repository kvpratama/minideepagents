"""Stage 13 — TOML Config + CLI.

Move experiment definition out of Python literals and into a TOML file.
Add a CLI with three subcommands:

- ``validate <config.toml>`` — load + validate
- ``run <config.toml>``      — run the optimization loop
- ``inspect <run_dir>``      — pretty-print a previous run's report

Run::

    uv run python stages_b/stage_13_toml_config_and_cli.py \
        validate stages_b/stage_13_example.toml

    uv run python stages_b/stage_13_toml_config_and_cli.py \
        run stages_b/stage_13_example.toml

    uv run python stages_b/stage_13_toml_config_and_cli.py inspect <run_dir>
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents import create_agent
from langchain.tools import tool

from config import get_model, get_settings

ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")
VALID_KINDS = ("module_attr", "workspace_file")
VALID_SPLITS = ("train", "holdout", "scorecard")

# ── Data model ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Surface:
    name: str
    kind: Literal["module_attr", "workspace_file"]
    target: str
    base_value: str
    filename: str


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected: str
    split: Literal["train", "holdout", "scorecard"]


@dataclass(frozen=True)
class Experiment:
    """Loaded experiment definition."""

    path: Path
    name: str
    max_iterations: int
    surfaces: dict[str, Surface]
    cases: tuple[EvalCase, ...]

    def cases_for_split(self, split: str) -> list[EvalCase]:
        return [c for c in self.cases if c.split == split]

    def has_split(self, split: str) -> bool:
        return bool(self.cases_for_split(split))


@dataclass(frozen=True)
class Variant:
    label: str
    values: dict[str, str]
    changed_surfaces: tuple[str, ...] = ()


@dataclass
class SplitResult:
    split: str
    variant: str
    passed: int
    total: int
    failures: list[str] = field(default_factory=list)


@dataclass
class IterationDecision:
    iteration: int
    candidate_variant: str
    changed_surfaces: list[str]
    train_passed: int
    train_total: int
    holdout_passed: int
    holdout_total: int
    accepted: bool
    reason: str


# ── TOML loader ─────────────────────────────────────────────────────────────


def expand_env(value: str) -> str:
    """Expand ``${ENV_VAR}`` references."""
    return ENV_PATTERN.sub(lambda m: os.environ[m.group(1)], value)


def _resolve_path(config_path: Path, raw: str) -> Path:
    p = Path(expand_env(raw)).expanduser()
    return p if p.is_absolute() else (config_path.parent / p).resolve()


def load_experiment(path: Path) -> Experiment:
    """Parse one TOML experiment definition into typed dataclasses."""
    config_path = path.resolve()
    raw = tomllib.loads(config_path.read_text())

    experiment = raw.get("experiment", {})
    if "name" not in experiment:
        msg = "experiment.name is required"
        raise ValueError(msg)

    name = str(experiment["name"])
    max_iterations = int(experiment.get("max_iterations", 3))
    if max_iterations < 1:
        msg = "experiment.max_iterations must be >= 1"
        raise ValueError(msg)

    # surfaces
    surfaces: dict[str, Surface] = {}
    for surface_name, payload in raw.get("surfaces", {}).items():
        kind = str(payload["kind"])
        if kind not in VALID_KINDS:
            msg = f"surface '{surface_name}': unknown kind {kind!r}; expected {VALID_KINDS}"
            raise ValueError(msg)
        target = str(payload["target"])

        # exactly one of base_value | base_file
        has_base_value = "base_value" in payload
        has_base_file = "base_file" in payload
        if has_base_value == has_base_file:
            msg = (
                f"surface '{surface_name}' must define exactly one of "
                "'base_value' or 'base_file'"
            )
            raise ValueError(msg)
        if has_base_file:
            base_path = _resolve_path(config_path, str(payload["base_file"]))
            base_value = base_path.read_text()
            default_filename = base_path.name
        else:
            base_value = str(payload["base_value"])
            default_filename = f"{surface_name}.txt"

        filename = str(payload.get("filename", default_filename))
        surfaces[surface_name] = Surface(
            name=surface_name,
            kind=kind,
            target=target,
            base_value=base_value,
            filename=filename,
        )

    if not surfaces:
        msg = "experiment must define at least one surface"
        raise ValueError(msg)

    # cases
    cases_payload = raw.get("cases", [])
    cases: list[EvalCase] = []
    for item in cases_payload:
        split = str(item["split"])
        if split not in VALID_SPLITS:
            msg = f"case split {split!r} must be one of {VALID_SPLITS}"
            raise ValueError(msg)
        cases.append(
            EvalCase(
                question=str(item["question"]),
                expected=str(item["expected"]),
                split=split,  # type: ignore[arg-type]
            )
        )

    if not any(c.split == "train" for c in cases):
        msg = "experiment must include at least one case with split='train'"
        raise ValueError(msg)
    if not any(c.split == "holdout" for c in cases):
        msg = "experiment must include at least one case with split='holdout'"
        raise ValueError(msg)

    return Experiment(
        path=config_path,
        name=name,
        max_iterations=max_iterations,
        surfaces=surfaces,
        cases=tuple(cases),
    )


# ── Patching (module_attr only at this stage) ───────────────────────────────


BASE_PROMPT = "You are a helpful assistant."


def patch_module_attrs(overrides: dict[str, str]) -> None:
    for target, value in overrides.items():
        module_name, _, attribute = target.partition(":")
        module = importlib.import_module(module_name)
        setattr(module, attribute, value)


def apply_variant(experiment: Experiment, variant: Variant) -> None:
    overrides = {
        s.target: variant.values[name]
        for name, s in experiment.surfaces.items()
        if s.kind == "module_attr"
    }
    patch_module_attrs(overrides)


def baseline_variant(experiment: Experiment) -> Variant:
    return Variant(
        label="baseline",
        values={name: s.base_value for name, s in experiment.surfaces.items()},
    )


def build_variant(experiment: Experiment, label: str, values: dict[str, str]) -> Variant:
    changed = tuple(
        sorted(name for name, s in experiment.surfaces.items() if values[name] != s.base_value)
    )
    return Variant(label=label, values=values, changed_surfaces=changed)


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
    return agent.invoke({"messages": [{"role": "user", "content": question}]})["messages"][-1].content


def normalize(text: str) -> str:
    text = text.strip()
    nums = re.findall(r"-?\d+\.?\d*", text)
    if nums:
        text = nums[-1]
    if text.endswith(".0"):
        text = text[:-2]
    return text


def run_eval(experiment: Experiment, variant: Variant, *, split: str) -> SplitResult:
    apply_variant(experiment, variant)
    failures: list[str] = []
    passed = 0
    for case in experiment.cases_for_split(split):
        ans = inner_agent(case.question)
        if normalize(ans) == normalize(case.expected):
            passed += 1
        else:
            failures.append(f"Q: {case.question}  Got: {normalize(ans)}  Expected: {case.expected}")
    return SplitResult(
        split=split,
        variant=variant.label,
        passed=passed,
        total=len(experiment.cases_for_split(split)),
        failures=failures,
    )


# ── Outer agent ──────────────────────────────────────────────────────────────

OUTER_SYSTEM_PROMPT = """\
You are an outer-loop Deep Agent that improves an inner agent's harness.

Read /task.md, then edit the file under /current/.  Write the full
improved content — not a diff.  Tell the inner agent to always call the
`calculator` tool for any arithmetic.  Keep the prompt concise and
general; do not encode specific Q/A pairs.
"""


def propose(experiment: Experiment, current: Variant, train_failures: list[str], iteration: int) -> dict[str, str]:
    workspace = Path(tempfile.mkdtemp(prefix=f"bh_stage13_iter{iteration}_"))
    (workspace / "current").mkdir()
    for name, surface in experiment.surfaces.items():
        (workspace / "current" / surface.filename).write_text(current.values[name])

    task = ["# Task", "", f"Iteration {iteration}.", "", "## Editable surfaces", ""]
    for name, surface in experiment.surfaces.items():
        task.append(f"- /current/{surface.filename} ({name}, {surface.kind})")
    task.extend(["", "## Failing train cases", ""])
    if train_failures:
        task.extend(f"- {f}" for f in train_failures)
    else:
        task.append("- None")
    (workspace / "task.md").write_text("\n".join(task) + "\n")

    settings = get_settings()
    backend = FilesystemBackend(root_dir=str(workspace), virtual_mode=True)
    agent = create_deep_agent(model=settings.model, system_prompt=OUTER_SYSTEM_PROMPT, backend=backend)
    agent.invoke(
        {"messages": [{"role": "user", "content": "Read /task.md, then improve /current/*."}]},
        config={"recursion_limit": 50},
    )
    proposed = {
        name: (workspace / "current" / s.filename).read_text().strip()
        for name, s in experiment.surfaces.items()
    }
    shutil.rmtree(workspace, ignore_errors=True)
    return proposed


# ── Run ─────────────────────────────────────────────────────────────────────


def run_experiment(experiment: Experiment, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": experiment.name,
                "config_path": str(experiment.path),
                "surfaces": {n: asdict(s) for n, s in experiment.surfaces.items()},
                "max_iterations": experiment.max_iterations,
                "created_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            },
            indent=2,
        )
        + "\n"
    )
    baseline = baseline_variant(experiment)
    base_train = run_eval(experiment, baseline, split="train")
    base_holdout = run_eval(experiment, baseline, split="holdout")
    print(f"Baseline: train {base_train.passed}/{base_train.total}  holdout {base_holdout.passed}/{base_holdout.total}\n")

    current = baseline
    cur_train, cur_holdout = base_train, base_holdout
    decisions: list[IterationDecision] = []

    for i in range(experiment.max_iterations):
        print(f"── Iteration {i} ──")
        proposed = propose(experiment, current, cur_train.failures, iteration=i)
        candidate = build_variant(experiment, label=f"iter-{i:03d}", values=proposed)
        cand_train = run_eval(experiment, candidate, split="train")
        cand_holdout = run_eval(experiment, candidate, split="holdout")
        cand_combined = cand_train.passed + cand_holdout.passed
        cur_combined = cur_train.passed + cur_holdout.passed
        accepted = cand_combined > cur_combined
        reason = f"combined {cand_combined} {'>' if accepted else '<='} {cur_combined}"
        decisions.append(
            IterationDecision(
                iteration=i,
                candidate_variant=candidate.label,
                changed_surfaces=list(candidate.changed_surfaces),
                train_passed=cand_train.passed,
                train_total=cand_train.total,
                holdout_passed=cand_holdout.passed,
                holdout_total=cand_holdout.total,
                accepted=accepted,
                reason=reason,
            )
        )
        print(f"  {'✓' if accepted else '✗'} {reason}\n")
        if accepted:
            current = candidate
            cur_train, cur_holdout = cand_train, cand_holdout
        else:
            apply_variant(experiment, current)

    report = {
        "name": experiment.name,
        "baseline": {"label": baseline.label, "values": baseline.values},
        "final": {
            "label": current.label,
            "values": current.values,
            "changed_surfaces": list(current.changed_surfaces),
        },
        "baseline_train": asdict(base_train),
        "baseline_holdout": asdict(base_holdout),
        "final_train": asdict(cur_train),
        "final_holdout": asdict(cur_holdout),
        "decisions": [asdict(d) for d in decisions],
    }

    if experiment.has_split("scorecard"):
        report["baseline_scorecard"] = asdict(run_eval(experiment, baseline, split="scorecard"))
        report["final_scorecard"] = asdict(run_eval(experiment, current, split="scorecard"))

    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


# ── CLI ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 13 — TOML config + CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Load and validate one experiment TOML")
    p_validate.add_argument("config", type=Path)

    p_run = sub.add_parser("run", help="Run the optimization loop on one experiment")
    p_run.add_argument("config", type=Path)
    p_run.add_argument("--output-dir", type=Path)

    p_inspect = sub.add_parser("inspect", help="Pretty-print a run's report.json")
    p_inspect.add_argument("run_dir", type=Path)

    return parser


def cmd_validate(args: argparse.Namespace) -> int:
    experiment = load_experiment(args.config)
    print(f"Config valid: {experiment.path}")
    print(f"Name: {experiment.name}")
    print(f"Max iterations: {experiment.max_iterations}")
    print(f"Surfaces: {', '.join(experiment.surfaces)}")
    for split in VALID_SPLITS:
        n = len(experiment.cases_for_split(split))
        print(f"{split.title()}: {n} cases")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    experiment = load_experiment(args.config)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or Path(tempfile.mkdtemp(prefix=f"bh_stage13_run_{timestamp}_"))
    print(f"Output dir: {output}\n")
    report = run_experiment(experiment, output)
    print("=" * 60)
    print(json.dumps({k: report[k] for k in ("baseline_train", "final_train", "baseline_holdout", "final_holdout")}, indent=2))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    payload = json.loads((args.run_dir / "report.json").read_text())
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return {"validate": cmd_validate, "run": cmd_run, "inspect": cmd_inspect}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
