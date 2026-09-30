"""Two comparisons of two runs, sharing one classification implementation.

- compare(): a per-record diff of two runs of one snapshot (spec 001 Story 4, FR-019-FR-025,
  research R7). The records are held fixed; the judging may differ.
- compare_cases(): a per-case diff of two runs of any two snapshots, pairing records by
  the same `input` + `expected` (spec 002). The judging is held fixed; the outputs may differ.

Imports no trustnoagent — both RunRecords already hold every result as plain data.
Deltas branch on what each result carries: a score gets a numeric delta, a label gets a
transition, and a status change is reported on its own, whatever the score or label says.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Literal

from tna_lab.datasets import load_record
from tna_lab.records import DatasetRecord, case_id
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
    # Article V: token counts are shown, not dropped (added in v0.2.0, spec 002 T000).
    tokens_in_a: int | None
    tokens_in_b: int | None
    tokens_out_a: int | None
    tokens_out_b: int | None


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


@dataclass(frozen=True)
class CaseDelta:
    """One paired case (spec 002 FR-015). The sibling of RecordDelta, with two record ids.

    `case_id` is computed at comparison time from `input` + `expected` and never stored."""

    case_id: str
    record_id_a: str
    record_id_b: str
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
    fingerprint_a: str | None
    fingerprint_b: str | None
    tokens_in_a: int | None
    tokens_in_b: int | None
    tokens_out_a: int | None
    tokens_out_b: int | None
    contexts_changed: bool
    output_changed: bool


UnmatchedReason = Literal["no_counterpart", "no_input"]


@dataclass(frozen=True)
class UnmatchedCase:
    """One scored record that could not be paired, with its own result (spec 002 FR-013).

    `case_id` is computed at comparison time, never stored; None exactly for `no_input`."""

    record_id: str
    case_id: str | None
    reason: UnmatchedReason
    status: str
    score: float | None
    label: str | None
    fingerprint: str | None
    tokens_in: int | None
    tokens_out: int | None


@dataclass(frozen=True)
class AmbiguousCase:
    """A case carried by more than one record within a run: listed, never paired
    (spec 002 FR-014). `case_id` is computed at comparison time, never stored."""

    case_id: str
    record_ids_a: tuple[str, ...]
    record_ids_b: tuple[str, ...]


@dataclass(frozen=True)
class CaseComparisonSummary:
    paired: int
    improved: int
    regressed: int
    unchanged: int
    contexts_changed: int
    output_changed: int
    unmatched_a: int
    unmatched_b: int
    ambiguous: int
    mean_score_delta: float | None
    pass_rate_delta: float | None


@dataclass(frozen=True)
class CaseComparison:
    run_a: str
    run_b: str
    evaluator_id: str
    cases: tuple[CaseDelta, ...]
    unmatched_a: tuple[UnmatchedCase, ...]
    unmatched_b: tuple[UnmatchedCase, ...]
    ambiguous: tuple[AmbiguousCase, ...]
    summary: CaseComparisonSummary


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


def _paired_fields(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    """Every field two paired results share, for RecordDelta and CaseDelta alike: one
    implementation, so the two comparisons cannot drift in what they classify or show."""
    score_a, score_b = a.get("score"), b.get("score")
    label_a, label_b = a.get("label"), b.get("label")
    delta = score_b - score_a if score_a is not None and score_b is not None else None
    both_labels = label_a is not None and label_b is not None
    return {
        "status_a": a["status"],
        "status_b": b["status"],
        "score_a": score_a,
        "score_b": score_b,
        "label_a": label_a,
        "label_b": label_b,
        "delta": delta,
        "transition": f"{label_a} → {label_b}" if both_labels and label_a != label_b else None,
        "status_changed": a["status"] != b["status"],
        "classification": _classify(a["status"], b["status"], delta, label_a, label_b),
        "fingerprint_a": a.get("judge_fingerprint"),
        "fingerprint_b": b.get("judge_fingerprint"),
        "tokens_in_a": a.get("tokens_in"),
        "tokens_in_b": b.get("tokens_in"),
        "tokens_out_a": a.get("tokens_out"),
        "tokens_out_b": b.get("tokens_out"),
    }


def _record_delta(record_id: str, a: Mapping[str, Any], b: Mapping[str, Any]) -> RecordDelta:
    return RecordDelta(record_id=record_id, **_paired_fields(a, b))


def _pass_rate_delta(pairs: Sequence[RecordDelta | CaseDelta]) -> float | None:
    """Set only when every label either run produced is from the ordered pass/fail set."""
    labels = {d.label_a for d in pairs} | {d.label_b for d in pairs}
    labels.discard(None)
    if not pairs or not labels or not labels.issubset(_ORDERED_LABELS):
        return None
    rate_a = sum(d.label_a == "pass" for d in pairs) / len(pairs)
    rate_b = sum(d.label_b == "pass" for d in pairs) / len(pairs)
    return rate_b - rate_a


def _counts(pairs: Sequence[RecordDelta | CaseDelta]) -> tuple[int, int, int]:
    """Improved, regressed, unchanged — the same tally for both comparisons."""
    return (
        sum(d.classification == "improved" for d in pairs),
        sum(d.classification == "regressed" for d in pairs),
        sum(d.classification == "unchanged" for d in pairs),
    )


def _mean_score_delta(pairs: Sequence[RecordDelta | CaseDelta]) -> float | None:
    deltas = [d.delta for d in pairs if d.delta is not None]
    return fmean(deltas) if deltas else None


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
    improved, regressed, unchanged = _counts(records)
    summary = ComparisonSummary(
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
        mean_score_delta=_mean_score_delta(records),
        pass_rate_delta=_pass_rate_delta(records),
    )
    return Comparison(
        run_a=run_a.run_id,
        run_b=run_b.run_id,
        evaluator_id=evaluator_id,
        records=records,
        summary=summary,
    )


def _scored_records(
    workspace: Path, run: RunRecord, results: Mapping[str, Mapping[str, Any]]
) -> dict[str, DatasetRecord]:
    """Every record `run` scored, resolved and hash-verified (spec 002 research R9).

    `snapshot_ref` names the dataset only to *find* each file; trust comes from
    load_record() recomputing the record's content hash."""
    dataset = run.snapshot_ref.partition("@")[0]
    return {rid: load_record(workspace, dataset, rid) for rid in results}


