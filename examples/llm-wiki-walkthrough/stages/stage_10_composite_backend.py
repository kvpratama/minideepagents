"""Stage 10 — CompositeBackend: sandbox for compute, local FS for truth.

This is the final architectural move and the one most easily
misunderstood.

By stage 09 we have a clean shape: pull from hub → run agent
against tempdir workspace → push to hub. But the agent's
filesystem tools are doing two *very different* jobs:

  1. Reads + writes of canonical artifacts: /raw/, /wiki/,
     /log.md, /AGENTS.md. These must end up byte-identical in the
     workspace so the push captures them.
  2. Scratch I/O: untar a dataset, jq across a JSON dump, compile
     a regex over a corpus, throw away the results. The agent
     wants a real Unix-like sandbox for this kind of work; the
     workspace tempdir wasn't designed to be one.

Conflating both onto the local tempdir means:
  - Every scratch write becomes a candidate for the hub push.
  - The push validator has to reject binaries, symlinks, large
    files — pushing complexity into the boundary.
  - You can't run the agent with sandbox-tier isolation for the
    compute parts.

`CompositeBackend` resolves this. A *default* sandbox backend
handles everything; specific routes (`/raw/`, `/wiki/`,
`/log.md`, `/AGENTS.md`) are remapped to a `FilesystemBackend`
pointed at the local workspace dir. The agent's virtual `/` is
unified; durability is split.

This is the shape the real `llm-wiki/helpers.py` uses in
`_run_agent_mode`.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from shared.model import model_or_skip

SAMPLE_SRC = Path(__file__).resolve().parents[1] / "shared" / "sample_source.md"


class FakeSandboxBackend:
    """Stand-in for LangSmithSandbox so this stage runs without auth.

    Real shape: `LangSmithSandbox(sandbox=client.create_sandbox(...))`,
    cleaned up via `client.delete_sandbox(...)` in a context manager.
    Here we just point at another local dir to keep the demo runnable.
    """

    def __init__(self, scratch_root: Path) -> None:
        self.scratch_root = scratch_root
        self.scratch_root.mkdir(parents=True, exist_ok=True)

    def as_backend(self) -> FilesystemBackend:
        return FilesystemBackend(root_dir=self.scratch_root, virtual_mode=True)


def permissions() -> list[FilesystemPermission]:
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
    ]


def build_agent(workspace: Path, sandbox_root: Path):
    """The signature move: split compute vs. durable on the backend."""
    sandbox = FakeSandboxBackend(sandbox_root).as_backend()
    workspace_backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    backend = CompositeBackend(
        default=sandbox,
        routes={
            "/raw/": workspace_backend,
            "/wiki/": workspace_backend,
            "/log.md": workspace_backend,
            "/AGENTS.md": workspace_backend,
        },
    )
    return create_deep_agent(
        model=model_or_skip("stage 10 final wiring"),
        backend=backend,
        permissions=permissions(),
        system_prompt=(
            "You are a research synthesizer.\n"
            "Canonical files: /raw/ (immutable), /wiki/, /log.md, /AGENTS.md.\n"
            "Anything else under / is scratch — safe to create and discard."
        ),
    )


def demonstrate_routing(workspace: Path, sandbox_root: Path) -> None:
    """Prove the split by writing to both sides and checking durability."""
    sandbox = FakeSandboxBackend(sandbox_root).as_backend()
    workspace_backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    backend = CompositeBackend(
        default=sandbox,
        routes={
            "/raw/": workspace_backend,
            "/wiki/": workspace_backend,
            "/log.md": workspace_backend,
            "/AGENTS.md": workspace_backend,
        },
    )

    # Write a canonical wiki page — should land in the workspace dir.
    backend.write("/wiki/ada-lovelace.md", "# Ada\n")
    # Write a scratch file — should land in the sandbox dir only.
    backend.write("/tmp/scratch.json", '{"hello": "world"}\n')

    print("[stage 10] workspace contents (push to hub):")  # noqa: T201
    for p in sorted(workspace.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(workspace)}")  # noqa: T201
    print("[stage 10] sandbox contents (discarded after run):")  # noqa: T201
    for p in sorted(sandbox_root.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(sandbox_root)}")  # noqa: T201


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        sandbox_root = Path(tmp) / "sandbox"
        workspace.mkdir()
        sandbox_root.mkdir()
        # Seed canonical files (analogous to hub pull + ensure_scaffold).
        (workspace / "raw").mkdir()
        (workspace / "wiki").mkdir()
        shutil.copy(SAMPLE_SRC, workspace / "raw" / "ada.md")
        (workspace / "log.md").write_text("# Change Log\n")
        (workspace / "AGENTS.md").write_text("# Wiki rules\n")

        _ = build_agent(workspace, sandbox_root)
        demonstrate_routing(workspace, sandbox_root)


if __name__ == "__main__":
    main()
