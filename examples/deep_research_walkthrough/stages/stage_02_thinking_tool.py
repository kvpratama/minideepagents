"""Stage 2 — Add ``think_tool`` and a research-focused system prompt.

What's new vs Stage 1
--------------------
1. A second tool, ``think_tool``, that does nothing but record a reflection
   string. The value is in *forcing the model to pause* between searches.
2. A focused system prompt with a tool-call budget and explicit stopping
   criteria. (This is a slimmed version of ``RESEARCHER_INSTRUCTIONS`` from
   the real ``deep_research`` example.)

Same architecture as Stage 1 — just better behavior because the prompt and
the reflection tool shape *how* the loop runs.

Run it::

    uv run python stages/stage_02_thinking_tool.py "Compare uv vs poetry"
"""

import sys
from datetime import datetime

from langchain.agents import create_agent

from config import get_model
from stages._shared_tools import tavily_search, think_tool

SYSTEM_PROMPT = f"""You are a research assistant. Today's date is {datetime.now():%Y-%m-%d}.

You have two tools:
- tavily_search: search the web
- think_tool: pause and reflect after each search

Workflow:
1. Read the question carefully.
2. Start broad, then narrow.
3. After every search, call think_tool to assess: what did I learn? what's
   missing? should I keep searching or answer now?

Hard limits:
- Simple queries: at most 2-3 searches.
- Complex queries: at most 5 searches.
- Stop when you can answer confidently or your last 2 searches were
  redundant.

When you answer, cite sources inline as [1], [2] and end with a ### Sources
section listing each numbered URL.
"""

agent = create_agent(
    model=get_model(),
    tools=[tavily_search, think_tool],
    system_prompt=SYSTEM_PROMPT,
)


def main() -> None:
    """Run the stage from the command line."""
    query = sys.argv[1] if len(sys.argv) > 1 else "Compare uv vs poetry"
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
