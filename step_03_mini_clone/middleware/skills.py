"""SkillsMiddleware — progressive disclosure for SKILL.md files.

The model is told *which* skills exist (via the system prompt) but not
their contents. When it decides a skill is relevant, it calls
`load_skill(name)` to read the markdown into context.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain.messages import SystemMessage
from langchain.tools import tool


def _discover(skills_dir: Path) -> dict[str, str]:
    """Return `{name: description}` for every `<name>/SKILL.md`."""
    out: dict[str, str] = {}
    for md in skills_dir.glob("*/SKILL.md"):
        name = md.parent.name
        desc = name
        for line in md.read_text().splitlines():
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip()
                break
        out[name] = desc
    return out


class SkillsMiddleware(AgentMiddleware):
    """Adds the `load_skill` tool and lists available skills in the system prompt."""

    def __init__(self, skills_dir: str | Path) -> None:
        self._dir = Path(skills_dir).resolve()
        self._catalog: dict[str, str] | None = None

        @tool
        async def load_skill(name: str) -> str:
            """Load a skill by name. Returns the full SKILL.md contents."""
            path = self._dir / name / "SKILL.md"
            
            def _read() -> str:
                if not path.exists():
                    return f"Error: skill '{name}' not found"
                return path.read_text()
                
            return await asyncio.to_thread(_read)

        self.tools = [load_skill]

    def _catalog_block(self) -> str:
        if not self._catalog:
            return ""
        listing = "\n".join(f"- {n}: {d}" for n, d in self._catalog.items())
        return (
            "\n\nThe following skills are available — call "
            "`load_skill(name)` to pull any whose guidance is relevant:\n"
            + listing
        )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        if self._catalog is None:
            self._catalog = _discover(self._dir)
        block = self._catalog_block()
        if not block:
            return handler(request)
        existing = request.system_message
        if existing is None:
            new_system = SystemMessage(content=block.strip())
        else:
            new_system = SystemMessage(content=str(existing.content) + block)
        return handler(request.override(system_message=new_system))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if self._catalog is None:
            self._catalog = await asyncio.to_thread(_discover, self._dir)
        block = self._catalog_block()
        if not block:
            return await handler(request)
        existing = request.system_message
        if existing is None:
            new_system = SystemMessage(content=block.strip())
        else:
            new_system = SystemMessage(content=str(existing.content) + block)
        return await handler(request.override(system_message=new_system))
