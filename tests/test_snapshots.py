"""Tests for tna_lab.snapshots: freeze() and resolve() (Story 2, T014)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tna_lab.datasets import ingest
from tna_lab.records import DatasetRecord
from tna_lab.snapshots import freeze, resolve


def _records(n: int) -> list[DatasetRecord]:
    return [DatasetRecord(input=f"q{i}", output=f"a{i}") for i in range(n)]


def test_freeze_captures_current_head(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(5))
    ref = freeze(tmp_path, "smoke", "v1")
    assert ref.dataset == "smoke"
    assert ref.tag == "v1"
    assert len(ref.record_ids) == 5
    assert ref.snapshot_id
    assert ref.frozen_at


def test_resolved_snapshot_is_unchanged_by_later_ingestion(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(5))
    freeze(tmp_path, "smoke", "v1")
    ingest(tmp_path, "smoke", _records(10))  # 5 more records

    resolved = resolve(tmp_path, "smoke@v1")
    assert len(resolved.record_ids) == 5
    assert set(resolved.record_ids) == {r for r in resolve(tmp_path, "smoke@v1").record_ids}


def test_two_freezes_of_identical_content_have_different_snapshot_ids(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(3))
    v1 = freeze(tmp_path, "smoke", "v1")
    v2 = freeze(tmp_path, "smoke", "v2")  # same HEAD content, different freeze event
    assert v1.record_ids == v2.record_ids
    assert v1.snapshot_id != v2.snapshot_id
    # Both remain independently resolvable.
    assert resolve(tmp_path, "smoke@v1").snapshot_id == v1.snapshot_id
    assert resolve(tmp_path, "smoke@v2").snapshot_id == v2.snapshot_id


def test_freezing_an_existing_tag_raises_and_does_not_overwrite(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(3))
    original = freeze(tmp_path, "smoke", "v1")
    ingest(tmp_path, "smoke", _records(5))  # HEAD now has more records
    with pytest.raises(ValueError, match="v1"):
        freeze(tmp_path, "smoke", "v1")
    # The original snapshot must be untouched.
    assert resolve(tmp_path, "smoke@v1").snapshot_id == original.snapshot_id
    assert resolve(tmp_path, "smoke@v1").record_ids == original.record_ids


def test_resolving_a_missing_tag_raises_and_never_falls_back_to_head(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(3))
    with pytest.raises(ValueError, match="does-not-exist"):
        resolve(tmp_path, "smoke@does-not-exist")
