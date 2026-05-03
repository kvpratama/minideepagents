"""Step A — Tiny harness.

Single-file synthesis of every capability built incrementally in
`step_01_walkthrough/`. Exposes one entrypoint, `create_deep_agent`, on top of
bare LangGraph.

Capabilities: model loop, todos, virtual filesystem, subagents (`task`),
permissions (HITL via `interrupt`), skills (`load_skill`).

Run the demo:  uv run python step_02_tiny_harness/example.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain.tools import BaseTool, ToolRuntime, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from utils.config import get_settings

load_dotenv()

# Import backends - handle both package and script mode
if __package__:
    from .backends import BackendFactory, default_state_backend_factory
else:  # script mode (`python step_02_tiny_harness/mini.py`)
    sys.path.insert(0, str(Path(__file__).parent))
    from backends import BackendFactory, default_state_backend_factory


# --- State (Task 2) ----------------------------------------------------------


class Todo(TypedDict):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    todos: list[Todo]
    files: dict[str, str]


# --- Builtin tools (Task 2) --------------------------------------------------


@tool
def write_todos(
    todos: list[Todo],
    runtime: ToolRuntime,
) -> Command:
    """Replace the agent's todo list."""
    return Command(
        update={
            "todos": todos,
            "messages": [
                ToolMessage(
                    f"Recorded {len(todos)} todos.", tool_call_id=runtime.tool_call_id
                )
            ],
        }
    )


def _make_fs_tools(factory: BackendFactory) -> list[BaseTool]:
    """Build the four file tools bound to a specific backend factory.

    Tools are *closures* over `factory` so they resolve the backend at
    invocation time, not at agent-build time. This matches how real
    deepagents passes `BackendFactory` to its FilesystemMiddleware.
    """

    @tool
    def ls(runtime: ToolRuntime) -> str:
        """List all files in the virtual filesystem."""
        paths = factory(runtime).ls()
        return "\n".join(paths) if paths else "(no files)"

    @tool
    def read_file(
        path: str,
        runtime: ToolRuntime,
    ) -> str:
        """Read the contents of a file from the virtual filesystem."""
        content = factory(runtime).read(path)
        if content is None:
            return f"Error: {path} not found"
        return content

    @tool
    def write_file(
        path: str,
        content: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Create or overwrite a file at `path` with `content`."""
        result = factory(runtime).write(path, content)
        return Command(
            update={
                **result["update"],
                "messages": [
                    ToolMessage(result["summary"], tool_call_id=runtime.tool_call_id)
                ],
            }
        )

    @tool
    def edit_file(
        path: str,
        old: str,
        new: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Replace the first occurrence of `old` with `new` inside `path`."""
        result = factory(runtime).edit(path, old, new)
        if isinstance(result, str):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            result,
                            tool_call_id=runtime.tool_call_id,
                            status="error",
                        )
                    ]
                }
            )
        return Command(
            update={
                **result["update"],
                "messages": [
                    ToolMessage(result["summary"], tool_call_id=runtime.tool_call_id)
                ],
            }
        )

    return [ls, read_file, write_file, edit_file]


# --- Subagents (Task 3) ------------------------------------------------------

_DEFAULT_SUBAGENT_PROMPT = (
    "You are a focused subagent. Complete the task in the user message "
    "using the tools available, then reply with a concise summary of what "
    "you did. You do not have access to `task`."
)


def _build_subagent_graph(*, model_name: str, prompt: str, tools: list[BaseTool]):
    settings = get_settings()
    bound = init_chat_model(
        model=model_name,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value(),
    ).bind_tools(tools)

    def call_model(state: State) -> dict:
        msgs = [{"role": "system", "content": prompt}] + list(state["messages"])
        return {"messages": [bound.invoke(msgs)]}

    def route(state: State) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    g = StateGraph(State)  # ty:ignore[invalid-argument-type]
    g.add_node("model", call_model)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "model")
    g.add_conditional_edges("model", route, {"tools": "tools", END: END})
    g.add_edge("tools", "model")
    return g.compile()


