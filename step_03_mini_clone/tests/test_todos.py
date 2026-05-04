"""Tests for TodosMiddleware."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from middleware.todos import TodosMiddleware


def _write_todos_call(call_id: str, todos: list[dict]) -> dict:
    return {
        "name": "write_todos",
        "args": {"todos": todos},
        "id": call_id,
        "type": "tool_call",
    }


class TestTodosMiddleware:
    def test_registers_write_todos_tool(self, make_fake_model) -> None:
        agent = create_agent(
            model=make_fake_model([AIMessage(content="ok")]),
            tools=[],
            middleware=[TodosMiddleware()],
        )
        tools = agent.nodes["tools"].bound._tools_by_name
        assert "write_todos" in tools

    def test_write_todos_updates_state(self, make_fake_model) -> None:
        todos = [{"content": "step 1", "status": "pending"}]
        model = make_fake_model([
            AIMessage(content="", tool_calls=[_write_todos_call("c1", todos)]),
            AIMessage(content="done"),
        ])
        agent = create_agent(
            model=model,
            tools=[],
            middleware=[TodosMiddleware()],
        )
        result = agent.invoke({"messages": [HumanMessage("plan it")]})
        assert result["todos"] == todos
