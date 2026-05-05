"""Stage 06 — Minimal Deep Agent.

We swap one function: `create_agent` → `create_deep_agent`. Nothing else
changes. The agent now silently inherits four pieces of middleware:

    - TodoListMiddleware    (the `write_todos` planning tool)
    - FilesystemMiddleware  (ls / read_file / write_file / edit_file / glob / grep)
    - SubAgentMiddleware    (the `task` tool to spawn focused subagents)
    - SummarizationMiddleware (auto-summarize when the message history grows)

We don't *use* AGENTS.md, skills, or a persistent backend yet — those are
stages 07, 08, 09. The point of this stage is to feel the upgrade.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deepagents import create_deep_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase

from config import get_model

DB_PATH = Path(__file__).resolve().parent.parent / "chinook.db"

SYSTEM_PROMPT = """You answer questions about the Chinook SQLite database.

For complex multi-step questions, use `write_todos` to plan first.

SQL tools available:
    sql_db_list_tables, sql_db_schema, sql_db_query_checker, sql_db_query

Rules: SELECT only. Named columns, not SELECT *. Default LIMIT 5."""


def build_graph():
    db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}", sample_rows_in_table_info=3)
    llm = get_model()
    tools = SQLDatabaseToolkit(db=db, llm=llm).get_tools()
    return create_deep_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)


graph = build_graph()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", help="Natural language question")
    args = parser.parse_args()

    print(f"Question: {args.question}\n")
    result = graph.invoke(
        {"messages": [{"role": "user", "content": args.question}]},
        {"recursion_limit": 50},
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
