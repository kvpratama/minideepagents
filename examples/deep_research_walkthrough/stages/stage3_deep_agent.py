"""Stage 3 — Switch to ``create_deep_agent``.

What's new vs Stage 2
--------------------
Replace ``create_agent`` with ``create_deep_agent``. The agent now gains, for
free, the following built-in tools from the Deep Agents harness:

- ``write_todos`` — task planning (TodoListMiddleware)
- ``ls``, ``read_file``, ``write_file``, ``edit_file``, ``glob``, ``grep`` —
  virtual filesystem (FilesystemMiddleware)
- ``task`` — sub-agent delegation (SubAgentMiddleware) — unused until Stage 4

Our explicit ``tools=[...]`` list is *added on top of* those built-ins.

Run it::

    uv run python stages/stage3_deep_agent.py "Research how Tavily ranks results"
"""

import sys
from datetime import datetime

from deepagents import create_deep_agent

from config import get_model
from stages._shared_tools import tavily_search, think_tool

SYSTEM_PROMPT = f"""You are a research assistant. Today's date is {datetime.now():%Y-%m-%d}.

For any non-trivial request:
1. Use write_todos to break the work into a checklist.
2. Use tavily_search to gather information; call think_tool after each search.
3. Use write_file to save notes to /notes.md as you go.
4. When done, write your final answer to /final_report.md and reply to the
   user with a short summary plus the report path.

Cite sources inline as [1], [2] and end the report with a ### Sources section.
"""

agent = create_deep_agent(
    model=get_model(),
    tools=[tavily_search, think_tool],
    system_prompt=SYSTEM_PROMPT,
)


def main() -> None:
    """Run the stage from the command line."""
    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Research how Tavily ranks results"
    )
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    print(result["messages"][-1].content)
    files = result.get("files", {})
    if files:
        print("\n--- Files in agent state ---")
        for path in files:
            print(f"  {path}")


if __name__ == "__main__":
    main()
