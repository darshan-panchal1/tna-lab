"""Tests for tna_lab.runs: run() and load_run() (Story 3, T018).

Every test injects a fake evaluate_fn (research R6). This file never imports
trustnoagent — the real default is exercised only by tests/test_runs_integration.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tna_lab.datasets import ingest
from tna_lab.records import DatasetRecord, record_id
from tna_lab.runs import load_run, run
from tna_lab.snapshots import freeze


@dataclass(frozen=True)
class FakeResult:
    """Shaped like trust-no-agent's EvalResult; run() must persist it field for field."""

    evaluator_id: str
    status: str
    score: float | None = None
    label: str | None = None
    error: str | None = None
    judge_fingerprint: str | None = "fp-test"
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeEvaluate:
    """Records every call; returns `ok`/0.5 unless `statuses` maps a record input to a status."""

    statuses: dict[str, str] = field(default_factory=dict)
    calls: list[tuple[str, Any, Any, Path]] = field(default_factory=list)

    def __call__(self, evaluator_id: str, record: Any, judge: Any, cache_dir: Path) -> Any:
        self.calls.append((evaluator_id, record, judge, cache_dir))
        status = self.statuses.get(record.input, "ok")
        if status == "ok":
            return FakeResult(evaluator_id, "ok", score=0.5)
        return FakeResult(evaluator_id, status, error=f"{status} for {record.input}")


@pytest.fixture(autouse=True)
def _models_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # run() builds its default judge exactly as JudgeConfig.from_env() would (FR-013);
    # these are placeholders, not a model choice — no call ever leaves the fake.
    monkeypatch.setenv("JUDGE_MODEL", "test-judge")
    monkeypatch.setenv("GENERATOR_MODEL", "test-generator")


def _records(n: int) -> list[DatasetRecord]:
    return [DatasetRecord(input=f"q{i}", output=f"a{i}") for i in range(n)]


def _frozen(workspace: Path, n: int) -> str:
    ingest(workspace, "smoke", _records(n))
    freeze(workspace, "smoke", "v1")
    return "smoke@v1"


def test_run_calls_evaluate_once_per_record_and_evaluator(tmp_path: Path) -> None:
    fake = FakeEvaluate()
    result = run(tmp_path, _frozen(tmp_path, 3), ["tna.fake.one"], evaluate_fn=fake)

    assert len(fake.calls) == 3
    assert {call[0] for call in fake.calls} == {"tna.fake.one"}
    assert set(result.results) == {"tna.fake.one"}
    assert set(result.results["tna.fake.one"]) == {record_id(r) for r in _records(3)}


def test_run_passes_each_records_content_to_evaluate(tmp_path: Path) -> None:
    fake = FakeEvaluate()
    run(tmp_path, _frozen(tmp_path, 3), ["tna.fake.one"], evaluate_fn=fake)
    assert sorted((call[1].input, call[1].output) for call in fake.calls) == [
        ("q0", "a0"),
        ("q1", "a1"),
        ("q2", "a2"),
    ]


def test_run_keeps_each_evaluators_results_distinguishable(tmp_path: Path) -> None:
    fake = FakeEvaluate()
    result = run(tmp_path, _frozen(tmp_path, 3), ["tna.fake.one", "tna.fake.two"], evaluate_fn=fake)

    assert len(fake.calls) == 6
    assert result.evaluator_ids == ("tna.fake.one", "tna.fake.two")
    assert set(result.results) == {"tna.fake.one", "tna.fake.two"}
    for evaluator_id, per_record in result.results.items():
        assert len(per_record) == 3
        assert {r["evaluator_id"] for r in per_record.values()} == {evaluator_id}


def test_run_persists_every_non_ok_result_unmodified_and_does_not_raise(tmp_path: Path) -> None:
    fake = FakeEvaluate(statuses={"q0": "error", "q1": "skipped", "q2": "invalid_output"})
    result = run(tmp_path, _frozen(tmp_path, 3), ["tna.fake.one"], evaluate_fn=fake)

    by_input = {r.input: record_id(r) for r in _records(3)}
    per_record = result.results["tna.fake.one"]
    for text, status in [("q0", "error"), ("q1", "skipped"), ("q2", "invalid_output")]:
        assert per_record[by_input[text]] == {
            "evaluator_id": "tna.fake.one",
            "status": status,
            "score": None,
            "label": None,
            "error": f"{status} for {text}",
            "judge_fingerprint": "fp-test",
            "raw": {},
        }


