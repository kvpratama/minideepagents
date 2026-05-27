"""Stage 04 — runner-managed log.md and wiki/index.md.

In stage 03 the agent could write anywhere under `/wiki/`. That
includes two files whose value depends on them being *machine
maintained*:

  - /log.md         — an append-only timeline of what the runner did.
  - /wiki/index.md  — a derived content catalog of wiki pages.

If the agent edits these, they drift: log entries are rewritten in
prose, index categories collide with new sections, page summaries
quietly diverge from the page bodies. Both files are runner
*outputs* about the agent, not agent outputs about the topic.

Fix: deny the agent write access to both, and have the runner own
their generation. The agent's only obligation is to keep `/wiki/*.md`
clean — the index is rebuilt from the directory listing, and the log
gets one structured entry per runner phase.
"""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from shared.model import model_or_skip

WORKSPACE = Path(__file__).resolve().parent / "_stage04_workspace"
SAMPLE_SRC = Path(__file__).resolve().parents[1] / "shared" / "sample_source.md"


def ensure_scaffold(workspace: Path) -> None:
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "wiki").mkdir(parents=True, exist_ok=True)
    shutil.copy(SAMPLE_SRC, workspace / "raw" / "ada.md")
    log = workspace / "log.md"
    if not log.exists():
        log.write_text("# Change Log\n")
    index = workspace / "wiki" / "index.md"
    if not index.exists():
        index.write_text("# Wiki\n\n## Other Pages\n\n- _No pages yet._\n")


def permissions() -> list[FilesystemPermission]:
    """Now denies log.md (runner-owned) and AGENTS.md (config-owned)."""
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
    ]


def append_log_entry(workspace: Path, phase: str, outcome: str, summary: str) -> None:
    """Append one structured timeline entry. Runner-only."""
    now = datetime.now(UTC)
    entry = (
        f"\n## [{now:%Y-%m-%d}] {phase} | outcome={outcome}\n"
        f"- timestamp: {now:%Y-%m-%dT%H:%M:%SZ}\n"
        f"- summary: {summary.strip()}\n"
    )
    with (workspace / "log.md").open("a", encoding="utf-8") as handle:
        handle.write(entry)


def refresh_index(workspace: Path) -> None:
    """Rebuild wiki/index.md from current wiki pages."""
    wiki = workspace / "wiki"
    pages = sorted(p for p in wiki.rglob("*.md") if p.name != "index.md")
    lines = ["# Wiki", "", "Content catalog.", "", "## Other Pages", ""]
    if not pages:
        lines.append("- _No pages yet._")
    else:
        for page in pages:
            rel = page.relative_to(wiki).as_posix()
            title = page.stem.replace("-", " ").title()
            lines.append(f"- [{title}]({rel})")
    (wiki / "index.md").write_text("\n".join(lines) + "\n")


def build_agent(workspace: Path):
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    return create_deep_agent(
        model=model_or_skip("stage 04 demonstrates runner-owned artifacts"),
        backend=backend,
        permissions=permissions(),
        system_prompt=(
            "Treat /raw/ as immutable. Synthesize under /wiki/. "
            "Never write /log.md or /wiki/index.md — those are runner-managed."
        ),
    )


def main() -> None:
    ensure_scaffold(WORKSPACE)
    # Pretend the agent just wrote a wiki page.
    (WORKSPACE / "wiki" / "ada-lovelace.md").write_text(
        "# Ada Lovelace\n\nWrote Note G in 1843.\n"
    )
    refresh_index(WORKSPACE)
    append_log_entry(
        WORKSPACE,
        phase="ingest.apply",
        outcome="applied",
        summary="Stub agent created wiki/ada-lovelace.md from /raw/ada.md.",
    )

    print("[stage 04] index now:")  # noqa: T201
    print((WORKSPACE / "wiki" / "index.md").read_text())  # noqa: T201
    print("[stage 04] log tail:")  # noqa: T201
    print((WORKSPACE / "log.md").read_text())  # noqa: T201

    _ = build_agent(WORKSPACE)


if __name__ == "__main__":
    main()
