"""Stage 01 — single shot.

The most primitive shape: one `create_deep_agent` call answers one
question against an in-memory state backend. No persistence, no
modes, no separation of evidence from synthesis. Run it twice and
the second invocation has zero memory of the first.

This is the architectural starting point that every other stage
will progressively constrain.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepagents import create_deep_agent

from shared.model import model_or_skip


def build_agent():
    """Return a deep agent that lives entirely in graph state."""
    return create_deep_agent(
        model=model_or_skip("stage 01 only needs the wiring"),
        system_prompt=(
            "You are a research assistant. Answer the user's question "
            "based on what you already know."
        ),
    )


def main() -> None:
    agent = build_agent()
    print("[stage 01] agent built with default StateBackend (in-memory).")  # noqa: T201
    print("[stage 01] no files exist on disk; nothing persists between runs.")  # noqa: T201

    if agent.get_graph():
        # Just enumerate the runtime to prove it's a real, invocable agent.
        print("[stage 01] nodes:", list(agent.get_graph().nodes))  # noqa: T201


if __name__ == "__main__":
    main()