def _by_case(records: Mapping[str, DatasetRecord]) -> dict[str | None, list[str]]:
    groups: dict[str | None, list[str]] = defaultdict(list)
    for rid in sorted(records):
        groups[case_id(records[rid])].append(rid)
    return groups


def _unmatched(
    rid: str, cid: str | None, reason: UnmatchedReason, result: Mapping[str, Any]
) -> UnmatchedCase:
    return UnmatchedCase(
        record_id=rid,
        case_id=cid,
        reason=reason,
        status=result["status"],
        score=result.get("score"),
        label=result.get("label"),
        fingerprint=result.get("judge_fingerprint"),
        tokens_in=result.get("tokens_in"),
        tokens_out=result.get("tokens_out"),
    )


def compare_cases(
    workspace: Path, run_a: RunRecord, run_b: RunRecord, evaluator_id: str
) -> CaseComparison:
    """Diff two runs' results for `evaluator_id`, pairing records by case — the same `input`
    and `expected` — across any two snapshots (spec 002). Reads record files; writes nothing.

    Every record either run scored lands in exactly one place (FR-011): a CaseDelta when
    its case has exactly one record on each side; an AmbiguousCase when either side has
    more than one, never a guess; otherwise its side's unmatched list, as `no_counterpart`,
    or `no_input` when it has no `input` and so no case (FR-003, FR-012-FR-014).
    """
    results_a = _results_for(run_a, evaluator_id)
    results_b = _results_for(run_b, evaluator_id)
    records_a = _scored_records(workspace, run_a, results_a)
    records_b = _scored_records(workspace, run_b, results_b)
    groups_a, groups_b = _by_case(records_a), _by_case(records_b)

    cases: list[CaseDelta] = []
    ambiguous: list[AmbiguousCase] = []
    unmatched_a: list[UnmatchedCase] = []
    unmatched_b: list[UnmatchedCase] = []
    for cid in sorted(k for k in groups_a.keys() | groups_b.keys() if k is not None):
        ids_a, ids_b = groups_a.get(cid, []), groups_b.get(cid, [])
        if len(ids_a) > 1 or len(ids_b) > 1:
            ambiguous.append(AmbiguousCase(cid, tuple(ids_a), tuple(ids_b)))
        elif ids_a and ids_b:
            (rid_a,), (rid_b,) = ids_a, ids_b
            rec_a, rec_b = records_a[rid_a], records_b[rid_b]
            cases.append(CaseDelta(
                case_id=cid,
                record_id_a=rid_a,
                record_id_b=rid_b,
                contexts_changed=rec_a.contexts != rec_b.contexts,
                output_changed=rec_a.output != rec_b.output,
                **_paired_fields(results_a[rid_a], results_b[rid_b]),
            ))
        elif ids_a:
            unmatched_a.append(_unmatched(ids_a[0], cid, "no_counterpart", results_a[ids_a[0]]))
        else:
            unmatched_b.append(_unmatched(ids_b[0], cid, "no_counterpart", results_b[ids_b[0]]))
    unmatched_a += [_unmatched(rid, None, "no_input", results_a[rid]) for rid in groups_a.get(None, [])]
    unmatched_b += [_unmatched(rid, None, "no_input", results_b[rid]) for rid in groups_b.get(None, [])]

    paired = tuple(cases)
    only_a = tuple(sorted(unmatched_a, key=lambda u: u.record_id))
    only_b = tuple(sorted(unmatched_b, key=lambda u: u.record_id))
    improved, regressed, unchanged = _counts(paired)
    summary = CaseComparisonSummary(
        paired=len(paired),
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
        contexts_changed=sum(d.contexts_changed for d in paired),
        output_changed=sum(d.output_changed for d in paired),
        unmatched_a=len(only_a),
        unmatched_b=len(only_b),
        ambiguous=len(ambiguous),
        mean_score_delta=_mean_score_delta(paired),
        pass_rate_delta=_pass_rate_delta(paired),
    )
    return CaseComparison(
        run_a=run_a.run_id,
        run_b=run_b.run_id,
        evaluator_id=evaluator_id,
        cases=paired,
        unmatched_a=only_a,
        unmatched_b=only_b,
        ambiguous=tuple(ambiguous),
        summary=summary,
    )
