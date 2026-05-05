"""Stage 04 — Hand-rolled ReAct loop.

The biggest conceptual jump in the walkthrough. Up until now we've made
exactly one LLM call per question. Here we let the model **decide what
to do next** in a loop:

    1. We bind three tools to the model: list_tables, get_schema, run_query.
    2. The model emits a tool call.
    3. We execute the tool and feed the result back as a ToolMessage.
    4. The model either calls another tool or produces a final answer.

This is the entire essence of an "agent". `create_agent` (stage 05) is
literally this same loop, written by someone else, with more polish.

Why does this beat stage 03? Because the model only fetches the schema
of tables it actually needs. The schema no longer has to fit in the
prompt up-front.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain_community.utilities import SQLDatabase 
from langchain_core.messages import AIMessage, SystemMessage 
from langchain_core.tools import tool 
from langgraph.graph import END, START, MessagesState, StateGraph 
from langgraph.prebuilt import ToolNode 

from config import get_model  

DB_PATH = Path(__file__).resolve().parent.parent / "chinook.db"

# Module-level DB handle (cheap to introspect; expensive to construct repeatedly).
_DB = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}", sample_rows_in_table_info=3)


# ---- Tools the agent can call ---------------------------------------------
@tool
def list_tables() -> str:
    """List every table name in the Chinook database."""
    return ", ".join(_DB.get_usable_table_names())


@tool
def get_schema(table_names: str) -> str:
    """Get the CREATE TABLE statement and 3 sample rows for one or more
    comma-separated table names (e.g. 'Artist,Album').
    """
    names = [n.strip() for n in table_names.split(",") if n.strip()]
    return _DB.get_table_info(table_names=names)


@tool
def run_query(sql: str) -> str:
    """Execute a read-only SELECT against Chinook. Reject anything else."""
    stripped = sql.strip().rstrip(";").lstrip()
    first_word = stripped.split(None, 1)[0].upper() if stripped else ""
    if first_word != "SELECT":
        return f"ERROR: only SELECT is allowed, got {first_word!r}"
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            cur = conn.execute(stripped)
            rows = cur.fetchall()
    except sqlite3.Error as e:  # surface the error so the LLM can self-correct
        return f"ERROR: {e}"
    return str(rows[:50])  # cap to keep tool output cheap


TOOLS = [list_tables, get_schema, run_query]

SYSTEM_PROMPT = """You answer questions about the Chinook SQLite database
by calling tools. Workflow:

1. Use `list_tables` to discover what exists.
2. Use `get_schema` on the tables you care about.
3. Use `run_query` to execute ONE read-only SELECT (LIMIT 5 by default).
4. Stop calling tools and write a clear final answer.

Rules: SELECT only. Pick named columns, not SELECT *. If a query fails,
read the error and try again."""


# ---- Graph: agent <-> tools ------------------------------------------------
def agent_node(state: MessagesState) -> dict:
    """Call the LLM with tools bound. The LLM decides: tool call, or done."""
    llm = get_model().bind_tools(TOOLS)
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = llm.invoke(messages)
    return {"messages": [response]}


def should_continue(state: MessagesState) -> str:
    """If the last AI message has tool calls, route to tools; else stop."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


tool_node = ToolNode(TOOLS)

builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")
graph = builder.compile(name="stage_04_react_loop")


# ---- CLI -------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", help="Natural language question")
    args = parser.parse_args()

    print(f"Question: {args.question}\n")
    result = graph.invoke(
        {"messages": [{"role": "user", "content": args.question}]},
        {"recursion_limit": 25},
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
