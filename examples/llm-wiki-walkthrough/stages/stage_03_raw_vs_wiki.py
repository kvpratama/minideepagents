"""Stage 03 — evidence/wiki split, enforced by FilesystemPermission.

Stage 02 let the agent stomp on its own outputs. The pressure here:
**the agent must never destroy its evidence**, because if it does,
nothing can be re-derived. Splitting the workspace into `/raw/`
(immutable) and `/wiki/` (editable) is half the fix — the prompt
*says* `/raw/` is read-only. But prompts are guidance, not enforcement.

The real abstraction is `FilesystemPermission`. We deny writes to
`/raw/**` at the middleware layer so the agent literally cannot
corrupt evidence even if the prompt is misread.
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

WORKSPACE = Path(__file__).resolve().parent / "_stage03_workspace"
SAMPLE_SRC = Path(__file__).resolve().parents[1] / "shared" / "sample_source.md"


def ensure_scaffold(workspace: Path) -> None:
    """Create the raw/ + wiki/ split and stage one immutable source."""
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "wiki").mkdir(parents=True, exist_ok=True)
    shutil.copy(SAMPLE_SRC, workspace / "raw" / "ada.md")


def permissions() -> list[FilesystemPermission]:
    """The minimum guard: evidence is read-only."""
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
    ]


def build_agent(workspace: Path):
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    return create_deep_agent(
        model=model_or_skip("stage 03 demonstrates permission enforcement"),
        backend=backend,
        permissions=permissions(),
        system_prompt=(
            "Treat /raw/ as immutable source material. "
            "Synthesize knowledge under /wiki/."
        ),
    )


def show_failure_without_permissions(workspace: Path) -> None:
    """A direct backend write to /raw/ illustrates what could happen."""
    raw_path = workspace / "raw" / "ada.md"
    print("[stage 03] /raw/ada.md BEFORE rogue overwrite:")  # noqa: T201
    print(raw_path.read_text()[:80] + "...\n")  # noqa: T201
    # If the agent did this without permissions, the source is gone:
    backup = raw_path.read_text()
    raw_path.write_text("(corrupted by rogue agent write)\n")
    print("[stage 03] /raw/ada.md AFTER rogue overwrite:")  # noqa: T201
    print(raw_path.read_text())  # noqa: T201
    raw_path.write_text(backup)  # restore for the next demo


def main() -> None:
    ensure_scaffold(WORKSPACE)
    show_failure_without_permissions(WORKSPACE)

    agent = build_agent(WORKSPACE)
    print("[stage 03] agent built with FilesystemPermission policy:")  # noqa: T201
    for perm in permissions():
        print(f"  - {perm}")  # noqa: T201
    print("[stage 03] writes to /raw/** are now blocked at the middleware layer.")  # noqa: T201
    _ = agent


if __name__ == "__main__":
    main()
