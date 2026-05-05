"""Stage 07 — Add `AGENTS.md` (always-loaded memory).

Same Deep Agent as stage 06, plus one parameter:

    memory=[str(AGENTS_MD)]

`AGENTS.md` is read on every invocation and prepended to the system
prompt. Unlike the system_prompt argument we've been using, AGENTS.md is
a *file in the repo*: it's versioned with the code, reviewable in PRs,
and editable by anyone (even non-engineers).

We also drop the inline SYSTEM_PROMPT — its content has moved into
AGENTS.md verbatim.
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
        backend=FilesystemBackend(root_dir=STAGE_DIR, virtual_mode=True),
        memory=["/AGENTS.md"],  # always-loaded identity + safety rules
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
