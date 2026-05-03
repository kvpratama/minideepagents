"""Step C.3b — The Backend protocol seam.

Step 03 hard-coded `state["files"]: dict[str, str]` inside every file tool.
That works, but it bakes the storage location into the tool body. Real
deepagents factors this out: tools call methods on a `Backend` object, and
the backend decides where to read/write (state, persistent store, sandbox,
etc.).

This file does the same refactor in miniature. We define a `Backend`
Protocol with four methods (`ls`, `read`, `write`, `edit`) and one concrete
implementation, `StateBackend`, that reads and writes `state["files"]`.

The agent loop, the system prompt, and the tool *signatures* all stay
identical to step 03. Only the tool *bodies* change: every file op goes
through `_backend(runtime).method(...)`.

Why this matters: once tools depend on a Protocol instead of a concrete
dict, swapping in a `StoreBackend` (LangGraph cross-thread store) or a
`SandboxBackend` (Daytona / local subprocess) is a one-line change. We
exercise that swap in `step_02_tiny_harness/`.

Run:  uv run python step_01_walkthrough/03b_backends.py
"""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, TypedDict

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import AnyMessage, HumanMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from utils.config import get_settings

load_dotenv()
settings = get_settings()


class Todo(TypedDict):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    todos: list[Todo]
    files: dict[str, str]


# --- Backend protocol --------------------------------------------------------
#
# Every file tool routes through a Backend. A backend has two jobs:
#   1) answer reads (`ls`, `read`)
#   2) describe writes as a state update (`write`, `edit` return a dict that
#      the tool merges into the LangGraph Command).
#
# Returning a dict (instead of mutating in place) keeps the tools pure: the
# graph reducer is still the only thing that *commits* state.


class WriteResult(TypedDict):
    """A state-update fragment plus a human-readable summary."""

    update: dict[str, dict[str, str]]  # always {"files": <new files dict>}
    summary: str  # short string used as the ToolMessage content


class Backend(Protocol):
    """The seam between file tools and storage.

    Implementations decide where files actually live. Step 03b ships one
    impl (`StateBackend`); step 02 will add `StoreBackend` and a fake
    sandbox.
    """

    def ls(self) -> list[str]: ...

    def read(self, path: str) -> str | None: ...

    def write(self, path: str, content: str) -> WriteResult: ...

    def edit(self, path: str, old: str, new: str) -> WriteResult | str: ...


# --- StateBackend ------------------------------------------------------------


class StateBackend:
    """Backend that reads/writes `state["files"]: dict[str, str]`.

    The backend never *applies* updates itself — it returns a `WriteResult`
    describing the new files dict, and the tool merges that into a
    LangGraph `Command(update=...)`. This keeps mutation in one place.
    """

    def __init__(self, files: dict[str, str]) -> None:
        # Snapshot the dict so write()/edit() return a fresh value each time.
        self._files = dict(files)

    def ls(self) -> list[str]:
        return sorted(self._files.keys())

    def read(self, path: str) -> str | None:
        return self._files.get(path)

    def write(self, path: str, content: str) -> WriteResult:
        new_files = {**self._files, path: content}
        return {
            "update": {"files": new_files},
            "summary": f"Wrote {len(content)} bytes to {path}.",
        }

    def edit(self, path: str, old: str, new: str) -> WriteResult | str:
        if path not in self._files:
            return f"Error: {path} not found"
        if old not in self._files[path]:
            return f"Error: substring not found in {path}"
        new_files = {**self._files, path: self._files[path].replace(old, new, 1)}
        return {
            "update": {"files": new_files},
            "summary": f"Edited {path}.",
        }


def _backend(runtime: ToolRuntime) -> Backend:
    """Build the backend for the current invocation.

    Real deepagents puts this behind a factory passed to the middleware. We
    inline it here so the seam stays visible: every tool resolves the
    backend the same way at call time.
    """
    return StateBackend(runtime.state.get("files") or {})


# --- Tools (now generic over `Backend`) --------------------------------------


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
                    f"Recorded {len(todos)} todos.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool
def ls(runtime: ToolRuntime) -> str:
    """List all files in the virtual filesystem."""
    paths = _backend(runtime).ls()
    return "\n".join(paths) if paths else "(no files)"


@tool
def read_file(
    path: str,
    runtime: ToolRuntime,
) -> str:
    """Read the contents of a file from the virtual filesystem."""
    content = _backend(runtime).read(path)
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
    result = _backend(runtime).write(path, content)
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
    result = _backend(runtime).edit(path, old, new)
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


SYSTEM = (
    "You are a deep agent with access to a virtual filesystem (now served "
    "through a `Backend`). Use `write_file`, `read_file`, `edit_file`, and "
    "`ls` to manage notes and intermediate work. Use `write_todos` to plan."
)


def build_agent():
    tools = [write_todos, ls, read_file, write_file, edit_file]
    model = init_chat_model(
        model=settings.model,
        model_provider=settings.model_provider,
        base_url=settings.base_url,
        temperature=0.7,
        api_key=settings.api_key.get_secret_value(),
    ).bind_tools(tools)

    def call_model(state: State) -> dict:
        msgs = [{"role": "system", "content": SYSTEM}] + list(state["messages"])
        return {"messages": [model.invoke(msgs)]}

    def route(state: State) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(State)  # ty:ignore[invalid-argument-type]
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "model")
    return graph.compile()


def main() -> None:
    agent = build_agent()
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    "Write a short haiku about autumn to `notes/haiku.txt`, "
                    "then read it back and confirm what you wrote."
                )
            ],
            "todos": [],
            "files": {},
        }
    )
    print("\n--- Final files ---")
    for path, content in result["files"].items():
        print(f"\n# {path}\n{content}")


if __name__ == "__main__":
    main()
