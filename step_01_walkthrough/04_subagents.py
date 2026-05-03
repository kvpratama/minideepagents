"""Step C.4 — Subagents via the `task` tool.

`task(description)` invokes a child agent graph with isolated message
history but shared files. The child runs the same loop as the parent and
returns its final text reply, which becomes the parent's ToolMessage
content. This is the deepagents subagent pattern in miniature.

Run:  uv run python step_01_walkthrough/04_subagents.py
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


# --- Filesystem + todos tools (copy-forward from 03) -------------------------


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


# --- Subagent ----------------------------------------------------------------

SUBAGENT_SYSTEM = (
    "You are a focused subagent. Complete the task described in the user "
    "message using the tools available, then reply with a concise summary "
    "of what you did. You do not have access to `task`."
)


def _build_subagent_graph():
    """A child graph: same kernel as the parent, but no `task` tool."""
    tools = [ls, read_file, write_file]
    model = init_chat_model(
        model=settings.model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value(),
    ).bind_tools(tools)

    def call_model(state: State) -> dict:
        msgs = [{"role": "system", "content": SUBAGENT_SYSTEM}] + list(
            state["messages"]
        )
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


def _make_task_tool():
    subagent = _build_subagent_graph()

    @tool
    def task(
        description: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Delegate a focused sub-task to a fresh subagent.

        The subagent has access to the shared filesystem but starts with an
        empty message history. Returns the subagent's final reply.
        """
        result = subagent.invoke(
            {
                "messages": [HumanMessage(description)],
                "todos": [],
                "files": runtime.state.get("files") or {},
            }
        )
        reply = result["messages"][-1].content
        return Command(
            update={
                "files": result.get("files") or runtime.state.get("files") or {},
                "messages": [
                    ToolMessage(str(reply), tool_call_id=runtime.tool_call_id)
                ],
            }
        )

    return task


# --- Parent agent ------------------------------------------------------------

PARENT_SYSTEM = (
    "You are an orchestrator. For focused sub-tasks (research, summarization, "
    "drafting), delegate to a subagent via the `task` tool. The subagent "
    "shares your filesystem but not your message history."
)


def build_agent():
    task_tool = _make_task_tool()
    tools = [write_todos, ls, read_file, write_file, task_tool]
    model = init_chat_model(
        model=settings.model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value(),
    ).bind_tools(tools)

    def call_model(state: State) -> dict:
        msgs = [{"role": "system", "content": PARENT_SYSTEM}] + list(state["messages"])
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


def main() -> None:
    agent = build_agent()
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    "Use a subagent to write a 4-line poem about the ocean to "
                    "`poems/ocean.txt`, then read it back yourself and tell me if "
                    "you like it."
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
