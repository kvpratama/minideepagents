"""SubagentsMiddleware — registers a `task` tool that runs a child agent.

Subagents share the parent's filesystem (same `files` channel) but have
isolated `messages`. The `task` tool packages the parent's `files` into
the child's input state, runs the child to completion, then returns the
child's last message *and* its updated `files` to the parent via a
`Command` update.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentMiddleware
from langchain.messages import HumanMessage, ToolMessage
from langchain.tools import BaseTool, ToolRuntime, tool
from langchain_core.language_models import BaseChatModel
from langgraph.types import Command

from step_03_mini_clone.backends.protocol import FilesystemBackend
from step_03_mini_clone.middleware.filesystem import FilesystemMiddleware

_DEFAULT_PROMPT = (
    "You are a focused subagent. Complete the task in the user message "
    "using the tools available, then reply with a concise summary of "
    "what you did. You do not have access to `task`."
)


def _build_child(
    *,
    model: BaseChatModel,
    backend: FilesystemBackend,
    prompt: str,
    extra_tools: list[BaseTool],
):
    return create_agent(
        model=model,
        tools=extra_tools,
        middleware=[FilesystemMiddleware(backend=backend)],
        system_prompt=prompt,
    )


class SubagentsMiddleware(AgentMiddleware):
    """Adds the `task` tool that delegates to one of N child agents."""

    def __init__(
        self,
        *,
        child_model: BaseChatModel,
        backend: FilesystemBackend,
        subagents: list[dict],
        parent_user_tools: list[BaseTool] | None = None,
    ) -> None:
        user_tools = list(parent_user_tools or [])

        registry: dict[str, Any] = {
            "general-purpose": _build_child(
                model=child_model, backend=backend,
                prompt=_DEFAULT_PROMPT, extra_tools=user_tools,
            ),
        }
        for spec in subagents:
            registry[spec["name"]] = _build_child(
                model=child_model, backend=backend,
                prompt=spec.get("prompt", _DEFAULT_PROMPT),
                extra_tools=spec.get("tools") or user_tools,
            )

        catalog_lines = ["- general-purpose: default subagent"]
        catalog_lines += [f"- {s['name']}: {s['description']}" for s in subagents]
        catalog = "\n".join(catalog_lines)

        @tool
        def task(
            description: str,
            subagent_type: str,
            runtime: ToolRuntime,
        ) -> Command:
            """Delegate a focused sub-task to a named subagent."""
            graph = registry.get(subagent_type)
            if graph is None:
                return Command(update={"messages": [ToolMessage(
                    f"Error: unknown subagent_type '{subagent_type}'. "
                    f"Available: {sorted(registry)}",
                    tool_call_id=runtime.tool_call_id, status="error")]})
            child_state = graph.invoke({
                "messages": [HumanMessage(description)],
                "files": runtime.state.get("files") or {},
            })
            reply = child_state["messages"][-1].content
            return Command(update={
                "files": child_state.get("files")
                         or runtime.state.get("files") or {},
                "messages": [ToolMessage(
                    str(reply), tool_call_id=runtime.tool_call_id)],
            })

        task.description = (
            "Delegate a focused sub-task to one of the available subagents. "
            "Subagents share the filesystem but start with empty message "
            f"history.\nAvailable subagents:\n{catalog}"
        )
        self.tools = [task]
