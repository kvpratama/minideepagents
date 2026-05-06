"""Stage 4 — Add a research sub-agent.

What's new vs Stage 3
--------------------
We define a single sub-agent, ``research-agent``, with its own focused system
prompt and a *narrow* tool list (just ``tavily_search`` + ``think_tool``).
The orchestrator keeps the broad toolset; it delegates research work via the
``task`` tool, which the SubAgentMiddleware already registered.

Why bother? **Context isolation.** Each sub-agent runs in its own context
window. The orchestrator only sees the sub-agent's *final summary*, not the
raw web pages it read along the way.

Run it::

    uv run python stages/stage_04_subagent.py "Compare DuckDB vs SQLite for analytics"
"""

import sys
from datetime import datetime

from deepagents import create_deep_agent

from config import get_model
from stages._shared_tools import tavily_search, think_tool

ORCHESTRATOR_PROMPT = """You are a research orchestrator.

For any research request:
1. Call write_todos to break it into focused sub-tasks.
2. For each sub-task, call the `task` tool to delegate to the
   `research-agent` sub-agent. Give one focused topic per delegation.
   Issue multiple task() calls in a single response to run sub-agents in
   parallel when sub-tasks are independent.
3. When all sub-agents have returned, consolidate citations (each unique URL
   gets one number) and write a final report to /final_report.md.
4. Reply to the user with a short summary plus the report path.

Do NOT call tavily_search yourself — always delegate to research-agent.
"""

RESEARCHER_PROMPT = f"""You are a focused research sub-agent. Today's date is {datetime.now():%Y-%m-%d}.

You research ONE topic and return findings to the orchestrator.

Tools: tavily_search, think_tool.

Workflow:
- Start broad, narrow as you learn.
- Call think_tool after every search.
- Stop after at most 3 searches for simple topics, 5 for complex.

Return findings with inline [1], [2] citations and a ### Sources section
listing each numbered URL.
"""

research_sub_agent = {
    "name": "research-agent",
    "description": (
        "Delegate one focused research topic. Returns findings with cited "
        "sources. Give the sub-agent a single topic per call."
    ),
    "system_prompt": RESEARCHER_PROMPT,
    "tools": [tavily_search, think_tool],
}

agent = create_deep_agent(
    model=get_model(),
    tools=[tavily_search, think_tool],
    system_prompt=ORCHESTRATOR_PROMPT,
    subagents=[research_sub_agent],
)


def main() -> None:
    """Run the stage from the command line."""
    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Compare DuckDB vs SQLite for analytics"
    )
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    print(result["messages"][-1].content)
    files = result.get("files", {})
    if "/final_report.md" in files:
        print("\n--- /final_report.md ---")
        print(files["/final_report.md"])


if __name__ == "__main__":
    main()
