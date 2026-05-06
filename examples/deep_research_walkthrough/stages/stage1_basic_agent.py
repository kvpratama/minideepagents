"""Stage 1 — Plain LangChain agent with one tool.

What's new in this stage
-----------------------
This is the floor: a stock LangChain ``create_agent`` agent given exactly one
tool (``tavily_search``) and no system prompt. Run a query and watch the
agent loop call the search tool until it produces an answer.

There is **no** planning, **no** filesystem, **no** sub-agents yet — that's
what later stages add.

Run it::

    uv run python stages/stage1_basic_agent.py "What is LangGraph?"
"""

import sys

from langchain.agents import create_agent

from config import get_model
from stages._shared_tools import tavily_search

agent = create_agent(
    model=get_model(),
    tools=[tavily_search],
)


def main() -> None:
    """Run the stage from the command line."""
    query = sys.argv[1] if len(sys.argv) > 1 else "What is LangGraph?"
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
