"""Stage 01 — Raw SQL.

The bedrock primitive. No LLM, no agent framework, no tools. Just `sqlite3`
talking to the Chinook database. Everything we build later is fancy
machinery for *generating* the SQL string we hand to this layer.

Studio note:
    A LangGraph Studio graph must expose a compiled graph object as
    `graph`. Stage 01 has no LLM, so we wrap the SQL execution in a
    single-node `StateGraph`. Whatever question you type in Studio is
    ignored; the graph always runs the same demo query. The point of
    this stage is to *see* the SQL primitive, not to interpret intent.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph

DB_PATH = Path(__file__).resolve().parent.parent / "chinook.db"

# A fixed demo query. Stage 02 will let the LLM generate this string.
DEMO_SQL = """
SELECT Name AS Artist
FROM Artist
ORDER BY ArtistId
LIMIT 5;
"""


def run_sql(sql: str) -> list[tuple]:
    """Execute a read-only SQL string against Chinook and return rows."""
    if not DB_PATH.exists():
        msg = f"Chinook database not found at {DB_PATH}. Run `make download-db`."
        raise FileNotFoundError(msg)
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        cur = conn.execute(sql)
        return cur.fetchall()


def execute_demo(state: MessagesState) -> dict:
    """The single graph node — runs the fixed demo query."""
    rows = run_sql(DEMO_SQL)
    answer = (
        "Stage 01 ignores the question and runs a fixed query.\n"
        f"SQL:\n{DEMO_SQL.strip()}\n\nResult:\n{rows}"
    )
    return {"messages": [AIMessage(content=answer)]}


# ---- LangGraph Studio entry point ------------------------------------------
builder = StateGraph(MessagesState)
builder.add_node("execute_demo", execute_demo)
builder.add_edge(START, "execute_demo")
builder.add_edge("execute_demo", END)
graph = builder.compile(name="stage_01_raw_sql")


# ---- CLI entry point -------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="?", default="(ignored)")
    args = parser.parse_args()

    print(f"Question: {args.question}  (stage 01 ignores this)\n")
    result = graph.invoke({"messages": [{"role": "user", "content": args.question}]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
