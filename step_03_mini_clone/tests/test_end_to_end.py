"""End-to-end smoke test for create_deep_agent."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from graph import create_deep_agent
from tests.conftest import SimpleFakeChatModel


def _call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _setup_skills(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "poetry"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: write short poems\n---\n# Poetry\n"
    )
    return tmp_path


def test_end_to_end(tmp_path) -> None:
    parent = SimpleFakeChatModel(responses=[
        AIMessage(content="", tool_calls=[
            _call("write_todos",
                  {"todos": [{"content": "do it", "status": "pending"}]},
                  "p0"),
        ]),
        AIMessage(content="", tool_calls=[
            _call("load_skill", {"name": "poetry"}, "p1"),
        ]),
        AIMessage(content="", tool_calls=[
            _call("write_file",
                  {"path": "out.txt", "content": "haiku"}, "p2"),
        ]),
        AIMessage(content="all done"),
    ])

    skills = _setup_skills(tmp_path)

    # Patch init_chat_model so create_deep_agent uses our fake.
    with patch("graph.init_chat_model", return_value=parent):
        agent = create_deep_agent(
            model="ignored",
            tools=[],
            instructions="be a deep agent",
            skills_dir=skills,
            require_approval=["write_file"],
        )

    config = {"configurable": {"thread_id": "e2e"}}
    result = agent.invoke({"messages": [HumanMessage("go")]}, config=config)
    # write_file is gated by HITL.
    assert "__interrupt__" in result
    result = agent.invoke(Command(resume="approved"), config=config)

    assert result["files"] == {"out.txt": "haiku"}
    assert result["todos"] == [{"content": "do it", "status": "pending"}]
    assert "all done" in result["messages"][-1].content
