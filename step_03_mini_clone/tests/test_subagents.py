"""Tests for SubagentsMiddleware."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

from backends.state import StateBackend
from middleware.filesystem import FilesystemMiddleware
from middleware.subagents import SubagentsMiddleware
from tests.conftest import SimpleFakeChatModel


def _call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class TestSubagentsMiddleware:
    def test_general_purpose_writes_to_shared_files(self) -> None:
        # Child speaks first (it runs to completion before parent resumes).
        child_model = SimpleFakeChatModel(responses=[
            AIMessage(content="", tool_calls=[
                _call("write_file",
                      {"path": "out.txt", "content": "child wrote"}, "ck1"),
            ]),
            AIMessage(content="wrote out.txt"),
        ])
        parent_model = SimpleFakeChatModel(responses=[
            AIMessage(content="", tool_calls=[
                _call("task",
                      {"description": "write the file",
                       "subagent_type": "general-purpose"}, "p1"),
            ]),
            AIMessage(content="all done"),
        ])

        backend = StateBackend()
        agent = create_agent(
            model=parent_model,
            tools=[],
            middleware=[
                FilesystemMiddleware(backend=backend),
                SubagentsMiddleware(
                    child_model=child_model,
                    backend=backend,
                    subagents=[],
                ),
            ],
        )
        result = agent.invoke({"messages": [HumanMessage("delegate")]})
        assert result["files"] == {"out.txt": "child wrote"}

    def test_unknown_subagent_returns_error(self) -> None:
        parent_model = SimpleFakeChatModel(responses=[
            AIMessage(content="", tool_calls=[
                _call("task",
                      {"description": "go", "subagent_type": "missing"}, "p1"),
            ]),
            AIMessage(content="ok"),
        ])
        agent = create_agent(
            model=parent_model,
            tools=[],
            middleware=[
                FilesystemMiddleware(backend=StateBackend()),
                SubagentsMiddleware(
                    child_model=SimpleFakeChatModel(responses=[]),
                    backend=StateBackend(),
                    subagents=[],
                ),
            ],
        )
        result = agent.invoke({"messages": [HumanMessage("delegate")]})
        tool_msgs = [m for m in result["messages"] if m.type == "tool"]
        assert any("unknown subagent_type" in (m.content or "")
                   for m in tool_msgs)
