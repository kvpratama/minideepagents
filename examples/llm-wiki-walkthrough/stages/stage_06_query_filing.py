"""Stage 06 — query with a filing decision.

Stage 05 split query off from ingest, but query was strictly
read-only. That means even *valuable* query answers — durable
research syntheses worth keeping — are thrown away. The opposite
extreme (every query writes a /wiki/query/* page) floods the wiki
with one-shot trivia.

The fix is a two-phase query:

  Phase 1 (read-only): analyze and decide whether the answer is
      worth filing. The decision is communicated back to the runner
      via a tiny structured marker:

          ANSWER:
          ...
          FILING_DECISION: file|skip
          FILING_REASON: <one sentence>

  Phase 2 (apply, conditional): runner re-invokes the agent with a
      write permission and a prompt that says "file this answer to
      /wiki/query/<slug>.md".

The marker-parse pattern looks crude compared to LangChain structured
output. It is — deliberately. See the markdown for why.
"""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from shared.model import model_or_skip

WORKSPACE = Path(__file__).resolve().parent / "_stage06_workspace"
SAMPLE_SRC = Path(__file__).resolve().parents[1] / "shared" / "sample_source.md"

_DECISION = re.compile(r"^FILING_DECISION:\s*(file|skip)\s*$", re.I | re.M)
_REASON = re.compile(r"^FILING_REASON:\s*(.+)$", re.I | re.M)


@dataclass(frozen=True)
class QueryDecision:
    answer: str
    should_file: bool
    reason: str


def ensure_scaffold(workspace: Path) -> None:
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "wiki" / "query").mkdir(parents=True, exist_ok=True)
    shutil.copy(SAMPLE_SRC, workspace / "raw" / "ada.md")


def query_review_prompt(question: str) -> str:
    return (
        f"Answer this question: {question}\n\n"
        "Read-only. Cite /wiki/ pages.\n\n"
        "Required output format (exact keys):\n"
        "ANSWER:\n"
        "<markdown answer with citations>\n\n"
        "FILING_DECISION: file|skip\n"
        "FILING_REASON: <one sentence>\n"
    )


def query_apply_prompt(question: str, answer: str, target_path: str) -> str:
    return (
        f"File a durable query answer at exactly `{target_path}`.\n"
        f"Question: {question}\n\nAnswer draft:\n{answer}\n"
    )


def parse_decision(raw: str) -> QueryDecision:
    decision = _DECISION.search(raw)
    reason = _REASON.search(raw)
    should_file = decision is not None and decision.group(1).lower() == "file"
    answer = raw[: decision.start()].strip() if decision else raw.strip()
    if answer.upper().startswith("ANSWER:"):
        answer = answer[len("ANSWER:"):].strip()
    return QueryDecision(
        answer=answer or "(no answer)",
        should_file=should_file,
        reason=reason.group(1).strip() if reason else "decision missing; defaulted to skip",
    )


def slug(text: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (out[:80].rstrip("-") or "query")


def run_query(workspace: Path, question: str) -> QueryDecision:
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    review_agent = create_deep_agent(
        model=model_or_skip("stage 06 review phase wiring"),
        backend=backend,
        permissions=[
            FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
            FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="deny"),
            FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        ],
        system_prompt="You are a research synthesizer.",
    )
    _ = review_agent
    # Wiring-only demo: pretend the model returned this.
    canned = (
        "ANSWER:\nAda Lovelace wrote Note G in 1843, widely cited as the "
        "first published algorithm for a machine.\n\n"
        "FILING_DECISION: file\nFILING_REASON: durable biographical synthesis.\n"
    )
    decision = parse_decision(canned)
    print(f"[stage 06][review] decision={decision.should_file} reason={decision.reason}")  # noqa: T201

    if decision.should_file:
        target = f"/wiki/query/{slug(question)}.md"
        apply_agent = create_deep_agent(
            model=model_or_skip("stage 06 apply phase wiring"),
            backend=backend,
            permissions=[
                FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
                FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
                FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
            ],
            system_prompt="You are a research synthesizer.",
        )
        _ = apply_agent
        # Simulate the filed page so the failure-vs-fix is visible.
        filed = workspace / "wiki" / "query" / f"{slug(question)}.md"
        filed.write_text(
            f"# {question}\n\n## Answer\n\n{decision.answer}\n\n"
            f"## Sources\n\n- /wiki/...\n"
        )
        print(f"[stage 06][apply] filed {filed.relative_to(workspace)}")  # noqa: T201
    return decision


def main() -> None:
    ensure_scaffold(WORKSPACE)
    run_query(WORKSPACE, "What did Ada Lovelace contribute to computing?")


if __name__ == "__main__":
    main()
