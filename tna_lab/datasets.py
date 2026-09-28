"""ingest(): content-addressed, idempotent record loading into a named dataset
(Story 1, spec FR-001-FR-005)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from tna_lab.records import DatasetRecord, record_id
from tna_lab.storage import overwrite_json, read_json, write_json


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
