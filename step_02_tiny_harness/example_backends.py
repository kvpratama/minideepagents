"""Tiny-harness example: same prompt across three backends.

Builds three agents from `create_deep_agent`, each parameterized with a
different `backend_factory`, and runs the same haiku-writing task. The
output makes the seam concrete — files end up in three different places
(state dict, store namespace, fake sandbox dict) but the agent code is
identical.

Run:  uv run python step_02_tiny_harness/example_backends.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain.messages import HumanMessage
from langgraph.store.memory import InMemoryStore

from backends import FakeSandboxBackend, StoreBackend
from mini import create_deep_agent

from utils.config import get_settings

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))


PROMPT = (
    "Write a 3-line haiku about autumn to `notes/haiku.txt`, "
    "then read it back and confirm exactly what you wrote."
)
INSTRUCTIONS = (
    "You are a deep agent. Plan with `write_todos`, persist with "
    "`write_file`, delegate with `task`."
)


def _approve_loop(agent, inputs, config):
    """Auto-approve every interrupt the agent raises."""
    from langgraph.types import Command

    state = agent.invoke(inputs, config=config)
    while "__interrupt__" in state:
        state = agent.invoke(Command(resume="approved"), config=config)
    return state


async def run_state() -> None:
    print("\n=== StateBackend (default) ===")
    agent = await create_deep_agent(
        model=get_settings().model,
        tools=[],
        instructions=INSTRUCTIONS,
        require_approval=["write_file", "edit_file"],
    )
    state = _approve_loop(
        agent,
        {"messages": [HumanMessage(PROMPT)], "todos": [], "files": {}},
        {"configurable": {"thread_id": "state-demo"}},
    )
    print("Files in state:", list(state.get("files", {}).keys()))


async def run_store() -> None:
    print("\n=== StoreBackend (cross-thread) ===")
    store = InMemoryStore()

    def store_factory(runtime):
        thread_id = runtime.config["configurable"]["thread_id"]
        return StoreBackend(store, thread_id)

    agent = await create_deep_agent(
        model=get_settings().model,
        tools=[],
        instructions=INSTRUCTIONS,
        require_approval=["write_file", "edit_file"],
        backend_factory=store_factory,
        store=store,
    )
    config = {"configurable": {"thread_id": "store-demo"}}
    _approve_loop(
        agent,
        {"messages": [HumanMessage(PROMPT)], "todos": [], "files": {}},
        config,
    )

    # Show the store contents directly, not via state.
    items = store.search(("deep_agent", "store-demo", "files"))
    print("Files in store:", [item.key for item in items])


async def run_sandbox() -> None:
    print("\n=== FakeSandboxBackend ===")
    sandbox = FakeSandboxBackend()

    def sandbox_factory(_runtime):
        return sandbox  # one shared backend across the run

    agent = await create_deep_agent(
        model=get_settings().model,
        tools=[],
        instructions=INSTRUCTIONS,
        require_approval=["write_file", "edit_file"],
        backend_factory=sandbox_factory,
    )
    _approve_loop(
        agent,
        {"messages": [HumanMessage(PROMPT)], "todos": [], "files": {}},
        {"configurable": {"thread_id": "sandbox-demo"}},
    )
    print("Files in sandbox:", sandbox.client.list_files())


async def main() -> None:
    await run_state()
    await run_store()
    await run_sandbox()


if __name__ == "__main__":
    asyncio.run(main())
