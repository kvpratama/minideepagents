"""Lazy model loader for walkthrough stages.

Most walkthrough stages do not need to actually invoke an LLM — the
architectural failure modes they demonstrate (permission denials, log
corruption, index drift, missing routing) happen at the *wiring* level,
not at the model level. So each stage builds a `create_deep_agent(...)`
object to make the wiring real, but the operational demos exercise the
underlying backend / permission / runner code directly.

If you do want to invoke the agent end-to-end, set:

    WIKI_WALKTHROUGH_MODEL=anthropic:claude-haiku-4-5

and the matching provider key. `load_model()` will resolve a LangChain
chat model from `init_chat_model` and return it; otherwise it returns
``None`` and the demo runs in "wiring-only" mode.
"""

from __future__ import annotations

import os
from typing import Any


def load_model() -> Any | None:
    """Return a chat model if `WIKI_WALKTHROUGH_MODEL` is set, else None."""
    spec = os.getenv("WIKI_WALKTHROUGH_MODEL")
    if not spec:
        return None
    from langchain.chat_models import init_chat_model  # noqa: PLC0415

    return init_chat_model(spec)


def model_or_skip(reason: str) -> Any | None:
    """Return a model or print why the LLM invocation is being skipped."""
    model = load_model()
    if model is None:
        print(f"[walkthrough] skipping LLM invocation — {reason}")  # noqa: T201
        print("[walkthrough] set WIKI_WALKTHROUGH_MODEL=... to run the agent")  # noqa: T201
    return model
