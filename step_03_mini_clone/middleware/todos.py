"""TodosMiddleware — adds a `todos` state channel and a `write_todos` tool.

This is the simplest middleware in the stack: it shows the two
core extension points exposed by `AgentMiddleware`:

1. `state_schema` — extend the agent state with new channels.
2. `tools` — register tools the agent can call.
"""

from __future__ import annotations

from typing import Literal

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from typing_extensions import TypedDict


class Todo(TypedDict):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class TodosState(AgentState):
    todos: list[Todo]


@tool
def write_todos(
    todos: list[Todo],
    runtime: ToolRuntime,
) -> Command:
    """Replace the agent's todo list."""
    return Command(
        update={
            "todos": todos,
            "messages": [
                ToolMessage(
                    f"Recorded {len(todos)} todos.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


class TodosMiddleware(AgentMiddleware):
    """Adds the `write_todos` planning tool."""

    state_schema = TodosState
    tools = [write_todos]
