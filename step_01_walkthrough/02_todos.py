"""Step C.2 — Planning with todos.

Adds `write_todos`, a stateful planning tool. The tool returns a
`Command` that simultaneously updates `state.todos` and emits the
`ToolMessage` reply. This is the same pattern deepagents uses for every
state-mutating tool.

Run:  uv run python step_01_walkthrough/02_todos.py
"""

from __future__ import annotations

from dotenv import load_dotenv

from typing import Annotated, Literal, TypedDict

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


@tool
def write_todos(
    todos: list[Todo],
    runtime: ToolRuntime,
) -> Command:
    """Replace the agent's todo list. Use this to plan multi-step work."""
    return Command(update={
        "todos": todos,
        "messages": [ToolMessage(f"Recorded {len(todos)} todos.", tool_call_id=runtime.tool_call_id)],
    })


SYSTEM = (
    "You are a planning agent. For any non-trivial request, first call "
    "`write_todos` to plan your work, then carry out the steps."
)


def build_agent():
    tools = [write_todos]
    model = init_chat_model(
        model=settings.model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value()
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
    result = agent.invoke({
        "messages": [HumanMessage("Plan a 3-day trip to Tokyo. Just write the plan as todos.")],
        "todos": [],
    })
    print("\n--- Final todos ---")
    for t in result["todos"]:
        print(f"[{t['status']}] {t['content']}")


if __name__ == "__main__":
    main()
