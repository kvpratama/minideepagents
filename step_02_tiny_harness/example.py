"""End-to-end demo for the tiny harness.

Exercises every capability in one run:
    planning, filesystem, subagents, permissions, skills.

Run:  uv run python step_02_tiny_harness/example.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from langchain.messages import HumanMessage
from langgraph.types import Command
from step_02_tiny_harness.mini import create_deep_agent
from utils.config import get_settings

SKILLS_DIR = Path(__file__).parent / "skills"

INSTRUCTIONS = (
    "You are a deep agent. Always start by recording a short plan with "
    "`write_todos`. Use `task` with subagent_type='general-purpose' to "
    "delegate focused subtasks. Use `write_file`/`read_file` to persist "
    "work. Writes require human approval — proceed anyway."
)


async def main() -> None:
    settings = get_settings()
    agent = await create_deep_agent(
        model=settings.model,
        tools=[],
        instructions=INSTRUCTIONS,
        subagents=[
            {"name": "general-purpose", "description": "default subagent with fs tools"}
        ],
        skills_dir=SKILLS_DIR,
        require_approval=["write_file", "edit_file"],
    )

    config = {"configurable": {"thread_id": "demo"}}
    inputs = {
        "messages": [
            HumanMessage(
                "Load the poetry skill if it looks relevant, then delegate a "
                "subagent to draft a 4-line haiku about a winter morning and "
                "save it to `haiku.txt`. Finally, read it back to me."
            )
        ],
        "todos": [],
        "files": {},
    }

    state = agent.invoke(inputs, config=config)
    while "__interrupt__" in state:
        ints = state["__interrupt__"]
        print(f"[HITL] auto-approving: {ints[0].value['prompt']}")
        state = agent.invoke(Command(resume="approved"), config=config)

    print("\n--- Todos ---")
    for t in state.get("todos") or []:
        print(f"  [{t['status']}] {t['content']}")
    print("\n--- Files ---")
    for path, content in (state.get("files") or {}).items():
        print(f"\n# {path}\n{content}")
    print("\n--- Final assistant reply ---")
    print(state["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
