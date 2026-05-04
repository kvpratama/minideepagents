"""Tests for PermissionsMiddleware."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backends.state import StateBackend
from middleware.filesystem import FilesystemMiddleware
from middleware.permissions import PermissionsMiddleware


def _call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _build_agent(model):
    return create_agent(
        model=model,
        tools=[],
        middleware=[
            FilesystemMiddleware(backend=StateBackend()),
            PermissionsMiddleware(dangerous_tools=["write_file"]),
        ],
        checkpointer=InMemorySaver(),
    )


class TestPermissionsMiddleware:
    def test_approval_proceeds(self, make_fake_model) -> None:
        model = make_fake_model([
            AIMessage(content="", tool_calls=[
                _call("write_file", {"path": "a.txt", "content": "hi"}, "c1"),
            ]),
            AIMessage(content="done"),
        ])
        agent = _build_agent(model)
        config = {"configurable": {"thread_id": "t1"}}
        result = agent.invoke({"messages": [HumanMessage("write")]}, config=config)
        assert "__interrupt__" in result
        result = agent.invoke(Command(resume="approved"), config=config)
        assert result["files"] == {"a.txt": "hi"}

    def test_rejection_returns_error_tool_message(self, make_fake_model) -> None:
        model = make_fake_model([
            AIMessage(content="", tool_calls=[
                _call("write_file", {"path": "a.txt", "content": "hi"}, "c1"),
            ]),
            AIMessage(content="ok, will skip"),
        ])
        agent = _build_agent(model)
        config = {"configurable": {"thread_id": "t2"}}
        agent.invoke({"messages": [HumanMessage("write")]}, config=config)
        result = agent.invoke(Command(resume="declined"), config=config)
        assert result.get("files", {}) == {}
        tool_msgs = [m for m in result["messages"] if m.type == "tool"]
        assert any("declined" in (m.content or "").lower() for m in tool_msgs)

    def test_safe_tool_skips_interrupt(self, make_fake_model) -> None:
        model = make_fake_model([
            AIMessage(content="", tool_calls=[_call("ls", {}, "c1")]),
            AIMessage(content="done"),
        ])
        agent = _build_agent(model)
        config = {"configurable": {"thread_id": "t3"}}
        result = agent.invoke({"messages": [HumanMessage("list")]}, config=config)
        assert "__interrupt__" not in result
