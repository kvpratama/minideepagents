"""Stage 09 — Context Hub pull / push lifecycle.

The wiki is now structurally sound (stages 03–08) but trapped on
one machine. Teammates can't review, branch, or comment. Two
operators running ingest in parallel last-write-wins each other.
Backups depend on the laptop not crashing.

Context Hub gives the wiki a durable, shareable home. The pattern
in the original repo:

    pull   →  workspace = tempdir()
              langsmith hub pull <repo> --dir <workspace>
    mutate →  run the mode against <workspace>
              (ingest / query / lint as before)
    push   →  langsmith hub push <repo> --dir <workspace>
              tempdir is torn down

Init is special — it bootstraps the hub repo with `source=internal`
before any pull is possible.

The hub CLI is shelled out, not imported. That's deliberate (see
the markdown).

This stage abstracts the hub commands behind a `FakeHub` so the
demo runs without LangSmith. The shape is identical to the
production code in `helpers._run_pull_mode` / `init.run_init`.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from shared.model import model_or_skip  # noqa: F401  (kept for parity)

WORKSPACE_PARENT = Path(__file__).resolve().parent / "_stage09_hub_store"
SAMPLE_SRC = Path(__file__).resolve().parents[1] / "shared" / "sample_source.md"
_ALLOWED_TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}


class FakeHub:
    """Stand-in for `langsmith hub`. Each repo is a directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def init(self, repo: str) -> Path:
        path = self.root / repo
        path.mkdir(parents=True, exist_ok=True)
        return path

    def pull(self, repo: str, dest: Path) -> None:
        src = self.root / repo
        if not src.exists():
            msg = f"hub repo {repo!r} not found; run init first"
            raise RuntimeError(msg)
        for child in src.iterdir():
            if child.is_dir():
                shutil.copytree(child, dest / child.name, dirs_exist_ok=True)
            else:
                shutil.copy2(child, dest / child.name)

    def push(self, repo: str, src: Path) -> None:
        dst = self.root / repo
        # Mirror the source-of-truth validation: text-only, no symlinks.
        for path in src.rglob("*"):
            if path.is_symlink():
                msg = f"symlinks unsupported: {path}"
                raise RuntimeError(msg)
            if path.is_file() and path.suffix.lower() not in _ALLOWED_TEXT_SUFFIXES:
                msg = f"non-text file blocked: {path}"
                raise RuntimeError(msg)
        # Replace; simulate the atomic push.
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def ensure_scaffold(workspace: Path, topic: str) -> None:
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "wiki").mkdir(parents=True, exist_ok=True)
    if not (workspace / "log.md").exists():
        (workspace / "log.md").write_text("# Change Log\n")
    if not (workspace / "AGENTS.md").exists():
        (workspace / "AGENTS.md").write_text(f"# {topic} Wiki\n")
    index = workspace / "wiki" / "index.md"
    if not index.exists():
        index.write_text(f"# {topic} Wiki\n\n## Other Pages\n\n- _No pages yet._\n")


def init_workflow(hub: FakeHub, repo: str, topic: str) -> None:
    """Bootstrap a hub repo from a fresh local scaffold."""
    local = WORKSPACE_PARENT / "_init_scratch"
    if local.exists():
        shutil.rmtree(local)
    local.mkdir(parents=True)
    ensure_scaffold(local, topic)
    hub.init(repo)
    hub.push(repo, local)
    shutil.rmtree(local)
    print(f"[stage 09][init] hub repo {repo!r} initialized.")  # noqa: T201


def pull_modify_push(hub: FakeHub, repo: str, mode: str) -> None:
    """The shape every modifying mode now wears."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        hub.pull(repo, workspace)
        ensure_scaffold(workspace, repo)
        # Wire the agent against this transient workspace.
        _backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
        _perms = [
            FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
            FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
            FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
            FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        ]
        # Wiring-only: simulate the mutation the mode would make.
        if mode == "ingest":
            shutil.copy(SAMPLE_SRC, workspace / "raw" / "ada.md")
            (workspace / "wiki" / "ada-lovelace.md").write_text(
                "# Ada Lovelace\n\n- Wrote Note G in 1843.\n"
            )
        elif mode == "lint":
            page = workspace / "wiki" / "ada-lovelace.md"
            if page.exists():
                page.write_text(page.read_text() + "- Cross-ref: /wiki/note-g.md\n")
        hub.push(repo, workspace)
        print(f"[stage 09][{mode}] pulled, mutated, pushed.")  # noqa: T201


def main() -> None:
    if WORKSPACE_PARENT.exists():
        shutil.rmtree(WORKSPACE_PARENT)
    hub = FakeHub(WORKSPACE_PARENT)
    init_workflow(hub, repo="ada-wiki", topic="Ada")
    pull_modify_push(hub, repo="ada-wiki", mode="ingest")
    pull_modify_push(hub, repo="ada-wiki", mode="lint")

    print("[stage 09] final hub-side wiki:")  # noqa: T201
    for child in sorted((WORKSPACE_PARENT / "ada-wiki" / "wiki").rglob("*.md")):
        rel = child.relative_to(WORKSPACE_PARENT / "ada-wiki")
        print(f"  {rel}")  # noqa: T201


if __name__ == "__main__":
    main()
