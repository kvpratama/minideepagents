"""PermissionsMiddleware — interrupts on dangerous tool calls.

Wraps every tool invocation. If the tool name is in the configured
`dangerous_tools` set, calls `interrupt({"tool": ..., "args": ...})` and
gates execution on the result equaling `"approved"`. Anything else
returns a `ToolMessage` saying the user declined.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import interrupt


class PermissionsMiddleware(AgentMiddleware):
    """Interrupts before each call to any tool in `dangerous_tools`."""

    def __init__(self, dangerous_tools: list[str]) -> None:
        self.dangerous = set(dangerous_tools)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        call = request.tool_call
        if call["name"] not in self.dangerous:
            return handler(request)
        decision = interrupt({
            "tool": call["name"],
            "args": call["args"],
            "prompt": f"Approve {call['name']}({call['args']})?",
        })
        if decision == "approved":
            return handler(request)
        return ToolMessage(
            "User declined this tool call.",
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
        )
