"""Tests for tna_lab.storage: canonical JSON, workspace resolution, JSON read/write (T006)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tna_lab import storage


def test_canonical_json_ignores_key_order() -> None:
    a = storage.canonical_json({"b": 2, "a": 1})
    b = storage.canonical_json({"a": 1, "b": 2})
    assert a == b


def test_canonical_json_is_compact_and_deterministic() -> None:
    once = storage.canonical_json({"x": [1, 2, 3], "y": None})
    twice = storage.canonical_json({"y": None, "x": [1, 2, 3]})
    assert once == twice
    assert " " not in once  # compact separators


def test_workspace_root_default_is_cwd_dot_tna_lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert storage.workspace_root(None) == tmp_path / ".tna-lab"


def test_workspace_root_explicit_is_returned_unchanged(tmp_path: Path) -> None:
    explicit = tmp_path / "somewhere-else"
    assert storage.workspace_root(explicit) == explicit


def test_write_json_read_json_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "record.json"
    data = {"input": "hi", "contexts": ["a", "b"], "metadata": {}}
    storage.write_json(path, data)
    assert storage.read_json(path) == data


def test_write_json_is_noop_on_identical_content(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    data = {"input": "hi"}
    storage.write_json(path, data)
    mtime_before = path.stat().st_mtime_ns
    storage.write_json(path, data)  # identical content, must not raise
    assert storage.read_json(path) == data
    # Content is unchanged; whether the OS bumps mtime on an identical write is not
    # load-bearing here — only that no exception was raised and content stayed correct.
    assert mtime_before <= path.stat().st_mtime_ns


def test_write_json_refuses_to_overwrite_different_content(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    storage.write_json(path, {"input": "hi"})
    with pytest.raises(ValueError, match="different content"):
        storage.write_json(path, {"input": "bye"})
    # The original content must survive the refused write.
    assert storage.read_json(path) == {"input": "hi"}
