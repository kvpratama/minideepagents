"""Step C.6 — Skills via progressive disclosure.

The agent is told *which* skills are available (from
`<skills_dir>/*/SKILL.md`) but not their contents. When the model decides a
skill is relevant, it calls `load_skill(name)` to pull the markdown into
context. This is deepagents' progressive-disclosure pattern, distilled.

Run:  uv run python step_01_walkthrough/06_skills.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import AnyMessage, HumanMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from utils.config import get_settings

load_dotenv()
settings = get_settings()


SKILLS_DIR = Path(__file__).parent / "skills"


class Todo(TypedDict):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    todos: list[Todo]
    files: dict[str, str]


# --- File tools (copy-forward, trimmed) --------------------------------------


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
                    f"Recorded {len(todos)} todos.", tool_call_id=runtime.tool_call_id
                )
            ],
        }
    )


@tool
def write_file(
    path: str,
    content: str,
    runtime: ToolRuntime,
) -> Command:
    """Create or overwrite a file at `path` with `content`."""
    new_files = {**(runtime.state.get("files") or {}), path: content}
    return Command(
        update={
            "files": new_files,
            "messages": [
                ToolMessage(
                    f"Wrote {len(content)} bytes to {path}.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


# --- Skills ------------------------------------------------------------------


def _discover_skills_sync() -> dict[str, str]:
    """Return {name: short_description} for every SKILL.md under SKILLS_DIR."""
    out: dict[str, str] = {}
    for md in SKILLS_DIR.glob("*/SKILL.md"):
        name = md.parent.name
        text = md.read_text()
        # Naive: pull the description out of the YAML-ish frontmatter.
        desc = name
        for line in text.splitlines():
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip()
                break
        out[name] = desc
    return out


async def _discover_skills() -> dict[str, str]:
    """Return {name: short_description} for every SKILL.md under SKILLS_DIR."""
    return await asyncio.to_thread(_discover_skills_sync)


@tool
def load_skill(name: str) -> str:
    """Load a skill by name. Returns the full SKILL.md contents."""
    path = SKILLS_DIR / name / "SKILL.md"
    if not path.exists():
        return f"Error: skill '{name}' not found"
    return path.read_text()


async def build_agent():
    skills = await _discover_skills()
    skills_block = "\n".join(f"- {n}: {d}" for n, d in skills.items()) or "(none)"
    system = (
        "You are a deep agent. The following skills are available — call "
        "`load_skill(name)` to load any whose guidance is relevant to the "
        f"user's request:\n{skills_block}\n\n"
        "Use `write_file` to save outputs. Use `write_todos` to plan."
    )

    tools = [write_todos, write_file, load_skill]
    model = init_chat_model(
        model=settings.model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value(),
    ).bind_tools(tools)

    def call_model(state: State) -> dict:
        msgs = [{"role": "system", "content": system}] + list(state["messages"])
        return {"messages": [model.invoke(msgs)]}

    def route(state: State) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    g = StateGraph(State)  # ty:ignore[invalid-argument-type]
    g.add_node("model", call_model)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "model")
    g.add_conditional_edges("model", route, {"tools": "tools", END: END})
    g.add_edge("tools", "model")
    return g.compile()


async def main() -> None:
    agent = await build_agent()
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    "Write a haiku about a winter morning to `haiku.txt`. "
                    "Load any skill that might help first."
                )
            ],
            "todos": [],
            "files": {},
        }
    )
    print("\n--- Final files ---")
    for path, content in result["files"].items():
        print(f"\n# {path}\n{content}")


if __name__ == "__main__":
    asyncio.run(main())
