"""The one place tna-lab's tests reach the real trustnoagent.evaluators.evaluate (T019).

Everything else uses a fake evaluate_fn (research R6). This proves the *default* wiring:
run() with no evaluate_fn hands a real EvalRecord and JudgeConfig to trust-no-agent and
persists what comes back. No live credential is needed — an installed trust-no-agent with
no reachable evidence cache answers with its own `error` result, never an exception
(trust-no-agent FR-004), so the assertions are on that result's shape, not a score.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tna_lab.datasets import ingest
from tna_lab.records import DatasetRecord
from tna_lab.runs import load_run, run
from tna_lab.snapshots import freeze

evaluators = pytest.importorskip("trustnoagent.evaluators")

_STATUSES = {"ok", "error", "skipped", "invalid_output"}


@pytest.fixture
def snapshot(tmp_path: Path) -> str:
    ingest(
        tmp_path,
        "smoke",
        [
            DatasetRecord(
                input="What is the refund window?",
                output="30 days from delivery.",
                expected="30 days.",
                contexts=("Refunds: 30 days from delivery, unopened.",),
            )
        ],
    )
    freeze(tmp_path, "smoke", "v1")
    return "smoke@v1"


@pytest.fixture(autouse=True)
def _models_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Placeholders for JudgeConfig.from_env(); offline mode never builds a client from them.
    monkeypatch.setenv("JUDGE_MODEL", "tna-lab-offline-test-judge")
    monkeypatch.setenv("GENERATOR_MODEL", "tna-lab-offline-test-generator")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)


def test_default_evaluate_fn_returns_a_well_formed_result(tmp_path: Path, snapshot: str) -> None:
    evaluator_id = min(info.id for info in evaluators.list_evaluators())
    result = run(tmp_path, snapshot, [evaluator_id])

    (persisted,) = result.results[evaluator_id].values()
    assert persisted["evaluator_id"] == evaluator_id
    assert persisted["status"] in _STATUSES
    if persisted["status"] == "ok":
        assert persisted["score"] is not None or persisted["label"] is not None
    else:  # no committed evidence reachable from an installed wheel: a named error, no verdict
        assert persisted["score"] is None and persisted["label"] is None
        assert persisted["error"]
    assert load_run(tmp_path, result.run_id) == result


def test_unknown_evaluator_is_persisted_as_trust_no_agents_own_error(
    tmp_path: Path, snapshot: str
) -> None:
    result = run(tmp_path, snapshot, ["tna.does.not.exist"])

    (persisted,) = result.results["tna.does.not.exist"].values()
    assert persisted["status"] == "error"
    assert "tna.does.not.exist" in persisted["error"]
    assert persisted["score"] is None