def _make_task_tool(
    *,
    model_name: str,
    subagent_specs: list[dict] | None,
    parent_user_tools: list[BaseTool],
    fs_tools: list[BaseTool],
    skills_block: str = "",
):
    specs = list(subagent_specs or [])
    default_tools = [*fs_tools, *parent_user_tools]
    spec_names = {s["name"] for s in specs}
    registry: dict[str, Any] = {}
    catalog_lines: list[str] = []

    # Seed the `general-purpose` fallback only if the user hasn't supplied
    # their own spec for it; otherwise the user's spec wins and the catalog
    # shows their description.
    if "general-purpose" not in spec_names:
        registry["general-purpose"] = _build_subagent_graph(
            model_name=model_name,
            prompt=_DEFAULT_SUBAGENT_PROMPT + skills_block,
            tools=default_tools,
        )
        catalog_lines.append("- general-purpose: default subagent with fs tools")

    for spec in specs:
        registry[spec["name"]] = _build_subagent_graph(
            model_name=model_name,
            prompt=spec.get("prompt", _DEFAULT_SUBAGENT_PROMPT) + skills_block,
            tools=spec.get("tools") or default_tools,
        )
        catalog_lines.append(f"- {spec['name']}: {spec['description']}")
    catalog = "\n".join(catalog_lines)

    @tool
    def task(description: str, subagent_type: str, runtime: ToolRuntime) -> Command:
        """Delegate a focused sub-task to a named subagent."""
        graph = registry.get(subagent_type)
        if graph is None:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Error: unknown subagent_type '{subagent_type}'. "
                            f"Available: {sorted(registry)}",
                            tool_call_id=runtime.tool_call_id,
                            status="error",
                        )
                    ]
                }
            )
        result = graph.invoke(
            {
                "messages": [HumanMessage(description)],
                "todos": [],
                "files": runtime.state.get("files") or {},
            }
        )
        reply = result["messages"][-1].content
        return Command(
            update={
                "files": result.get("files") or runtime.state.get("files") or {},
                "messages": [
                    ToolMessage(str(reply), tool_call_id=runtime.tool_call_id)
                ],
            }
        )

    task.description = (
        "Delegate a focused sub-task to one of the available subagents. "
        "Subagents share the filesystem but start with empty message history.\n"
        f"Available subagents:\n{catalog}"
    )
    return task


# --- Permissions (Task 4) ----------------------------------------------------


def _make_permissions_node(dangerous: set[str]):
    """Return a graph node that interrupts before each dangerous tool call."""

    def permissions_node(state: State) -> dict:
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return {}
        declined: list[ToolMessage] = []
        surviving: list[dict] = []
        for call in last.tool_calls:
            if call["name"] in dangerous:
                decision = interrupt(
                    {
                        "tool": call["name"],
                        "args": call["args"],
                        "prompt": f"Approve {call['name']}({call['args']})?",
                    }
                )
                if decision != "approved":
                    declined.append(
                        ToolMessage(
                            "User declined this tool call.",
                            tool_call_id=call["id"],
                            name=call["name"],
                        )
                    )
                    continue
            surviving.append(call)  # ty:ignore[invalid-argument-type]
        if not declined:
            return {}
        rewritten = AIMessage(content=last.content, tool_calls=surviving, id=last.id)
        return {"messages": [rewritten, *declined]}

    return permissions_node


# --- Skills (Task 5) ---------------------------------------------------------


