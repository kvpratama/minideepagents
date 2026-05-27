"""Stage 05 — ingest vs query: one workflow can't serve two intents.

By stage 04 we have a safe, persistent, audit-logged wiki. But every
invocation still uses the same system prompt and the same permission
set. Two failure modes appear:

  - "Just answer a question" runs still allow writes, so the agent
    sometimes "improves" the wiki opportunistically — silent edits
    during a question.
  - The ingest prompt and the question prompt have to be merged into
    one omni-prompt, which is long and unfocused.

Fix: introduce a `mode` ("ingest" | "query"), per-mode prompt
construction, and per-mode permission profiles. Query gets a strictly
read-only permission set; ingest keeps the write-to-/wiki permission.
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

WORKSPACE = Path(__file__).resolve().parent / "_stage05_workspace"
SAMPLE_SRC = Path(__file__).resolve().parents[1] / "shared" / "sample_source.md"


def ensure_scaffold(workspace: Path) -> None:
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "wiki").mkdir(parents=True, exist_ok=True)
    shutil.copy(SAMPLE_SRC, workspace / "raw" / "ada.md")


def apply_permissions() -> list[FilesystemPermission]:
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
    ]


def readonly_permissions() -> list[FilesystemPermission]:
    """Query mode: deny writes everywhere."""
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
    ]


def ingest_prompt(source_name: str) -> str:
    return (
        "Apply ingest for the staged source.\n"
        f"Read /raw/{source_name}, update canonical /wiki/ pages, "
        "and report a concise change summary.\n"
        "Never write /raw/, /log.md, or /AGENTS.md."
    )


def query_prompt(question: str) -> str:
    return (
        f"Question: {question}\n\n"
        "Read-only: do not create, edit, or delete files. "
        "Read /wiki/ pages and provide a grounded answer with citations."
    )


def run_mode(workspace: Path, mode: str, *, source: str | None = None,
             question: str | None = None) -> None:
    if mode == "ingest":
        prompt = ingest_prompt(source or "ada.md")
        perms = apply_permissions()
    elif mode == "query":
        prompt = query_prompt(question or "What is Ada Lovelace known for?")
        perms = readonly_permissions()
    else:
        msg = f"unknown mode {mode!r}"
        raise ValueError(msg)

    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    agent = create_deep_agent(
        model=model_or_skip(f"stage 05 mode={mode} wiring demo"),
        backend=backend,
        permissions=perms,
        system_prompt="You are a research synthesizer.",
    )
    print(f"[stage 05][{mode}] permission profile:")  # noqa: T201
    for perm in perms:
        print(f"  - {perm}")  # noqa: T201
    print(f"[stage 05][{mode}] prompt (truncated):")  # noqa: T201
    print("  " + prompt.replace("\n", "\n  ")[:400])  # noqa: T201
    _ = agent


def main() -> None:
    ensure_scaffold(WORKSPACE)
    run_mode(WORKSPACE, "ingest", source="ada.md")
    print()  # noqa: T201
    run_mode(WORKSPACE, "query", question="What is Ada Lovelace known for?")


if __name__ == "__main__":
    main()
