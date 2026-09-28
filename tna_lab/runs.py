"""run(): score a frozen snapshot through trust-no-agent, persisting every result
unmodified (Story 3, spec FR-011-FR-018, research R3, R5, R6).

The only module in tna_lab that imports trustnoagent. It never computes, retries or
reinterprets a score, and never catches what evaluate() raises — trust-no-agent already
turns every evaluation-time failure into a status (research R5).
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trustnoagent import EvalRecord, EvalResult, JudgeConfig
from trustnoagent.evaluators import evaluate

from tna_lab.datasets import dataset_dir
from tna_lab.snapshots import SnapshotRef, resolve
from tna_lab.storage import canonical_json, read_json, write_json

# Which function scores one record — a test seam only, never a model or provider choice
# (research R6). The shipped default is always trust-no-agent's own evaluate().
EvaluateFn = Callable[[str, EvalRecord, JudgeConfig], EvalResult]


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    snapshot_id: str
    snapshot_ref: str
    evaluator_ids: tuple[str, ...]
    judge_model: str
    generator_model: str
    created_at: str
    # {evaluator_id: {record_id: trust-no-agent's EvalResult as a plain dict, unmodified}}
    results: Mapping[str, Mapping[str, dict[str, Any]]]


def _run_path(workspace: Path, run_id: str) -> Path:
    return workspace / "runs" / f"{run_id}.json"


def _eval_record(workspace: Path, dataset: str, rid: str) -> EvalRecord:
    data = read_json(dataset_dir(workspace, dataset) / "records" / f"{rid}.json")
    contexts = data["contexts"]
    return EvalRecord(
        input=data["input"],
        output=data["output"],
        expected=data["expected"],
        contexts=tuple(contexts) if contexts is not None else None,
        metadata=data["metadata"],
    )


def run(
    workspace: Path,
    snapshot: str | SnapshotRef,
    evaluator_ids: Sequence[str],
    judge: JudgeConfig | None = None,
    evaluate_fn: EvaluateFn = evaluate,
) -> RunRecord:
    """Score every record in `snapshot` (`<dataset>@<tag>`, or an already-resolved
    SnapshotRef) with every evaluator id, once per (record, evaluator) pair (FR-012).

    Raises ValueError if `snapshot` does not resolve (FR-009). Never raises for a
    per-record scoring failure: every result, whatever its status, is persisted (FR-017).
    """
    ref = resolve(workspace, snapshot) if isinstance(snapshot, str) else snapshot
    config = judge if judge is not None else JudgeConfig.from_env()  # FR-013: as-is
    ids = tuple(dict.fromkeys(evaluator_ids))  # a repeated id is still scored only once

    now = datetime.now(UTC)
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"

    records = {rid: _eval_record(workspace, ref.dataset, rid) for rid in ref.record_ids}
    results = {
        evaluator_id: {
            rid: asdict(evaluate_fn(evaluator_id, record, config))
            for rid, record in records.items()
        }
        for evaluator_id in ids
    }

    payload = {
        "run_id": run_id,
        "snapshot_id": ref.snapshot_id,
        "snapshot_ref": f"{ref.dataset}@{ref.tag}",
        "evaluator_ids": list(ids),
        "judge_model": config.judge_model,
        "generator_model": config.generator_model,
        "created_at": now.isoformat(),
        # Normalized through JSON so the returned record equals what load_run() reads back.
        "results": json.loads(canonical_json(results)),
    }
    write_json(_run_path(workspace, run_id), payload)
    return _from_json(payload)


def load_run(workspace: Path, run_id: str) -> RunRecord:
    """Read a persisted run record back. Raises ValueError if `run_id` does not exist."""
    path = _run_path(workspace, run_id)
    if not path.exists():
        raise ValueError(f"run {run_id!r} does not exist")
    return _from_json(read_json(path))


def _from_json(data: dict[str, Any]) -> RunRecord:
    return RunRecord(
        run_id=data["run_id"],
        snapshot_id=data["snapshot_id"],
        snapshot_ref=data["snapshot_ref"],
        evaluator_ids=tuple(data["evaluator_ids"]),
        judge_model=data["judge_model"],
        generator_model=data["generator_model"],
        created_at=data["created_at"],
        results=data["results"],
    )