def _discover_skills_sync(skills_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for md in skills_dir.glob("*/SKILL.md"):
        name = md.parent.name
        text = md.read_text()
        desc = name
        for line in text.splitlines():
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip()
                break
        out[name] = desc
    return out


async def _discover_skills(skills_dir: Path) -> dict[str, str]:
    return await asyncio.to_thread(_discover_skills_sync, skills_dir)


async def _make_skill_machinery(skills_dir: str | Path | None):
    """Return (load_skill_tool_or_None, skills_system_block)."""
    if skills_dir is None:
        return None, ""
    root = Path(skills_dir).resolve()
    skills = await _discover_skills(root)
    block = "\n".join(f"- {n}: {d}" for n, d in skills.items()) or "(none)"

    @tool
    def load_skill(name: str) -> str:
        """Load a skill by name. Returns the full SKILL.md contents."""
        path = root / name / "SKILL.md"
        if not path.exists():
            return f"Error: skill '{name}' not found"
        return path.read_text()

    system_block = (
        "\n\nThe following skills are available — call `load_skill(name)` to "
        f"pull any whose guidance is relevant:\n{block}"
    )
    return load_skill, system_block


# --- Entrypoint (Task 6) -----------------------------------------------------


async def create_deep_agent(
    model: str,
    tools: list[BaseTool],
    instructions: str,
    *,
    subagents: list[dict] | None = None,
    skills_dir: str | Path | None = None,
    require_approval: list[str] | None = None,
    backend_factory: BackendFactory = default_state_backend_factory,
    store: object | None = None,
):
    """Build a compiled deep-agent graph.

    Args:
        model: Model identifier (e.g. ``"openai/o1-mini"``).
        tools: User tools available to the parent and to subagents.
        instructions: System prompt prefix; skills block is appended.
        subagents: Optional subagent specs; ``general-purpose`` is always added.
        skills_dir: Directory containing ``<name>/SKILL.md``.
        require_approval: Tool names that trigger HITL ``interrupt()``.
        backend_factory: Builds a `Backend` for each tool invocation.
            Defaults to `default_state_backend_factory` (state-backed).
        store: Optional LangGraph `BaseStore`. Passed to `compile()` so
            tools using `StoreBackend` can read/write across threads.

    Returns:
        Compiled graph with an in-memory checkpointer. Callers must pass
        ``config={"configurable": {"thread_id": ...}}``.
    """
    settings = get_settings()
    user_tools = list(tools)

    fs_tools = _make_fs_tools(backend_factory)

    load_skill_tool, skills_block = await _make_skill_machinery(skills_dir)

    if load_skill_tool is not None:
        user_tools.append(load_skill_tool)

    task_tool = _make_task_tool(
        model_name=model,
        subagent_specs=subagents,
        parent_user_tools=user_tools,
        fs_tools=fs_tools,
        skills_block=skills_block,
    )

    all_tools: list[BaseTool] = [
        write_todos,
        *fs_tools,
        *user_tools,
        task_tool,
    ]

    system = instructions + skills_block

    bound = init_chat_model(
        model=model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value(),
    ).bind_tools(all_tools)

    def call_model(state: State) -> dict:
        msgs = [{"role": "system", "content": system}] + list(state["messages"])
        return {"messages": [bound.invoke(msgs)]}

    dangerous = set(require_approval or [])
    permissions = _make_permissions_node(dangerous) if dangerous else None

    def route_after_model(state: State) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return END
        return "permissions" if permissions is not None else "tools"

    def route_after_permissions(state: State) -> str:
        ai = next(
            (m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None
        )
        return "tools" if (ai and ai.tool_calls) else "model"

    g = StateGraph(State)  # ty:ignore[invalid-argument-type]
    g.add_node("model", call_model)
    g.add_node("tools", ToolNode(all_tools))
    g.add_edge(START, "model")
    if permissions is not None:
        g.add_node("permissions", permissions)
        g.add_conditional_edges(
            "model",
            route_after_model,
            {"permissions": "permissions", "tools": "tools", END: END},
        )
        g.add_conditional_edges(
            "permissions", route_after_permissions, {"tools": "tools", "model": "model"}
        )
    else:
        g.add_conditional_edges(
            "model", route_after_model, {"tools": "tools", END: END}
        )
    g.add_edge("tools", "model")
    if store is not None:
        return g.compile(checkpointer=InMemorySaver(), store=store)  # ty:ignore[invalid-argument-type]
    return g.compile(checkpointer=InMemorySaver())


# --- Studio entrypoint -------------------------------------------------------

_STUDIO_SKILLS_DIR = Path(__file__).parent / "skills"


async def _studio_graph():
    return await create_deep_agent(
        model=get_settings().model,
        tools=[],
        instructions=(
            "You are a deep agent. Plan with `write_todos`, "
            "persist with `write_file`, delegate with `task`, "
            "load skills via `load_skill`."
        ),
        skills_dir=_STUDIO_SKILLS_DIR,
        require_approval=["write_file", "edit_file"],
    )


async def _studio_graph_with_store():
    """Studio variant that persists files in an InMemoryStore.

    Multiple thread runs see the same files (until the dev server
    restarts), demonstrating cross-thread persistence.
    """
    from langgraph.store.memory import InMemoryStore

    if __package__:
        from .backends import StoreBackend
    else:
        from backends import StoreBackend

    store = InMemoryStore()

    def store_factory(runtime):
        thread_id = runtime.config.get("configurable", {}).get(
            "thread_id", "studio-default"
        )
        return StoreBackend(store, thread_id)

    return await create_deep_agent(
        model=get_settings().model,
        tools=[],
        instructions=(
            "You are a deep agent with persistent storage. Plan with "
            "`write_todos`, persist with `write_file`, delegate with "
            "`task`, load skills via `load_skill`."
        ),
        skills_dir=_STUDIO_SKILLS_DIR,
        require_approval=["write_file", "edit_file"],
        backend_factory=store_factory,
        store=store,
    )
