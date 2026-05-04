"""FilesystemMiddleware — `ls`, `read_file`, `write_file`, `edit_file` tools.

Tools delegate to the configured `FilesystemBackend`. Files live in the
`files` state channel as `dict[str, str]`.
"""

from __future__ import annotations

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain.messages import ToolMessage
from langchain.tools import BaseTool, ToolRuntime, tool
from langgraph.types import Command

from step_03_mini_clone.backends.protocol import FilesystemBackend


class FilesystemState(AgentState):
    files: dict[str, str]


def _build_tools(backend: FilesystemBackend) -> list[BaseTool]:
    @tool
    def ls(runtime: ToolRuntime) -> str:
        """List all files in the virtual filesystem."""
        files = runtime.state.get("files") or {}
        return backend.ls(files)

    @tool
    def read_file(
        path: str,
        runtime: ToolRuntime,
    ) -> str:
        """Read the contents of a file."""
        files = runtime.state.get("files") or {}
        content, err = backend.read(files, path)
        return content if content is not None else err

    @tool
    def write_file(
        path: str,
        content: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Create or overwrite a file."""
        files = runtime.state.get("files") or {}
        new, msg = backend.write(files, path, content)
        if new is None:
            return Command(update={"messages": [ToolMessage(
                msg, tool_call_id=runtime.tool_call_id, status="error")]})
        return Command(update={
            "files": new,
            "messages": [ToolMessage(msg, tool_call_id=runtime.tool_call_id)],
        })

    @tool
    def edit_file(
        path: str,
        old: str,
        new: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Replace the first occurrence of `old` with `new` in `path`."""
        files = runtime.state.get("files") or {}
        new_files, msg = backend.edit(files, path, old, new)
        if new_files is None:
            return Command(update={"messages": [ToolMessage(
                msg, tool_call_id=runtime.tool_call_id, status="error")]})
        return Command(update={
            "files": new_files,
            "messages": [ToolMessage(msg, tool_call_id=runtime.tool_call_id)],
        })

    return [ls, read_file, write_file, edit_file]


class FilesystemMiddleware(AgentMiddleware):
    """Adds the four filesystem tools backed by a `FilesystemBackend`."""

    state_schema = FilesystemState

    def __init__(self, backend: FilesystemBackend) -> None:
        self.backend = backend
        self.tools = _build_tools(backend)
