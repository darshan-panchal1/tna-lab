"""ingest(): content-addressed, idempotent record loading into a named dataset
(Story 1, spec FR-001-FR-005)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from tna_lab.records import DatasetRecord, record_id
from tna_lab.storage import overwrite_json, read_json, write_json

_FIELDS = frozenset({"input", "output", "expected", "contexts", "metadata"})


@dataclass(frozen=True)
class IngestResult:
    added: int
    already_present: int


def dataset_dir(workspace: Path, dataset: str) -> Path:
    """`workspace` is an already-resolved root (see `storage.workspace_root`); this
    module never re-resolves it, so a library caller's explicit path is never silently
    reinterpreted relative to the process's current directory."""
    return workspace / "datasets" / dataset


def ingest(workspace: Path, dataset: str, records: Iterable[DatasetRecord]) -> IngestResult:
    ds_dir = dataset_dir(workspace, dataset)
    records_dir = ds_dir / "records"
    head_path = ds_dir / "head.json"

    head_ids: set[str] = set(read_json(head_path)["record_ids"]) if head_path.exists() else set()

    added = 0
    already_present = 0
    for record in records:
        rid = record_id(record)
        record_path = records_dir / f"{rid}.json"
        if record_path.exists():
            already_present += 1
        else:
            payload = dict(asdict(record))
            payload["contexts"] = list(record.contexts) if record.contexts is not None else None
            write_json(record_path, payload)
            added += 1
        head_ids.add(rid)

    overwrite_json(head_path, {"record_ids": sorted(head_ids)})
    return IngestResult(added=added, already_present=already_present)


def load_jsonl(path: Path) -> list[DatasetRecord]:
    """Parse one DatasetRecord per non-blank line of a JSONL file (FR-001).

    Raises ValueError naming the file and line for a line that is not a JSON object, or
    that carries a field outside trust-no-agent's EvalRecord five — never silently drops it.
    """
    records = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        data = json.loads(line)
        if not isinstance(data, dict):  # bad input data, not a caller's programming error
            kind = type(data).__name__
            raise ValueError(f"{path}:{lineno}: expected a JSON object, got {kind}")  # noqa: TRY004
        if unknown := sorted(data.keys() - _FIELDS):
            raise ValueError(
                f"{path}:{lineno}: unknown field(s) {', '.join(map(repr, unknown))}; "
                f"a record has only {', '.join(sorted(_FIELDS))}"
            )
        contexts = data.get("contexts")
        records.append(
            DatasetRecord(
                input=data.get("input"),
                output=data.get("output"),
                expected=data.get("expected"),
                contexts=tuple(contexts) if contexts is not None else None,
                metadata=data.get("metadata", {}),
            )
        )
    return records


def load_record(workspace: Path, dataset: str, rid: str) -> DatasetRecord:
    """Read one record back and prove it is the record `rid` names (spec 002 research R9).

    Read-only. Raises ValueError naming the dataset and the record if the file is absent,
    or if its content no longer hashes to `rid`: record files are content-addressed, so a
    mismatch means the workspace was edited or assembled from elsewhere.
    """
    path = dataset_dir(workspace, dataset) / "records" / f"{rid}.json"
    if not path.exists():
        raise ValueError(f"record {rid!r} does not exist in dataset {dataset!r}")
    data = read_json(path)
    contexts = data["contexts"]
    record = DatasetRecord(
        input=data["input"],
        output=data["output"],
        expected=data["expected"],
        contexts=tuple(contexts) if contexts is not None else None,
        metadata=data["metadata"],
    )
    if record_id(record) != rid:
        raise ValueError(
            f"record {rid!r} in dataset {dataset!r} no longer matches its content hash; "
            "the workspace was modified after ingestion"
        )
    return record
