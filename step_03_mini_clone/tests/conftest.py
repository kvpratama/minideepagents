"""Test scaffolding for step B.

Adds `step_03_mini_clone/` to `sys.path` so tests can use bare imports like
`from middleware.todos import TodosMiddleware`. Also exposes a
`make_fake_model` helper for deterministic, hermetic tests.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable

ROOT = Path(__file__).resolve().parents[1]  # step_03_mini_clone/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class SimpleFakeChatModel(BaseChatModel):
    """Minimal fake chat model that supports bind_tools."""

    model_config = {"arbitrary_types_allowed": True}

    responses: list[AIMessage] = []
    _index: int = 0

    def __init__(self, responses: list[AIMessage], **kwargs: Any) -> None:
        super().__init__(responses=responses, **kwargs)
        self._index = 0

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> Any:
        from langchain_core.outputs import ChatGeneration, ChatResult

        if self._index >= len(self.responses):
            raise IndexError("No more responses")
        response = self.responses[self._index]
        self._index += 1
        return ChatResult(generations=[ChatGeneration(message=response)])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable:
        """Return self - tools are ignored in fake model."""
        return self

    @property
    def _llm_type(self) -> str:
        return "simple_fake"


@pytest.fixture
def make_fake_model():
    """Build a `SimpleFakeChatModel` from a list of `AIMessage`s."""

    def _factory(messages: Iterable[AIMessage]) -> SimpleFakeChatModel:
        return SimpleFakeChatModel(responses=list(messages))

    return _factory
