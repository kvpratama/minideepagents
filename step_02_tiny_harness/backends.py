"""Backend implementations for the tiny harness.

The harness's file tools (`ls`, `read_file`, `write_file`, `edit_file`)
don't talk to `state["files"]` directly. They go through a `Backend` —
the same seam introduced in `step_01_walkthrough/03b_backends.py`. That lets
us swap *where* files live without touching the agent loop.

Three backends ship here:

* `StateBackend` — the default. Files live in `state["files"]` (ephemeral,
  per-thread). Identical semantics to the original mini.py.
* `StoreBackend` — files live in a LangGraph `BaseStore`. Survives across
  threads / processes (depending on which Store impl is plugged in).
* `FakeSandboxBackend` — files live inside an in-memory dict that mimics
  a remote sandbox API. Pedagogical stand-in for Daytona/Docker; shows
  the same Protocol scales to "filesystem behind a network call."
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypedDict

from langgraph.store.base import BaseStore


class WriteResult(TypedDict):
    """A state-update fragment plus a human-readable summary.

    `update` is whatever should be merged into the LangGraph
    `Command(update=...)` that the tool returns. For state-backed
    backends that's `{"files": <new dict>}`; for backends that store
    data outside state (Store, Sandbox), it's `{}` because the tool
    has nothing to commit to LangGraph state.
    """

    update: dict[str, object]
    summary: str


class Backend(Protocol):
    """The seam between file tools and storage."""

    def ls(self) -> list[str]: ...
    def read(self, path: str) -> str | None: ...
    def write(self, path: str, content: str) -> WriteResult: ...
    def edit(self, path: str, old: str, new: str) -> WriteResult | str: ...


# --- StateBackend: files in `state["files"]` --------------------------------


class StateBackend:
    """Default backend — reads and writes `state["files"]: dict[str, str]`."""

    def __init__(self, files: dict[str, str]) -> None:
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
        new_files = {
            **self._files,
            path: self._files[path].replace(old, new, 1),
        }
        return {
            "update": {"files": new_files},
            "summary": f"Edited {path}.",
        }


# --- StoreBackend: files in a LangGraph Store -------------------------------
#
# A Store is LangGraph's cross-thread persistence layer. Items are
# namespaced tuples; values are JSON-serializable dicts. We use the
# namespace `("deep_agent", <thread_id>, "files")` and store one item per
# file path with payload `{"content": <str>}`.
#
# Unlike `StateBackend`, we do *not* return state updates from
# `write`/`edit`: the data already lives in the store. The tool's
# `Command(update=...)` therefore gets an empty fragment.


class StoreBackend:
    """Backend that persists files in a LangGraph BaseStore.

    The store can be any `BaseStore` impl — `InMemoryStore` for tests,
    a Postgres-backed store for production, etc. We don't care: the
    Protocol only sees `get`/`put`/`search`/`delete`.
    """

    NAMESPACE_ROOT = ("deep_agent",)

    def __init__(self, store: BaseStore, thread_id: str) -> None:
        self._store = store
        self._namespace = (*self.NAMESPACE_ROOT, thread_id, "files")

    def ls(self) -> list[str]:
        items = self._store.search(self._namespace)
        return sorted(item.key for item in items)

    def read(self, path: str) -> str | None:
        item = self._store.get(self._namespace, path)
        if item is None:
            return None
        return item.value.get("content")

    def write(self, path: str, content: str) -> WriteResult:
        self._store.put(self._namespace, path, {"content": content})
        return {
            "update": {},
            "summary": f"Wrote {len(content)} bytes to {path} (store).",
        }

    def edit(self, path: str, old: str, new: str) -> WriteResult | str:
        current = self.read(path)
        if current is None:
            return f"Error: {path} not found"
        if old not in current:
            return f"Error: substring not found in {path}"
        self._store.put(
            self._namespace, path, {"content": current.replace(old, new, 1)}
        )
        return {"update": {}, "summary": f"Edited {path} (store)."}


# --- FakeSandboxBackend: files behind a "remote" API ------------------------
#
# Real sandbox backends in deepagents wrap Daytona, Docker, or Modal: each
# call is a network round-trip to a container. We mimic that shape with a
# single object that holds an in-memory dict but only exposes operations
# through methods named like a remote API client. Two takeaways:
#
#   1. The `Backend` Protocol absorbs the latency model — `read` may be
#      slow, but the *contract* is unchanged.
#   2. State updates always come back empty, because the sandbox is the
#      source of truth — the harness state never sees the file contents.


class _FakeSandboxClient:
    """Stand-in for a remote sandbox HTTP client."""

    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    # The ASCII-art "API" — methods are named to look network-shaped so
    # readers don't mistake the in-memory dict for the abstraction.
    def list_files(self) -> list[str]:
        return sorted(self._files.keys())

    def get_file(self, path: str) -> str | None:
        return self._files.get(path)

    def put_file(self, path: str, content: str) -> None:
        self._files[path] = content


class FakeSandboxBackend:
    """Backend that talks to a `_FakeSandboxClient`.

    A real implementation would call `client.exec("cat /workspace/...")`
    or similar. The Protocol shape is the same.
    """

    def __init__(self, client: _FakeSandboxClient | None = None) -> None:
        self._client = client or _FakeSandboxClient()

    @property
    def client(self) -> _FakeSandboxClient:
        """Exposed so tests / examples can inspect the sandbox state."""
        return self._client

    def ls(self) -> list[str]:
        return self._client.list_files()

    def read(self, path: str) -> str | None:
        return self._client.get_file(path)

    def write(self, path: str, content: str) -> WriteResult:
        self._client.put_file(path, content)
        return {
            "update": {},
            "summary": f"Wrote {len(content)} bytes to {path} (sandbox).",
        }

    def edit(self, path: str, old: str, new: str) -> WriteResult | str:
        current = self._client.get_file(path)
        if current is None:
            return f"Error: {path} not found"
        if old not in current:
            return f"Error: substring not found in {path}"
        self._client.put_file(path, current.replace(old, new, 1))
        return {"update": {}, "summary": f"Edited {path} (sandbox)."}


# --- BackendFactory ---------------------------------------------------------
#
# Tools are stateless — they get rebuilt against a fresh backend on every
# invocation. So we don't pass a Backend, we pass a *factory*: something
# that takes the current `ToolRuntime` and returns a Backend. This mirrors
# `BackendFactory` in real deepagents (backends/protocol.py).


from langchain.tools import ToolRuntime

BackendFactory = Callable[[ToolRuntime], Backend]


def default_state_backend_factory(runtime: ToolRuntime) -> Backend:
    """Default factory: builds a `StateBackend` from `state["files"]`."""
    return StateBackend(runtime.state.get("files") or {})
