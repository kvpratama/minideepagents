"""Pluggable backend protocol for the virtual filesystem.

Real deepagents has many concrete backends (state, store, sandbox, ...);
mini-clone ships only `StateBackend`. The ABC exists so the abstraction
boundary is visible — the middleware never touches a dict directly.
"""

from __future__ import annotations

import abc


class FilesystemBackend(abc.ABC):
    """Read/write a virtual filesystem represented as `dict[str, str]`.

    Each method takes the current files mapping and returns a 2-tuple of
    `(new_files_or_None, message)`. `new_files=None` means the operation
    failed and the caller should surface the message as an error
    `ToolMessage`. Otherwise the caller emits a `Command` updating the
    `files` channel with the returned dict.
    """

    @abc.abstractmethod
    def ls(self, files: dict[str, str]) -> str:
        """Return a human-readable listing of all paths."""

    @abc.abstractmethod
    def read(self, files: dict[str, str], path: str) -> tuple[str | None, str]:
        """Return `(content, "")` on success, `(None, error_msg)` on failure."""

    @abc.abstractmethod
    def write(
        self, files: dict[str, str], path: str, content: str,
    ) -> tuple[dict[str, str] | None, str]:
        """Create or overwrite `path`."""

    @abc.abstractmethod
    def edit(
        self, files: dict[str, str], path: str, old: str, new: str,
    ) -> tuple[dict[str, str] | None, str]:
        """Replace the first occurrence of `old` with `new` in `path`."""
