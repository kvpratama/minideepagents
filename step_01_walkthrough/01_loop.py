"""Step C.1 — The core agent loop.

A bare LangGraph StateGraph implementing model -> tools -> model -> ... until
the model stops emitting tool calls. This is the kernel that every other
capability in deepagents wraps.

Run:  uv run python step_01_walkthrough/01_loop.py
"""

from __future__ import annotations

from dotenv import load_dotenv
from typing import Annotated, TypedDict

from langchain.chat_models import init_chat_model
from langchain.messages import AnyMessage, HumanMessage
from langchain.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from utils.config import get_settings

load_dotenv()
settings = get_settings()


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"It is 72F and sunny in {city}."


def build_agent():
    tools = [get_weather]
    model = init_chat_model(
        model=settings.model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value()
    ).bind_tools(tools)

    def call_model(state: State) -> dict:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    def route(state: State) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(State)  # ty:ignore[invalid-argument-type]
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "model")
    return graph.compile()


def main() -> None:
    agent = build_agent()
    result = agent.invoke({"messages": [HumanMessage("What's the weather in Paris?")]})
    for msg in result["messages"]:
        msg.pretty_print()


if __name__ == "__main__":
    main()
