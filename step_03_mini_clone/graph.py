"""Step B — `create_deep_agent` built on `create_agent` + middleware.

Same signature as `step_02_tiny_harness/mini.py:create_deep_agent`. The body
is just middleware composition — every loop, tool dispatch, and prompt
mutation is delegated to LangChain's `create_agent` runtime.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from step_03_mini_clone.backends.state import StateBackend
from step_03_mini_clone.middleware.filesystem import FilesystemMiddleware
from step_03_mini_clone.middleware.permissions import PermissionsMiddleware
from step_03_mini_clone.middleware.skills import SkillsMiddleware
from step_03_mini_clone.middleware.subagents import SubagentsMiddleware
from step_03_mini_clone.middleware.todos import TodosMiddleware
from utils.config import get_settings

load_dotenv()


def create_deep_agent(
    model: str,
    tools: list[BaseTool],
    instructions: str,
    *,
    subagents: list[dict] | None = None,
    skills_dir: str | Path | None = None,
    require_approval: list[str] | None = None,
):
    """Build a deep agent on `create_agent` + a curated middleware stack.

    Args:
        model: Model identifier (passed to `init_chat_model`).
        tools: User-supplied tools available to the parent and children.
        instructions: System prompt prefix.
        subagents: Optional subagent specs.
        skills_dir: Directory containing `<name>/SKILL.md` files.
        require_approval: Tool names that should trigger HITL `interrupt()`.

    Returns:
        A compiled `create_agent` graph with an in-memory checkpointer.
    """
    settings = get_settings()
    bound = init_chat_model(
        model=model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value(),
    )

    backend = StateBackend()
    middleware: list = [
        TodosMiddleware(),
        FilesystemMiddleware(backend=backend),
        SubagentsMiddleware(
            child_model=bound,
            backend=backend,
            subagents=subagents or [],
            parent_user_tools=list(tools),
        ),
    ]
    if skills_dir is not None:
        middleware.append(SkillsMiddleware(skills_dir=skills_dir))
    if require_approval:
        middleware.append(PermissionsMiddleware(dangerous_tools=require_approval))

    return create_agent(
        model=bound,
        tools=list(tools),
        middleware=middleware,
        system_prompt=instructions,
        checkpointer=InMemorySaver(),
    )


# --- Studio entrypoint -------------------------------------------------------

_STUDIO_SKILLS_DIR = Path(__file__).parent / "skills"


def _studio_graph():
    return create_deep_agent(
        model=get_settings().model,
        tools=[],
        instructions=("You are a deep agent. Plan with `write_todos`, "
                      "persist with `write_file`, delegate with `task`, "
                      "load skills via `load_skill`."),
        skills_dir=_STUDIO_SKILLS_DIR,
        require_approval=["write_file", "edit_file"],
    )
