"""Stage 5 — The full orchestrator (matches ``examples/deep_research/agent.py``).

What's new vs Stage 4
--------------------
The architecture is identical to Stage 4. The difference is the **prompts**.
Here we use the full three-prompt set vendored from the real example:

- ``RESEARCH_WORKFLOW_INSTRUCTIONS``      — orchestrator workflow + report rules
- ``SUBAGENT_DELEGATION_INSTRUCTIONS``    — delegation strategy + limits
- ``RESEARCHER_INSTRUCTIONS``             — sub-agent search & reflection rules

Run it::

    uv run python stages/stage_05_full_orchestrator.py "What are the top 5 LLM coding agents in 2025?"
"""

import sys
from datetime import datetime

from deepagents import create_deep_agent

from config import get_model
from stages._shared_tools import tavily_search, think_tool

# --- vendored from research_agent/prompts.py -------------------------------
RESEARCH_WORKFLOW_INSTRUCTIONS = """# Research Workflow

Follow this workflow for all research requests:

1. **Plan**: Create a todo list with write_todos to break down the research into focused tasks
2. **Save the request**: Use write_file() to save the user's research question to `/research_request.md`
3. **Research**: Delegate research tasks to sub-agents using the task() tool - ALWAYS use sub-agents for research, never conduct research yourself
4. **Synthesize**: Review all sub-agent findings and consolidate citations (each unique URL gets one number across all findings)
5. **Write Report**: Write a comprehensive final report to `/final_report.md`
6. **Verify**: Read `/research_request.md` and confirm you've addressed all aspects with proper citations and structure

## Research Planning Guidelines
- Batch similar research tasks into a single TODO to minimize overhead
- For simple fact-finding questions, use 1 sub-agent
- For comparisons or multi-faceted topics, delegate to multiple parallel sub-agents
- Each sub-agent should research one specific aspect and return findings

## Report Writing Guidelines

**For comparisons:** Introduction → Overview A → Overview B → Detailed comparison → Conclusion
**For lists/rankings:** Just list items with details — no introduction needed
**For summaries:** Overview → key concepts → conclusion

**Citations:**
- Cite sources inline as [1], [2], [3]
- Each unique URL gets one number across ALL sub-agent findings
- End with a ### Sources section, one URL per line: `[1] Title: URL`
"""

SUBAGENT_DELEGATION_INSTRUCTIONS = """# Sub-Agent Research Coordination

Coordinate research by delegating tasks from your TODO list to specialized
research sub-agents.

## Delegation Strategy

**DEFAULT: Start with 1 sub-agent** for most queries:
- "What is quantum computing?" → 1 sub-agent
- "List the top 10 coffee shops in San Francisco" → 1 sub-agent
- "Research context engineering for AI agents" → 1 sub-agent

**ONLY parallelize when the query EXPLICITLY requires comparison or has
clearly independent aspects:**

- "Compare OpenAI vs Anthropic vs DeepMind" → 3 parallel sub-agents
- "Renewable energy in Europe, Asia, North America" → 3 parallel sub-agents

## Key Principles
- Bias towards a single sub-agent: one comprehensive task is more
  token-efficient than many narrow ones.
- Avoid premature decomposition.
- Parallelize only for clear comparisons.

## Limits
- At most {max_concurrent_research_units} parallel sub-agents per iteration.
- Issue multiple task() calls in a single response for parallel execution.
- Stop after {max_researcher_iterations} delegation rounds if you still lack
  adequate sources.
"""

RESEARCHER_INSTRUCTIONS = """You are a research assistant conducting research on the user's input topic. Today's date is {date}.

<Task>
Use the research tools to gather information about the user's input topic.
You may call tools in series or in parallel.
</Task>

<Available Research Tools>
1. **tavily_search** — web search
2. **think_tool** — strategic reflection
**CRITICAL: call think_tool after each search.**
</Available Research Tools>

<Instructions>
1. Read the question carefully.
2. Start with broad queries.
3. After each search, pause and assess.
4. Narrow down as you go.
5. Stop when you can answer confidently.
</Instructions>

<Hard Limits>
- Simple queries: 2-3 search calls.
- Complex queries: up to 5 search calls.
- Always stop after 5 if you still cannot find sources.
- Stop immediately when you can answer comprehensively, have 3+ relevant
  sources, or your last 2 searches returned similar information.
</Hard Limits>

<Final Response Format>
Cite sources inline as [1], [2], [3] and end with a ### Sources section
listing each numbered URL with its title.
</Final Response Format>
"""
# ---------------------------------------------------------------------------

MAX_CONCURRENT_RESEARCH_UNITS = 3
MAX_RESEARCHER_ITERATIONS = 3
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")

INSTRUCTIONS = (
    RESEARCH_WORKFLOW_INSTRUCTIONS
    + "\n\n"
    + "=" * 80
    + "\n\n"
    + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
        max_concurrent_research_units=MAX_CONCURRENT_RESEARCH_UNITS,
        max_researcher_iterations=MAX_RESEARCHER_ITERATIONS,
    )
)

research_sub_agent = {
    "name": "research-agent",
    "description": (
        "Delegate research to the sub-agent researcher. Only give this "
        "researcher one topic at a time."
    ),
    "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=CURRENT_DATE),
    "tools": [tavily_search, think_tool],
}

agent = create_deep_agent(
    model=get_model(),
    tools=[tavily_search, think_tool],
    system_prompt=INSTRUCTIONS,
    subagents=[research_sub_agent],
)


def main() -> None:
    """Run the stage from the command line."""
    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What are the top 5 LLM coding agents in 2025?"
    )
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    print(result["messages"][-1].content)
    files = result.get("files", {})
    if "/final_report.md" in files:
        print("\n--- /final_report.md ---")
        print(files["/final_report.md"])


if __name__ == "__main__":
    main()
