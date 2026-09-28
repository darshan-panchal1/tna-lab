"""Tests for tna_lab.datasets.ingest (Story 1, T010)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tna_lab.datasets import ingest, load_jsonl
from tna_lab.records import DatasetRecord, record_id
from tna_lab.storage import read_json


def _records(n: int) -> list[DatasetRecord]:
    return [DatasetRecord(input=f"q{i}", output=f"a{i}") for i in range(n)]


def test_ingest_creates_one_record_file_per_record_and_a_head_manifest(tmp_path: Path) -> None:
    result = ingest(tmp_path, "smoke", _records(5))
    assert result.added == 5
    assert result.already_present == 0

    head = read_json(tmp_path / "datasets" / "smoke" / "head.json")
    assert len(head["record_ids"]) == 5
    for record in _records(5):
        rid = record_id(record)
        assert rid in head["record_ids"]
        assert (tmp_path / "datasets" / "smoke" / "records" / f"{rid}.json").exists()


def test_reingesting_identical_records_is_a_noop(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(5))
    result = ingest(tmp_path, "smoke", _records(5))
    assert result.added == 0
    assert result.already_present == 5
    head = read_json(tmp_path / "datasets" / "smoke" / "head.json")
    assert len(head["record_ids"]) == 5


def test_ingesting_a_record_with_absent_contexts_succeeds(tmp_path: Path) -> None:
    record = DatasetRecord(input="q", output="a", contexts=None)
    result = ingest(tmp_path, "smoke", [record])
    assert result.added == 1


def test_ingest_reports_mixed_new_and_existing_records(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(2))
    result = ingest(tmp_path, "smoke", _records(5))  # 2 already present, 3 new
    assert result.added == 3
    assert result.already_present == 2
    head = read_json(tmp_path / "datasets" / "smoke" / "head.json")
    assert len(head["record_ids"]) == 5


def test_load_jsonl_reads_one_record_per_line(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(
        '{"input": "q", "output": "a", "contexts": ["c1", "c2"], "metadata": {"k": "v"}}\n'
        "\n"
        '{"output": "only an output"}\n'
    )
    assert load_jsonl(path) == [
        DatasetRecord(input="q", output="a", contexts=("c1", "c2"), metadata={"k": "v"}),
        DatasetRecord(output="only an output"),
    ]


def test_load_jsonl_rejects_an_unknown_field_naming_it_and_its_line(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"input": "q"}\n{"input": "q", "answer": "a"}\n')
    with pytest.raises(ValueError, match=r"records\.jsonl:2.*'answer'"):
        load_jsonl(path)


def test_load_jsonl_rejects_a_line_that_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('["q", "a"]\n')
    with pytest.raises(ValueError, match=r"records\.jsonl:1"):
        load_jsonl(path)
