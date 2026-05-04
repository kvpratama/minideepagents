"""StateBackend — virtual filesystem stored in agent state."""

from __future__ import annotations

from step_03_mini_clone.backends.protocol import FilesystemBackend


class StateBackend(FilesystemBackend):
    """Concrete backend that treats the `files` state channel as the source of truth.

    Every operation is pure: it never mutates the input dict; the caller is
    responsible for emitting a `Command(update={"files": ...})`.
    """

    def ls(self, files: dict[str, str]) -> str:
        if not files:
            return "(no files)"
        return "\n".join(sorted(files.keys()))

    def read(
        self, files: dict[str, str], path: str,
    ) -> tuple[str | None, str]:
        if path not in files:
            return None, f"Error: {path} not found"
        return files[path], ""

    def write(
        self, files: dict[str, str], path: str, content: str,
    ) -> tuple[dict[str, str] | None, str]:
        new = {**files, path: content}
        return new, f"Wrote {len(content)} bytes to {path}."

    def edit(
        self, files: dict[str, str], path: str, old: str, new: str,
    ) -> tuple[dict[str, str] | None, str]:
        if path not in files:
            return None, f"Error: {path} not found"
        if old not in files[path]:
            return None, f"Error: substring not found in {path}"
        updated = {**files, path: files[path].replace(old, new, 1)}
        return updated, f"Edited {path}."
