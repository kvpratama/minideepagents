"""Stage 08 — lint reconciliation.

By stage 07 we have ingest (write), query (read or write-on-demand),
and runner-managed log + index. What's missing is *maintenance*. A
wiki built over months accumulates:

  - Contradictions between two ingests of different sources.
  - Stale claims superseded by newer evidence.
  - Orphan pages (no inbound links).
  - Missing cross-references between related pages.

Ingest is forward-only; query is point-in-time. Neither reconciles.

Lint is a single-pass apply mode dedicated to reconciliation. It is
*not* two-phase — the operational pressure is the opposite of
ingest. We *want* lint to apply immediately because operators run
it periodically to keep the corpus healthy; gating every lint on
review would just stop people running it.

The prompt explicitly instructs the model to read recent /log.md
entries first — this is the first place the runner-managed log
becomes input to the agent. The structured `## [date] phase | ...`
format from stage 04 is why this works: the model can scan it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from shared.model import model_or_skip

WORKSPACE = Path(__file__).resolve().parent / "_stage08_workspace"
SAMPLE_SRC = Path(__file__).resolve().parents[1] / "shared" / "sample_source.md"


def ensure_scaffold(workspace: Path) -> None:
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "wiki").mkdir(parents=True, exist_ok=True)
    shutil.copy(SAMPLE_SRC, workspace / "raw" / "ada.md")
    if not (workspace / "log.md").exists():
        (workspace / "log.md").write_text(
            "# Change Log\n\n"
            "## [2026-05-01] ingest.apply | outcome=applied source_count=1\n"
            "- timestamp: 2026-05-01T10:00:00Z\n"
            "- summary: created /wiki/ada-lovelace.md.\n\n"
            "## [2026-05-10] ingest.apply | outcome=applied source_count=2\n"
            "- timestamp: 2026-05-10T10:00:00Z\n"
            "- summary: added /wiki/note-g.md; minor /wiki/ada-lovelace.md edits.\n"
        )
    # Pretend two earlier ingests left a contradiction.
    (workspace / "wiki" / "ada-lovelace.md").write_text(
        "# Ada Lovelace\n\n- Born 1815.\n- Wrote Note G in 1842.\n"
    )
    (workspace / "wiki" / "note-g.md").write_text(
        "# Note G\n\nPublished in 1843.\n"
    )


def lint_permissions() -> list[FilesystemPermission]:
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
    ]


def lint_prompt() -> str:
    return (
        "Run a single-pass lint reconciliation under /wiki/.\n\n"
        "Execution mode:\n"
        "- Read recent /log.md entries first (latest ~10 `## [` headings).\n"
        "- Apply updates immediately. No review/confirm phase.\n"
        "- Update pages in place; create new canonical pages where needed.\n"
        "- Do not edit /log.md. Never write /raw/.\n\n"
        "Required health checks:\n"
        "- Reconcile contradictions; preserve explicit uncertainty when unresolved.\n"
        "- Identify and qualify stale claims.\n"
        "- Detect orphan pages and add cross-references.\n"
        "- Create canonical pages for important concepts when missing.\n\n"
        "Return a report with sections:\n"
        "## Reconciled Changes\n## Remaining Gaps\n"
        "## Suggested Next Questions and Sources\n"
    )


def run_lint(workspace: Path) -> str:
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    agent = create_deep_agent(
        model=model_or_skip("stage 08 lint wiring"),
        backend=backend,
        permissions=lint_permissions(),
        system_prompt="You are a wiki maintainer.",
    )
    _ = agent
    # Wiring-only: simulate the reconciled fix.
    (workspace / "wiki" / "ada-lovelace.md").write_text(
        "# Ada Lovelace\n\n- Born 1815.\n- Wrote Note G in 1843 "
        "(corrected from 1842; cross-ref /wiki/note-g.md).\n"
    )
    return (
        "## Reconciled Changes\n- Fixed Note G date in ada-lovelace.md.\n\n"
        "## Remaining Gaps\n- No coverage of Babbage relationship.\n\n"
        "## Suggested Next Questions and Sources\n- Ingest Babbage correspondence.\n"
    )


def main() -> None:
    ensure_scaffold(WORKSPACE)
    print("[stage 08] before lint:")  # noqa: T201
    print((WORKSPACE / "wiki" / "ada-lovelace.md").read_text())  # noqa: T201
    print("---")  # noqa: T201
    report = run_lint(WORKSPACE)
    print("[stage 08] after lint:")  # noqa: T201
    print((WORKSPACE / "wiki" / "ada-lovelace.md").read_text())  # noqa: T201
    print("[stage 08] report:")  # noqa: T201
    print(report)  # noqa: T201


if __name__ == "__main__":
    main()
