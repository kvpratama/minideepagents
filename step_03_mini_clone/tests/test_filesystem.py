"""Tests for FilesystemMiddleware."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from backends.state import StateBackend
from middleware.filesystem import FilesystemMiddleware


def _call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


class TestFilesystemMiddleware:
    def test_registers_four_tools(self, make_fake_model) -> None:
        agent = create_agent(
            model=make_fake_model([AIMessage(content="ok")]),
            tools=[],
            middleware=[FilesystemMiddleware(backend=StateBackend())],
        )
        tools = agent.nodes["tools"].bound._tools_by_name
        for name in ("ls", "read_file", "write_file", "edit_file"):
            assert name in tools

    def test_write_then_read(self, make_fake_model) -> None:
        model = make_fake_model([
            AIMessage(content="", tool_calls=[
                _call("write_file", {"path": "a.txt", "content": "hi"}, "c1"),
            ]),
            AIMessage(content="", tool_calls=[
                _call("read_file", {"path": "a.txt"}, "c2"),
            ]),
            AIMessage(content="done"),
        ])
        agent = create_agent(
            model=model,
            tools=[],
            middleware=[FilesystemMiddleware(backend=StateBackend())],
        )
        result = agent.invoke({"messages": [HumanMessage("write a file")]})
        assert result["files"] == {"a.txt": "hi"}
        # The read_file ToolMessage should contain "hi"
        tool_msgs = [m for m in result["messages"] if m.type == "tool"]
        assert any("hi" in (m.content or "") for m in tool_msgs)

    def test_edit_substring_missing(self, make_fake_model) -> None:
        model = make_fake_model([
            AIMessage(content="", tool_calls=[
                _call("write_file", {"path": "a.txt", "content": "hello"}, "c1"),
            ]),
            AIMessage(content="", tool_calls=[
                _call("edit_file", {"path": "a.txt", "old": "X", "new": "Y"}, "c2"),
            ]),
            AIMessage(content="done"),
        ])
        agent = create_agent(
            model=model,
            tools=[],
            middleware=[FilesystemMiddleware(backend=StateBackend())],
        )
        result = agent.invoke({"messages": [HumanMessage("edit it")]})
        # File unchanged
        assert result["files"] == {"a.txt": "hello"}
        # Error surfaced as ToolMessage
        tool_msgs = [m for m in result["messages"] if m.type == "tool"]
        assert any("substring not found" in (m.content or "") for m in tool_msgs)
