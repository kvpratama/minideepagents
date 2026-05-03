"""Step C.5 — Permissions via HITL interrupts.

Before each call to a "dangerous" tool (here: `write_file`, `edit_file`),
a permissions node calls `interrupt(...)` to ask the human for approval.
The graph pauses; the host resumes with `Command(resume={"approved": ...})`.

To keep the demo runnable without a TTY, we use an in-memory checkpointer
and auto-approve every interrupt programmatically. In a real app the resume
value would come from a UI.

Run:  uv run python step_01_walkthrough/05_permissions.py
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from utils.config import get_settings

load_dotenv()
settings = get_settings()


DANGEROUS = {"write_file", "edit_file"}


class Todo(TypedDict):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    todos: list[Todo]
    files: dict[str, str]


# --- Tools (copy-forward, trimmed for brevity) -------------------------------


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


# --- Permissions node --------------------------------------------------------


def permissions_node(state: State) -> dict:
    """Inspect the last AIMessage; for every dangerous tool call, ask the
    human. Replace declined calls with synthetic ToolMessages so the model
    never sees them executed.
    """
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {}

    declined_messages: list[ToolMessage] = []
    surviving_calls = []
    for call in last.tool_calls:
        if call["name"] in DANGEROUS:
            decision = interrupt(
                {
                    "tool": call["name"],
                    "args": call["args"],
                    "prompt": f"Approve {call['name']}({call['args']})?",
                }
            )
            if not decision.get("approved"):
                declined_messages.append(
                    ToolMessage(
                        "User declined this tool call.",
                        tool_call_id=call["id"],
                        name=call["name"],
                    )
                )
                continue
        surviving_calls.append(call)

    if not declined_messages:
        return {}

    # Rewrite the AIMessage to keep only approved calls, then attach declines.
    rewritten = AIMessage(
        content=last.content,
        tool_calls=surviving_calls,
        id=last.id,
    )
    return {"messages": [rewritten, *declined_messages]}


SYSTEM = (
    "You are a deep agent with file tools. Writes and edits require human "
    "approval; reads do not. Plan with `write_todos`."
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

    def route_after_model(state: State) -> str:
        last = state["messages"][-1]
        return "permissions" if getattr(last, "tool_calls", None) else END

    def route_after_permissions(state: State) -> str:
        # last = state["messages"][-1]
        # If the last AIMessage still has any tool_calls, run them.
        ai = next(
            (m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None
        )
        if ai and ai.tool_calls:
            return "tools"
        return "model"  # all calls were declined; let the model react

    g = StateGraph(State)  # ty:ignore[invalid-argument-type]
    g.add_node("model", call_model)
    g.add_node("permissions", permissions_node)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "model")
    g.add_conditional_edges(
        "model", route_after_model, {"permissions": "permissions", END: END}
    )
    g.add_conditional_edges(
        "permissions", route_after_permissions, {"tools": "tools", "model": "model"}
    )
    g.add_edge("tools", "model")
    return g.compile(checkpointer=InMemorySaver())


def main() -> None:
    agent = build_agent()
    config = {"configurable": {"thread_id": "demo"}}
    inputs = {
        "messages": [
            HumanMessage("Write a one-line motto to `motto.txt`, then read it back.")
        ],
        "todos": [],
        "files": {},
    }

    # Drive the graph manually so we can auto-approve interrupts.
    state = agent.invoke(inputs, config=config)
    while "__interrupt__" in state:
        ints = state["__interrupt__"]
        print(f"\n[HITL] Auto-approving: {ints[0].value['prompt']}")
        state = agent.invoke(Command(resume={"approved": True}), config=config)

    print("\n--- Final files ---")
    for path, content in state["files"].items():
        print(f"\n# {path}\n{content}")


if __name__ == "__main__":
    main()
