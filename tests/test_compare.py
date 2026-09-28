"""Tests for tna_lab.compare (Story 4, T023).

RunRecords are built directly as plain data: compare() needs no evaluate_fn and no
trustnoagent — everything it reads is already on the two records.
"""

from __future__ import annotations

from typing import Any

import pytest

from tna_lab.compare import compare
from tna_lab.runs import RunRecord

SCORE = "tna.fake.score"
LABEL = "tna.fake.label"


def _ok(*, score: float | None = None, label: str | None = None, fp: str = "fp-a") -> dict[str, Any]:
    return {"status": "ok", "score": score, "label": label, "judge_fingerprint": fp, "error": None}


def _failed(status: str, fp: str = "fp-a") -> dict[str, Any]:
    return {"status": status, "score": None, "label": None, "judge_fingerprint": fp, "error": status}


def _run(
    run_id: str,
    results: dict[str, dict[str, dict[str, Any]]],
    snapshot_id: str = "snap-1",
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        snapshot_id=snapshot_id,
        snapshot_ref="smoke@v1",
        evaluator_ids=tuple(results),
        judge_model="test-judge",
        generator_model="test-generator",
        created_at="2026-09-29T00:00:00+00:00",
        results=results,
    )


def _scores(run_id: str, scores: list[float], fp: str = "fp-a") -> RunRecord:
    return _run(run_id, {SCORE: {f"r{i}": _ok(score=s, fp=fp) for i, s in enumerate(scores)}})


def _labels(run_id: str, labels: list[str]) -> RunRecord:
    return _run(run_id, {LABEL: {f"r{i}": _ok(label=lbl) for i, lbl in enumerate(labels)}})


def test_score_deltas_classify_each_record_and_summarize() -> None:
    result = compare(_scores("a", [0.5, 0.8, 0.5]), _scores("b", [0.7, 0.8, 0.3]), SCORE)

    assert (result.run_a, result.run_b, result.evaluator_id) == ("a", "b", SCORE)
    r0, r1, r2 = result.records
    assert [d.record_id for d in result.records] == ["r0", "r1", "r2"]
    assert [d.classification for d in result.records] == ["improved", "unchanged", "regressed"]
    assert r0.delta == pytest.approx(0.2)
    assert r1.delta == 0.0
    assert r2.delta == pytest.approx(-0.2)
    assert (r0.score_a, r0.score_b) == (0.5, 0.7)
    assert r0.label_a is None and r0.transition is None

    summary = result.summary
    assert (summary.improved, summary.regressed, summary.unchanged) == (1, 1, 1)
    assert summary.mean_score_delta == pytest.approx(0.0)
    assert summary.pass_rate_delta is None


def test_mean_score_delta_is_the_mean_of_per_record_deltas() -> None:
    result = compare(_scores("a", [0.5, 0.5]), _scores("b", [0.6, 0.9]), SCORE)
    assert result.summary.mean_score_delta == pytest.approx(0.25)


def test_ordered_pass_fail_labels_report_transitions_and_a_pass_rate_delta() -> None:
    result = compare(
        _labels("a", ["pass", "fail", "pass"]), _labels("b", ["pass", "pass", "pass"]), LABEL
    )

    r0, r1, r2 = result.records
    assert r1.classification == "improved"
    assert r1.transition == "fail → pass"
    assert (r1.label_a, r1.label_b) == ("fail", "pass")
    assert r1.delta is None
    assert r0.classification == r2.classification == "unchanged"
    assert r0.transition is None

    summary = result.summary
    assert (summary.improved, summary.regressed, summary.unchanged) == (1, 0, 2)
    assert summary.pass_rate_delta == pytest.approx(1 / 3)
    assert summary.mean_score_delta is None


def test_pass_to_fail_is_a_regression() -> None:
    result = compare(_labels("a", ["pass"]), _labels("b", ["fail"]), LABEL)
    assert result.records[0].classification == "regressed"
    assert result.summary.pass_rate_delta == pytest.approx(-1.0)


def test_unordered_labels_keep_the_transition_but_withhold_a_judgment() -> None:
    result = compare(_labels("a", ["polite"]), _labels("b", ["curt"]), LABEL)
    (delta,) = result.records
    assert delta.transition == "polite → curt"
    assert delta.classification == "unchanged"
    assert result.summary.pass_rate_delta is None


def test_a_status_change_is_reported_regardless_of_score_or_label() -> None:
    run_a = _run("a", {SCORE: {"r0": _ok(score=0.5), "r1": _failed("invalid_output")}})
    run_b = _run("b", {SCORE: {"r0": _failed("invalid_output"), "r1": _ok(score=0.5)}})
    result = compare(run_a, run_b, SCORE)

    r0, r1 = result.records
    assert r0.status_changed and r1.status_changed
    assert (r0.status_a, r0.status_b) == ("ok", "invalid_output")
    assert (r0.score_a, r0.score_b, r0.delta) == (0.5, None, None)
    assert r0.classification == "regressed"
    assert r1.classification == "improved"
    assert result.summary.mean_score_delta is None  # no record has a score on both sides


def test_a_change_between_two_failure_statuses_is_not_a_judgment() -> None:
    run_a = _run("a", {SCORE: {"r0": _failed("error")}})
    run_b = _run("b", {SCORE: {"r0": _failed("skipped")}})
    (delta,) = compare(run_a, run_b, SCORE).records
    assert delta.status_changed
    assert delta.classification == "unchanged"


def test_comparing_a_run_to_itself_is_all_unchanged_with_zero_delta() -> None:
    run_a = _scores("a", [0.5, 0.8, 0.1])
    result = compare(run_a, run_a, SCORE)
    assert all(d.classification == "unchanged" and d.delta == 0.0 for d in result.records)
    assert not any(d.status_changed for d in result.records)
    summary = result.summary
    assert (summary.improved, summary.regressed, summary.unchanged) == (0, 0, 3)
    assert summary.mean_score_delta == 0.0


def test_both_runs_fingerprints_are_surfaced() -> None:
    result = compare(_scores("a", [0.5], fp="fp-a"), _scores("b", [0.5], fp="fp-b"), SCORE)
    (delta,) = result.records
    assert (delta.fingerprint_a, delta.fingerprint_b) == ("fp-a", "fp-b")


def test_runs_against_different_snapshots_raise_naming_the_mismatch() -> None:
    run_a = _run("a", {SCORE: {"r0": _ok(score=0.5)}}, snapshot_id="snap-1")
    run_b = _run("b", {SCORE: {"r0": _ok(score=0.5)}}, snapshot_id="snap-2")
    with pytest.raises(ValueError, match="snapshot") as excinfo:
        compare(run_a, run_b, SCORE)
    assert "snap-1" in str(excinfo.value) and "snap-2" in str(excinfo.value)


@pytest.mark.parametrize("missing_in", ["a", "b"])
def test_a_run_without_the_evaluator_raises_naming_it(missing_in: str) -> None:
    with_it = _run("a" if missing_in == "b" else "b", {SCORE: {"r0": _ok(score=0.5)}})
    without = _run(missing_in, {LABEL: {"r0": _ok(label="pass")}})
    run_a, run_b = (without, with_it) if missing_in == "a" else (with_it, without)
    with pytest.raises(ValueError, match=SCORE) as excinfo:
        compare(run_a, run_b, SCORE)
    assert repr(missing_in) in str(excinfo.value)
