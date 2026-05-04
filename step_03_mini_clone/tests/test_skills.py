"""Tests for SkillsMiddleware."""

from __future__ import annotations

from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from middleware.skills import SkillsMiddleware


def _call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _build_skills(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "poetry"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: write short poems\n"
        "---\n"
        "# Poetry\n\nDo poetry.\n"
    )
    return tmp_path


class TestSkillsMiddleware:
    def test_load_skill_tool_returns_skill_md(self, make_fake_model, tmp_path) -> None:
        skills_dir = _build_skills(tmp_path)
        model = make_fake_model([
            AIMessage(content="", tool_calls=[
                _call("load_skill", {"name": "poetry"}, "c1"),
            ]),
            AIMessage(content="ok"),
        ])
        mw = SkillsMiddleware(skills_dir=skills_dir)
        agent = create_agent(model=model, tools=[], middleware=[mw])
        result = agent.invoke({"messages": [HumanMessage("use poetry")]})
        tool_msgs = [m for m in result["messages"] if m.type == "tool"]
        assert any("Do poetry" in (m.content or "") for m in tool_msgs)

    def test_load_skill_unknown(self, make_fake_model, tmp_path) -> None:
        skills_dir = _build_skills(tmp_path)
        model = make_fake_model([
            AIMessage(content="", tool_calls=[
                _call("load_skill", {"name": "nope"}, "c1"),
            ]),
            AIMessage(content="ok"),
        ])
        mw = SkillsMiddleware(skills_dir=skills_dir)
        agent = create_agent(model=model, tools=[], middleware=[mw])
        result = agent.invoke({"messages": [HumanMessage("use nope")]})
        tool_msgs = [m for m in result["messages"] if m.type == "tool"]
        assert any("not found" in (m.content or "") for m in tool_msgs)

    def test_system_prompt_lists_skills(self, make_fake_model, tmp_path) -> None:
        """Verify the catalog block contains skill name and description."""
        skills_dir = _build_skills(tmp_path)
        mw = SkillsMiddleware(skills_dir=skills_dir)
        block = mw._catalog_block()
        assert "poetry" in block
        assert "write short poems" in block