def test_run_record_carries_the_exact_snapshot_identity(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(3))
    v1 = freeze(tmp_path, "smoke", "v1")
    v2 = freeze(tmp_path, "smoke", "v2")  # same records, different freeze event

    result = run(tmp_path, "smoke@v1", ["tna.fake.one"], evaluate_fn=FakeEvaluate())
    assert result.snapshot_id == v1.snapshot_id
    assert result.snapshot_id != v2.snapshot_id
    assert result.snapshot_ref == "smoke@v1"


def test_run_accepts_an_already_resolved_snapshot(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(2))
    ref = freeze(tmp_path, "smoke", "v1")
    result = run(tmp_path, ref, ["tna.fake.one"], evaluate_fn=FakeEvaluate())
    assert result.snapshot_id == ref.snapshot_id
    assert result.snapshot_ref == "smoke@v1"


def test_run_without_a_judge_passes_a_judge_config_from_the_environment(tmp_path: Path) -> None:
    fake = FakeEvaluate()
    result = run(tmp_path, _frozen(tmp_path, 1), ["tna.fake.one"], evaluate_fn=fake)

    judge = fake.calls[0][2]
    assert judge is not None
    assert (judge.judge_model, judge.generator_model) == ("test-judge", "test-generator")
    assert (result.judge_model, result.generator_model) == ("test-judge", "test-generator")


def test_run_creates_the_workspace_cache_and_passes_it_to_every_call(tmp_path: Path) -> None:
    snapshot = _frozen(tmp_path, 3)
    assert not (tmp_path / "cache").exists()

    fake = FakeEvaluate()
    run(tmp_path, snapshot, ["tna.fake.one", "tna.fake.two"], evaluate_fn=fake)

    assert (tmp_path / "cache").is_dir()
    assert len(fake.calls) == 6
    assert {call[3] for call in fake.calls} == {tmp_path / "cache"}


def test_every_run_in_a_workspace_shares_one_cache(tmp_path: Path) -> None:
    snapshot = _frozen(tmp_path, 2)
    first, second = FakeEvaluate(), FakeEvaluate()
    run(tmp_path, snapshot, ["tna.fake.one"], evaluate_fn=first)
    run(tmp_path, snapshot, ["tna.fake.one"], evaluate_fn=second)
    assert {call[3] for call in first.calls + second.calls} == {tmp_path / "cache"}


def test_an_explicit_cache_dir_is_created_and_used_instead(tmp_path: Path) -> None:
    snapshot = _frozen(tmp_path, 2)
    elsewhere = tmp_path / "shared" / "evidence"

    fake = FakeEvaluate()
    run(tmp_path, snapshot, ["tna.fake.one"], cache_dir=elsewhere, evaluate_fn=fake)

    assert elsewhere.is_dir()
    assert {call[3] for call in fake.calls} == {elsewhere}
    assert not (tmp_path / "cache").exists()


def test_run_against_a_missing_snapshot_raises_naming_the_tag(tmp_path: Path) -> None:
    ingest(tmp_path, "smoke", _records(1))
    with pytest.raises(ValueError, match="nope"):
        run(tmp_path, "smoke@nope", ["tna.fake.one"], evaluate_fn=FakeEvaluate())


def test_two_runs_of_the_same_snapshot_are_distinct_records(tmp_path: Path) -> None:
    snapshot = _frozen(tmp_path, 2)
    first = run(tmp_path, snapshot, ["tna.fake.one"], evaluate_fn=FakeEvaluate())
    second = run(tmp_path, snapshot, ["tna.fake.one"], evaluate_fn=FakeEvaluate())
    assert first.run_id != second.run_id
    assert first.snapshot_id == second.snapshot_id


def test_load_run_returns_what_run_returned(tmp_path: Path) -> None:
    fake = FakeEvaluate(statuses={"q1": "invalid_output"})
    result = run(tmp_path, _frozen(tmp_path, 3), ["tna.fake.one", "tna.fake.two"], evaluate_fn=fake)
    assert (tmp_path / "runs" / f"{result.run_id}.json").exists()
    assert load_run(tmp_path, result.run_id) == result


def test_load_run_of_an_unknown_id_raises_naming_it(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="20260101T000000Z-deadbeef"):
        load_run(tmp_path, "20260101T000000Z-deadbeef")
