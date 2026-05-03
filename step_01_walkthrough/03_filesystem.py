"""Step C.3 — Virtual filesystem in state.

Adds `ls`, `read_file`, `write_file`, `edit_file`. Files live in
`state.files` as a plain dict[str, str]. Read tools return text; write
tools return a `Command` that mutates `state.files` and emits a
`ToolMessage`. This mirrors the StateBackend pattern in real deepagents.

Run:  uv run python step_01_walkthrough/03_filesystem.py
"""

from __future__ import annotations

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


class Todo(TypedDict):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    todos: list[Todo]
    files: dict[str, str]


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
def ls(runtime: ToolRuntime) -> str:
    """List all files in the virtual filesystem."""
    files = runtime.state.get("files") or {}
    if not files:
        return "(no files)"
    return "\n".join(sorted(files.keys()))


@tool
def read_file(
    path: str,
    runtime: ToolRuntime,
) -> str:
    """Read the contents of a file from the virtual filesystem."""

    files = runtime.state.get("files") or {}
    if path not in files:
        return f"Error: {path} not found"
    return files[path]


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


@tool
def edit_file(
    path: str,
    old: str,
    new: str,
    runtime: ToolRuntime,
) -> Command:
    """Replace the first occurrence of `old` with `new` inside `path`."""
    files = dict(runtime.state.get("files") or {})
    if path not in files:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error: {path} not found",
                        tool_call_id=runtime.tool_call_id,
                        status="error",
                    )
                ]
            }
        )
    if old not in files[path]:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error: substring not found in {path}",
                        tool_call_id=runtime.tool_call_id,
                        status="error",
                    )
                ]
            }
        )
    files[path] = files[path].replace(old, new, 1)
    return Command(
        update={
            "files": files,
            "messages": [
                ToolMessage(f"Edited {path}.", tool_call_id=runtime.tool_call_id)
            ],
        }
    )


SYSTEM = (
    "You are a deep agent with access to a virtual filesystem. "
    "Use `write_file`, `read_file`, `edit_file`, and `ls` to manage notes "
    "and intermediate work. Use `write_todos` to plan."
)


def build_agent():
    tools = [write_todos, ls, read_file, write_file, edit_file]
    model = init_chat_model(
        model=settings.model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value(),
    ).bind_tools(tools)

    def call_model(state: State) -> dict:
        msgs = [{"role": "system", "content": SYSTEM}] + list(state["messages"])
        return {"messages": [model.invoke(msgs)]}

    def route(state: State) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(State)  # ty:ignore[invalid-argument-type]
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "model")
    return graph.compile()


def main() -> None:
    agent = build_agent()
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    "Write a short haiku about autumn to `notes/haiku.txt`, "
                    "then read it back and confirm what you wrote."
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
    main()
