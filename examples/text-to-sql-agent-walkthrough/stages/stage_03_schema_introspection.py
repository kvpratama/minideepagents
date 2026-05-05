"""Stage 03 — Dynamic schema introspection.

Stage 02 hand-wrote the schema as a string literal. That doesn't scale.
Here we replace it with `SQLDatabase.get_table_info()` from
`langchain_community`, which uses SQLAlchemy reflection to produce a
schema description with column types and three sample rows per table.

This is exactly what the SQL toolkit (stages 05+) generates internally.
We're seeing the magic before it disappears behind the framework.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain_community.utilities import SQLDatabase 
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage 
from langgraph.graph import END, START, MessagesState, StateGraph 

from config import get_model 

DB_PATH = Path(__file__).resolve().parent.parent / "chinook.db"


def get_schema_description() -> str:
    """Introspect the database and return a CREATE-TABLE-style description."""
    db = SQLDatabase.from_uri(
        f"sqlite:///{DB_PATH}", sample_rows_in_table_info=3
    )
    return db.get_table_info()


def build_system_prompt() -> str:
    return f"""You translate a natural-language question into ONE
read-only SQLite SELECT statement against the Chinook database.

The actual schema (introspected at runtime, with sample rows):

{get_schema_description()}

Rules:
- Output ONLY the SQL inside a ```sql ... ``` fenced block. No prose.
- SELECT only. No INSERT/UPDATE/DELETE/DROP/ALTER/CREATE.
- Always LIMIT to 5 rows unless the question specifies otherwise.
- Prefer named columns over SELECT *.
"""


def run_sql(sql: str) -> list[tuple]:
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        cur = conn.execute(sql)
        return cur.fetchall()


def extract_sql(text: str) -> str:
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else text).strip().rstrip(";")


def answer(state: MessagesState) -> dict:
    question = state["messages"][-1].content
    llm = get_model()
    response = llm.invoke(
        [
            SystemMessage(content=build_system_prompt()),
            HumanMessage(content=question),
        ]
    )
    sql = extract_sql(response.content)
    rows = run_sql(sql)
    return {
        "messages": [
            AIMessage(content=f"SQL:\n```sql\n{sql}\n```\n\nResult:\n{rows}")
        ]
    }


builder = StateGraph(MessagesState)
builder.add_node("answer", answer)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)
graph = builder.compile(name="stage_03_schema_introspection")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", help="Natural language question")
    args = parser.parse_args()

    print(f"Question: {args.question}\n")
    result = graph.invoke({"messages": [{"role": "user", "content": args.question}]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
