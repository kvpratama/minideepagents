"""Stage 09 — Persistent filesystem backend (final form).

Identical to stage 08 plus:

    backend=FilesystemBackend(root_dir=str(STAGE_DIR))

Without this argument, Deep Agents uses an in-memory backend: any files
the agent writes (via `write_file`, `edit_file`) live only for the
current invocation. With `FilesystemBackend`, those writes hit the real
disk under `root_dir`. That makes them:

    - inspectable from your editor mid-run,
    - persistent across invocations on the same thread,
    - exportable as artifacts (CSVs, intermediate analyses).

This is the configuration the upstream `text-to-sql-agent/agent.py`
uses. Stage 09 == upstream, modulo cosmetics.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase

from config import get_model

STAGE_DIR = Path(__file__).resolve().parent
DB_PATH = STAGE_DIR.parent / "chinook.db"


def build_graph():
    db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}", sample_rows_in_table_info=3)
    llm = get_model()
    tools = SQLDatabaseToolkit(db=db, llm=llm).get_tools()
    return create_deep_agent(
        model=llm,
        tools=tools,
        memory=["/AGENTS.md"],
        skills=["/skills"],
        backend=FilesystemBackend(root_dir=str(STAGE_DIR), virtual_mode=True),
    )


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
