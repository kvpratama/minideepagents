"""Stage 02 — One-shot LLM → SQL.

We add an LLM. The whole pipeline is now:

    user question
        + hardcoded schema
            -> single LLM call
                -> SQL string
                    -> sqlite3 execution
                        -> printed result

The LLM never sees the database. We hardcode a tiny schema description
into the prompt. This is the *minimum* a model needs to produce SQL.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  
from langgraph.graph import END, START, MessagesState, StateGraph  

from config import get_model 

DB_PATH = Path(__file__).resolve().parent.parent / "chinook.db"

# Hardcoded schema. Stage 03 will introspect this dynamically.
HARDCODED_SCHEMA = """
Tables in the Chinook SQLite database:

- Artist(ArtistId PK, Name)
- Album(AlbumId PK, Title, ArtistId FK -> Artist)
- Track(TrackId PK, Name, AlbumId FK -> Album, GenreId, MediaTypeId,
        Composer, Milliseconds, Bytes, UnitPrice)
- Genre(GenreId PK, Name)
- Customer(CustomerId PK, FirstName, LastName, Country, Email,
           SupportRepId FK -> Employee)
- Employee(EmployeeId PK, FirstName, LastName, Title, ReportsTo, Country)
- Invoice(InvoiceId PK, CustomerId FK, InvoiceDate, Total, BillingCountry)
- InvoiceLine(InvoiceLineId PK, InvoiceId FK, TrackId FK, UnitPrice, Quantity)
"""

SYSTEM_PROMPT = f"""You translate a natural-language question into ONE
read-only SQLite SELECT statement against the Chinook database.

{HARDCODED_SCHEMA}

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
    """Pull SQL out of a ```sql ... ``` fence. Fall back to raw text."""
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else text).strip().rstrip(";")


def answer(state: MessagesState) -> dict:
    """One LLM call → SQL → execute → return result."""
    question = state["messages"][-1].content
    llm = get_model()
    response = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]
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
graph = builder.compile(name="stage_02_llm_one_shot")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", help="Natural language question")
    args = parser.parse_args()

    print(f"Question: {args.question}\n")
    result = graph.invoke({"messages": [{"role": "user", "content": args.question}]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
