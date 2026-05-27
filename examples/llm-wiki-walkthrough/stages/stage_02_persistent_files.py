"""Stage 02 — persistent files via FilesystemBackend.

The minimal fix for stage 01: give the agent a `FilesystemBackend`
rooted at a stable local directory so writes survive the process.

Now the agent can build *something* across runs, but there is no
structure. Every page lives at the top level. There is no notion
of "source material" vs. "synthesized knowledge". The agent is
free to overwrite anything it created previously.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from shared.model import model_or_skip

WIKI_DIR = Path(__file__).resolve().parent / "_stage02_workspace"


def build_agent(wiki_dir: Path):
    """A deep agent rooted at one flat persistent directory."""
    backend = FilesystemBackend(root_dir=wiki_dir, virtual_mode=True)
    return create_deep_agent(
        model=model_or_skip("stage 02 demonstrates persistence, not LLM use"),
        backend=backend,
        system_prompt=(
            "You are a research assistant. Read any files in your "
            "workspace before answering. Write notes back as markdown."
        ),
    )


def simulate_collision(wiki_dir: Path) -> None:
    """Show what happens when the agent has no structural guardrails."""
    wiki_dir.mkdir(parents=True, exist_ok=True)
    # Two independent "research sessions" both decide to write `notes.md`.
    (wiki_dir / "notes.md").write_text("Ada Lovelace was born in 1815.\n")
    (wiki_dir / "notes.md").write_text("Ada Lovelace wrote Note G in 1843.\n")
    # The second session has silently destroyed the first session's facts.
    print("[stage 02] notes.md final contents:")  # noqa: T201
    print((wiki_dir / "notes.md").read_text())  # noqa: T201


def main() -> None:
    agent = build_agent(WIKI_DIR)
    print(f"[stage 02] FilesystemBackend rooted at {WIKI_DIR}")  # noqa: T201
    print("[stage 02] writes now persist between runs — but with zero structure.")  # noqa: T201
    simulate_collision(WIKI_DIR)
    print("[stage 02] nothing distinguishes evidence from synthesis here.")  # noqa: T201
    _ = agent  # keep the build_agent call alive for wiring inspection


if __name__ == "__main__":
    main()
