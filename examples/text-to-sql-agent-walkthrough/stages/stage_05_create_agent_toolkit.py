"""Stage 05 — `create_agent` + `SQLDatabaseToolkit`.

The hand-rolled loop from stage 04 disappears into one function call. We
also stop hand-rolling the SQL tools and use the curated bundle from
`langchain_community`. Same behavior, dramatically less code.

What `SQLDatabaseToolkit` gives you:
    - sql_db_list_tables   (≈ stage 04's list_tables)
    - sql_db_schema        (≈ stage 04's get_schema)
    - sql_db_query         (≈ stage 04's run_query)
    - sql_db_query_checker (NEW — uses an LLM to lint SQL before running)

Compare line counts: stage 04 ≈ 110 lines, stage 05 ≈ 50 lines.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain.agents import create_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase

from config import get_model

DB_PATH = Path(__file__).resolve().parent.parent / "chinook.db"

SYSTEM_PROMPT = """You answer questions about the Chinook SQLite database
by calling tools. Workflow:

1. Use sql_db_list_tables to discover what exists.
2. Use sql_db_schema on the tables you care about.
3. Use sql_db_query_checker on your SQL before running it.
4. Use sql_db_query to execute. LIMIT 5 by default.
5. Write a clear final answer.

Rules: SELECT only. Named columns, not SELECT *."""


def build_graph():
    db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}", sample_rows_in_table_info=3)
    llm = get_model()
    tools = SQLDatabaseToolkit(db=db, llm=llm).get_tools()
    return create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)


graph = build_graph()


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
