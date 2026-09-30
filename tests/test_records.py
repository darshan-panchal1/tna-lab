"""Tests for tna_lab.records: DatasetRecord identity (T005, research R1)."""

from __future__ import annotations

from tna_lab.records import DatasetRecord, case_id, record_id


def _record(**overrides: object) -> DatasetRecord:
    base: dict[str, object] = {
        "input": "What is the refund window?",
        "output": "30 days.",
        "expected": "30 days.",
        "contexts": ("Refunds: 30 days from delivery.",),
        "metadata": {},
    }
    base.update(overrides)
    return DatasetRecord(**base)  # type: ignore[arg-type]


def test_identical_field_values_produce_the_same_id_regardless_of_contexts_construction() -> None:
    a = _record(contexts=("x", "y"))
    b = _record(contexts=tuple(c for c in ["x", "y"]))
    assert record_id(a) == record_id(b)


def test_changing_any_field_changes_the_id() -> None:
    base = _record()
    base_id = record_id(base)
    assert record_id(_record(input="different question")) != base_id
    assert record_id(_record(output="different answer")) != base_id
    assert record_id(_record(expected="different expected")) != base_id
    assert record_id(_record(contexts=("different context",))) != base_id
    assert record_id(_record(metadata={"k": "v"})) != base_id


def test_none_contexts_differs_from_empty_tuple_contexts() -> None:
    absent = record_id(_record(contexts=None))
    empty = record_id(_record(contexts=()))
    assert absent != empty


def test_record_id_is_a_full_sha256_hex_digest() -> None:
    rid = record_id(_record())
    assert len(rid) == 64
    assert rid == rid.lower()
    int(rid, 16)  # raises ValueError if not valid hex


# T002 (spec 002): case identity - input + expected only, computed, never stored.


def test_case_id_ignores_output_contexts_and_metadata() -> None:
    a = _record(output="30 days.", contexts=("c1",), metadata={"agent": "v1"})
    b = _record(output="Thirty days, from delivery.", contexts=None, metadata={"agent": "v2"})
    assert record_id(a) != record_id(b)
    assert case_id(a) == case_id(b)


def test_case_id_changes_with_expected_and_distinguishes_none_from_empty() -> None:
    assert case_id(_record(expected="30 days.")) != case_id(_record(expected="One month."))
    assert case_id(_record(expected=None)) != case_id(_record(expected=""))


def test_case_id_is_none_without_input() -> None:
    assert case_id(_record(input=None)) is None
    assert case_id(_record(input=None, output="other", expected="other")) is None


def test_case_id_does_not_normalize_text() -> None:
    base = case_id(_record(input="What is X?"))
    assert case_id(_record(input="What is X? ")) != base
    assert case_id(_record(input="what is x?")) != base


def test_case_id_is_a_full_sha256_distinct_from_the_record_id() -> None:
    record = _record()
    cid = case_id(record)
    assert cid is not None
    assert len(cid) == 64 and cid == cid.lower() and all(c in "0123456789abcdef" for c in cid)
    assert cid != record_id(record)
