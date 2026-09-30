"""Tests for tna_lab.compare.compare_cases (spec 002).

Run records are built directly over records ingested for real, so every case resolves
through datasets.load_record() exactly as in production. No trustnoagent import: results
are plain data, as they are in a stored RunRecord.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tna_lab.compare import compare, compare_cases
from tna_lab.datasets import ingest
from tna_lab.records import DatasetRecord, case_id, record_id
from tna_lab.runs import RunRecord
from tna_lab.snapshots import freeze

EVAL = "tna.fake.score"


def _rec(
    question: str,
    output: str = "an answer",
    expected: str | None = "the reference",
    contexts: tuple[str, ...] | None = ("a context",),
    metadata: dict[str, str] | None = None,
) -> DatasetRecord:
    return DatasetRecord(
        input=question, output=output, expected=expected, contexts=contexts,
        metadata=metadata or {},
    )


def _cid(question: str) -> str:
    """The case id `_rec(question)` has; every `_rec` has an input, so it is never None."""
    cid = case_id(_rec(question))
    assert cid is not None
    return cid


def _ok(
    score: float | None = None, label: str | None = None, fp: str = "fp", tokens: tuple[int, int] = (10, 2)
) -> dict[str, Any]:
    return {
        "status": "ok", "score": score, "label": label, "judge_fingerprint": fp,
        "tokens_in": tokens[0], "tokens_out": tokens[1], "error": None,
    }


def _failed(status: str) -> dict[str, Any]:
    return {
        "status": status, "score": None, "label": None, "judge_fingerprint": None,
        "tokens_in": None, "tokens_out": None, "error": status,
    }


def _scored(
    workspace: Path,
    dataset: str,
    scored: list[tuple[DatasetRecord, dict[str, Any]]],
    run_id: str | None = None,
    judge: str = "test-judge",
    generator: str = "test-generator",
    evaluator: str = EVAL,
) -> RunRecord:
    """Ingest and freeze `dataset`, then return a run record scoring every record as given."""
    ingest(workspace, dataset, [r for r, _ in scored])
    snapshot = freeze(workspace, dataset, "base")
    return RunRecord(
        run_id=run_id or f"run-{dataset}",
        snapshot_id=snapshot.snapshot_id,
        snapshot_ref=f"{dataset}@base",
        evaluator_ids=(evaluator,),
        judge_model=judge,
        generator_model=generator,
        created_at="2026-09-30T00:00:00+00:00",
        results={evaluator: {record_id(r): result for r, result in scored}},
    )


# User Story 1 — compare two output sets for the same test cases.


def test_cases_pair_across_two_datasets(tmp_path: Path) -> None:
    v1 = [(_rec(f"q{i}", output=f"v1 answer {i}"), _ok(score=0.5)) for i in range(3)]
    v2 = [(_rec(f"q{i}", output=f"v2 answer {i}"), _ok(score=0.5)) for i in range(3)]
    run_a, run_b = _scored(tmp_path, "agent-v1", v1), _scored(tmp_path, "agent-v2", v2)
    assert run_a.snapshot_id != run_b.snapshot_id

    result = compare_cases(tmp_path, run_a, run_b, EVAL)

    assert (result.run_a, result.run_b, result.evaluator_id) == ("run-agent-v1", "run-agent-v2", EVAL)
    assert len(result.cases) == 3
    for (rec_a, _), (rec_b, _) in zip(v1, v2, strict=True):
        (delta,) = [d for d in result.cases if d.case_id == case_id(rec_a)]
        assert (delta.record_id_a, delta.record_id_b) == (record_id(rec_a), record_id(rec_b))


def test_score_deltas_classify_each_case_and_summarize(tmp_path: Path) -> None:
    scores_a, scores_b = [0.5, 0.8, 0.5], [0.7, 0.8, 0.3]
    run_a = _scored(tmp_path, "v1", [(_rec(f"q{i}", output="a"), _ok(score=s)) for i, s in enumerate(scores_a)])
    run_b = _scored(tmp_path, "v2", [(_rec(f"q{i}", output="b"), _ok(score=s)) for i, s in enumerate(scores_b)])

    result = compare_cases(tmp_path, run_a, run_b, EVAL)

    by_question = {d.case_id: d for d in result.cases}
    q0, q1, q2 = (by_question[_cid(f"q{i}")] for i in range(3))
    assert (q0.classification, q1.classification, q2.classification) == ("improved", "unchanged", "regressed")
    assert q0.delta == pytest.approx(0.2)
    assert q1.delta == 0.0
    assert q2.delta == pytest.approx(-0.2)
    s = result.summary
    assert (s.paired, s.improved, s.regressed, s.unchanged) == (3, 1, 1, 1)
    assert s.mean_score_delta == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("result_a", "result_b"),
    [
        (_ok(score=0.5), _ok(score=0.9)),
        (_ok(score=0.9), _ok(score=0.5)),
        (_ok(score=0.5), _ok(score=0.5)),
        (_ok(score=0.5), _failed("invalid_output")),
        (_failed("invalid_output"), _ok(score=0.5)),
        (_failed("error"), _failed("skipped")),
        (_ok(label="fail"), _ok(label="pass")),
        (_ok(label="pass"), _ok(label="fail")),
        (_ok(label="polite"), _ok(label="curt")),
    ],
)
def test_classification_and_shared_fields_match_compare_exactly(
    tmp_path: Path, result_a: dict[str, Any], result_b: dict[str, Any]
) -> None:
    run_a = _scored(tmp_path, "v1", [(_rec("q", output="a"), result_a)])
    run_b = _scored(tmp_path, "v2", [(_rec("q", output="b"), result_b)])
    (case,) = compare_cases(tmp_path, run_a, run_b, EVAL).cases

    # The same two results through spec 001's compare(), over one shared snapshot.
    same_snapshot_b = replace(run_a, run_id="b", results={EVAL: {case.record_id_a: result_b}})
    (record,) = compare(run_a, same_snapshot_b, EVAL).records

    shared = (
        "status_a", "status_b", "score_a", "score_b", "label_a", "label_b", "delta", "transition",
        "status_changed", "classification", "fingerprint_a", "fingerprint_b",
        "tokens_in_a", "tokens_in_b", "tokens_out_a", "tokens_out_b",
    )
    assert {f: getattr(case, f) for f in shared} == {f: getattr(record, f) for f in shared}


def test_changed_contexts_are_flagged_and_still_counted(tmp_path: Path) -> None:
    run_a = _scored(tmp_path, "v1", [
        (_rec("q0", contexts=("chunk",)), _ok(score=0.4)),
        (_rec("q1", contexts=None), _ok(score=0.4)),
        (_rec("q2"), _ok(score=0.4)),
    ])
    run_b = _scored(tmp_path, "v2", [
        (_rec("q0", contexts=("chunk", "another chunk")), _ok(score=0.8)),
        (_rec("q1", contexts=()), _ok(score=0.8)),  # absent vs. present-but-empty: changed
        (_rec("q2", output="different"), _ok(score=0.8)),
    ])

    result = compare_cases(tmp_path, run_a, run_b, EVAL)

    flags = {d.case_id: d.contexts_changed for d in result.cases}
    assert flags == {case_id(_rec("q0")): True, case_id(_rec("q1")): True, case_id(_rec("q2")): False}
    assert all(d.classification == "improved" for d in result.cases)
    assert result.summary.contexts_changed == 2
    assert result.summary.mean_score_delta == pytest.approx(0.4)  # every pair counted


def test_output_changed_and_an_identical_record_on_both_sides(tmp_path: Path) -> None:
    same = _rec("same", output="unchanged answer")
    run_a = _scored(tmp_path, "v1", [(same, _ok(score=0.6)), (_rec("q", output="old"), _ok(score=0.6))])
    run_b = _scored(tmp_path, "v2", [(same, _ok(score=0.6)), (_rec("q", output="new"), _ok(score=0.6))])

    result = compare_cases(tmp_path, run_a, run_b, EVAL)

    identical = next(d for d in result.cases if d.case_id == case_id(same))
    changed = next(d for d in result.cases if d.case_id == case_id(_rec("q")))
    assert identical.record_id_a == identical.record_id_b == record_id(same)
    assert (identical.output_changed, identical.contexts_changed) == (False, False)
    assert (changed.output_changed, changed.contexts_changed) == (True, False)
    assert result.summary.output_changed == 1


def test_a_metadata_only_difference_pairs_with_no_flag(tmp_path: Path) -> None:
    run_a = _scored(tmp_path, "v1", [(_rec("q", metadata={"agent": "v1"}), _ok(score=0.5))])
    run_b = _scored(tmp_path, "v2", [(_rec("q", metadata={"agent": "v2"}), _ok(score=0.5))])

    (case,) = compare_cases(tmp_path, run_a, run_b, EVAL).cases

    assert case.record_id_a != case.record_id_b
    assert (case.output_changed, case.contexts_changed) == (False, False)


def test_a_status_change_is_reported_alongside_the_classification(tmp_path: Path) -> None:
    run_a = _scored(tmp_path, "v1", [(_rec("q", output="a"), _ok(score=0.5))])
    run_b = _scored(tmp_path, "v2", [(_rec("q", output="b"), _failed("invalid_output"))])

    (case,) = compare_cases(tmp_path, run_a, run_b, EVAL).cases

    assert case.status_changed
    assert (case.status_a, case.status_b) == ("ok", "invalid_output")
    assert case.classification == "regressed"


def test_labels_give_transitions_and_a_pass_rate_delta(tmp_path: Path) -> None:
    run_a = _scored(tmp_path, "v1", [
        (_rec("q0", output="a"), _ok(label="pass")), (_rec("q1", output="a"), _ok(label="fail")),
    ])
    run_b = _scored(tmp_path, "v2", [
        (_rec("q0", output="b"), _ok(label="pass")), (_rec("q1", output="b"), _ok(label="pass")),
    ])

    result = compare_cases(tmp_path, run_a, run_b, EVAL)

    q1 = next(d for d in result.cases if d.case_id == case_id(_rec("q1")))
    assert q1.transition == "fail → pass"
    assert q1.classification == "improved"
    assert result.summary.pass_rate_delta == pytest.approx(0.5)
    assert result.summary.mean_score_delta is None


def test_every_case_carries_both_fingerprints_and_token_counts(tmp_path: Path) -> None:
    run_a = _scored(tmp_path, "v1", [(_rec("q", output="a"), _ok(score=0.5, fp="fp-v1", tokens=(1919, 582)))])
    run_b = _scored(tmp_path, "v2", [(_rec("q", output="b"), _ok(score=0.6, fp="fp-v2", tokens=(1915, 710)))])

    (case,) = compare_cases(tmp_path, run_a, run_b, EVAL).cases

    assert (case.fingerprint_a, case.fingerprint_b) == ("fp-v1", "fp-v2")
    assert (case.tokens_in_a, case.tokens_out_a, case.tokens_in_b, case.tokens_out_b) == (1919, 582, 1915, 710)


def test_comparing_a_run_to_itself_is_all_unchanged(tmp_path: Path) -> None:
    run_a = _scored(tmp_path, "v1", [(_rec(f"q{i}"), _ok(score=0.1 * i)) for i in range(3)])

    result = compare_cases(tmp_path, run_a, run_a, EVAL)

    assert len(result.cases) == 3
    assert all(d.classification == "unchanged" and d.delta == 0.0 for d in result.cases)
    assert not any(d.output_changed or d.contexts_changed or d.status_changed for d in result.cases)
    assert (result.summary.improved, result.summary.regressed, result.summary.unchanged) == (0, 0, 3)
