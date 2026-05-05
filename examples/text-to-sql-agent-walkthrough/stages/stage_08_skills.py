"""Stage 08 — Add skills (progressive disclosure).

Same as stage 07 plus one parameter:

    skills=[str(SKILLS_DIR)]

A *skill* is a `SKILL.md` file inside a directory. Each one has YAML
frontmatter with `name` and `description`. The agent sees only the
descriptions in its system prompt; it loads the full `SKILL.md` body
*on demand* by calling a `read_skill` tool when a description matches
the user's task.

This is **progressive disclosure**:
    - AGENTS.md  -> always loaded   (identity, safety, general rules)
    - SKILL.md   -> loaded on demand (specialised workflows)

We ship two skills:
    skills/query-writing/SKILL.md       (how to write SQL well)
    skills/schema-exploration/SKILL.md  (how to discover structure)
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
        memory=["/AGENTS.md"],
        skills=["/skills"],  # progressive disclosure
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
