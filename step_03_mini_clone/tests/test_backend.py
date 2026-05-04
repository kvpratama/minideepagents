"""Unit tests for the StateBackend."""

from __future__ import annotations

from backends.state import StateBackend


class TestStateBackend:
    def test_ls_empty(self) -> None:
        backend = StateBackend()
        assert backend.ls({}) == "(no files)"

    def test_ls_lists_paths_sorted(self) -> None:
        backend = StateBackend()
        assert backend.ls({"b.txt": "x", "a.txt": "y"}) == "a.txt\nb.txt"

    def test_read_missing(self) -> None:
        backend = StateBackend()
        content, err = backend.read({}, "missing")
        assert content is None
        assert "not found" in err

    def test_read_found(self) -> None:
        backend = StateBackend()
        content, err = backend.read({"a.txt": "hi"}, "a.txt")
        assert content == "hi"
        assert err == ""

    def test_write_creates_new_dict(self) -> None:
        backend = StateBackend()
        original = {"a.txt": "old"}
        new, msg = backend.write(original, "b.txt", "new")
        assert new == {"a.txt": "old", "b.txt": "new"}
        assert original == {"a.txt": "old"}  # immutability
        assert "3 bytes" in msg

    def test_edit_missing_path(self) -> None:
        backend = StateBackend()
        new, msg = backend.edit({}, "x", "a", "b")
        assert new is None
        assert "not found" in msg

    def test_edit_substring_missing(self) -> None:
        backend = StateBackend()
        new, msg = backend.edit({"a.txt": "hi"}, "a.txt", "z", "y")
        assert new is None
        assert "substring not found" in msg

    def test_edit_replaces_first(self) -> None:
        backend = StateBackend()
        new, msg = backend.edit(
            {"a.txt": "foo bar foo"}, "a.txt", "foo", "BAZ",
        )
        assert new == {"a.txt": "BAZ bar foo"}
        assert "Edited" in msg
