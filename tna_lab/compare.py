"""compare(): a per-record diff of two runs for one evaluator (Story 4, spec
FR-019-FR-025, research R7).

Imports no trustnoagent — both RunRecords already hold every result as plain data.
Deltas branch on what each result carries: a score gets a numeric delta, a label gets a
transition, and a status change is reported on its own, whatever the score or label says.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from statistics import fmean
from typing import Any, Literal

from tna_lab.runs import RunRecord

Classification = Literal["improved", "regressed", "unchanged"]

# The only label set with an order this feature is willing to assume (data-model.md's
# note on label ordering). Any other rubric's labels get a transition but no judgment.
_ORDERED_LABELS = {"fail": 0, "pass": 1}


@dataclass(frozen=True)
class RecordDelta:
    record_id: str
    status_a: str
    status_b: str
    score_a: float | None
    score_b: float | None
    label_a: str | None
    label_b: str | None
    delta: float | None
    transition: str | None
    status_changed: bool
    classification: Classification
    # Article V / FR-027: a comparison surfaces both runs' fingerprints, not only scores.
    fingerprint_a: str | None
    fingerprint_b: str | None


@dataclass(frozen=True)
class ComparisonSummary:
    improved: int
    regressed: int
    unchanged: int
    mean_score_delta: float | None
    pass_rate_delta: float | None


@dataclass(frozen=True)
class Comparison:
    run_a: str
    run_b: str
    evaluator_id: str
    records: tuple[RecordDelta, ...]
    summary: ComparisonSummary


def _results_for(run: RunRecord, evaluator_id: str) -> Mapping[str, Mapping[str, Any]]:
    if evaluator_id not in run.results:
        raise ValueError(f"run {run.run_id!r} has no results for evaluator {evaluator_id!r}")
    return run.results[evaluator_id]


def _classify(
    status_a: str, status_b: str, delta: float | None, label_a: str | None, label_b: str | None
) -> Classification:
    if status_a != status_b:  # only a move into or out of `ok` is a judgment
        if status_a == "ok":
            return "regressed"
        return "improved" if status_b == "ok" else "unchanged"
    if delta is not None:
        return "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"
    if label_a in _ORDERED_LABELS and label_b in _ORDERED_LABELS and label_a != label_b:
        return "improved" if _ORDERED_LABELS[label_b] > _ORDERED_LABELS[label_a] else "regressed"
    return "unchanged"


def _record_delta(record_id: str, a: Mapping[str, Any], b: Mapping[str, Any]) -> RecordDelta:
    score_a, score_b = a.get("score"), b.get("score")
    label_a, label_b = a.get("label"), b.get("label")
    delta = score_b - score_a if score_a is not None and score_b is not None else None
    both_labels = label_a is not None and label_b is not None
    return RecordDelta(
        record_id=record_id,
        status_a=a["status"],
        status_b=b["status"],
        score_a=score_a,
        score_b=score_b,
        label_a=label_a,
        label_b=label_b,
        delta=delta,
        transition=f"{label_a} → {label_b}" if both_labels and label_a != label_b else None,
        status_changed=a["status"] != b["status"],
        classification=_classify(a["status"], b["status"], delta, label_a, label_b),
        fingerprint_a=a.get("judge_fingerprint"),
        fingerprint_b=b.get("judge_fingerprint"),
    )


def _pass_rate_delta(records: tuple[RecordDelta, ...]) -> float | None:
    """Set only when every label either run produced is from the ordered pass/fail set."""
    labels = {d.label_a for d in records} | {d.label_b for d in records}
    labels.discard(None)
    if not records or not labels or not labels.issubset(_ORDERED_LABELS):
        return None
    rate_a = sum(d.label_a == "pass" for d in records) / len(records)
    rate_b = sum(d.label_b == "pass" for d in records) / len(records)
    return rate_b - rate_a


def compare(run_a: RunRecord, run_b: RunRecord, evaluator_id: str) -> Comparison:
    """Diff two runs' results for `evaluator_id`, one RecordDelta per record in both.

    Raises ValueError if the runs scored different snapshot ids, or if either lacks
    results for `evaluator_id` — the message names which (FR-021). A status change moves
    a record into `improved` (into `ok`) or `regressed` (out of `ok`); any other change
    between two failure statuses is reported via `status_changed` but not judged.
    """
    if run_a.snapshot_id != run_b.snapshot_id:
        raise ValueError(
            "cannot compare runs against different snapshots: "
            f"run {run_a.run_id!r} scored {run_a.snapshot_ref} ({run_a.snapshot_id}), "
            f"run {run_b.run_id!r} scored {run_b.snapshot_ref} ({run_b.snapshot_id})"
        )
    results_a = _results_for(run_a, evaluator_id)
    results_b = _results_for(run_b, evaluator_id)

    records = tuple(
        _record_delta(rid, results_a[rid], results_b[rid]) for rid in results_a if rid in results_b
    )
    deltas = [d.delta for d in records if d.delta is not None]
    summary = ComparisonSummary(
        improved=sum(d.classification == "improved" for d in records),
        regressed=sum(d.classification == "regressed" for d in records),
        unchanged=sum(d.classification == "unchanged" for d in records),
        mean_score_delta=fmean(deltas) if deltas else None,
        pass_rate_delta=_pass_rate_delta(records),
    )
    return Comparison(
        run_a=run_a.run_id,
        run_b=run_b.run_id,
        evaluator_id=evaluator_id,
        records=records,
        summary=summary,
    )
