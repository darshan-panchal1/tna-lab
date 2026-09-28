"""freeze(): an append-only, timestamp-keyed immutable dataset snapshot (Story 2,
spec FR-006-FR-010, research R2)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tna_lab.datasets import dataset_dir
from tna_lab.storage import canonical_json, read_json, write_json


@dataclass(frozen=True)
class SnapshotRef:
    dataset: str
    tag: str
    snapshot_id: str
    frozen_at: str
    record_ids: tuple[str, ...]


def _snapshot_path(workspace: Path, dataset: str, tag: str) -> Path:
    return dataset_dir(workspace, dataset) / "snapshots" / f"{tag}.json"


def freeze(workspace: Path, dataset: str, tag: str) -> SnapshotRef:
    """Freeze `dataset`'s current HEAD as an immutable snapshot addressable as
    `<dataset>@<tag>`. Raises ValueError if `tag` already exists for this dataset —
    freezing never overwrites (Constitution Article VIII: append-only)."""
    snapshot_path = _snapshot_path(workspace, dataset, tag)
    if snapshot_path.exists():
        raise ValueError(
            f"snapshot tag {tag!r} already exists for dataset {dataset!r}; "
            "freezing never overwrites an existing snapshot"
        )

    head_path = dataset_dir(workspace, dataset) / "head.json"
    record_ids = tuple(sorted(read_json(head_path)["record_ids"]))
    frozen_at = datetime.now(UTC).isoformat()

    # A nonce, not just the timestamp, guarantees two freezes of identical content are
    # never the same snapshot_id even when issued within the same clock tick (research R2).
    nonce = secrets.token_hex(8)
    snapshot_id = hashlib.sha256(
        canonical_json(
            {"dataset": dataset, "record_ids": list(record_ids), "frozen_at": frozen_at, "nonce": nonce}
        ).encode("utf-8")
    ).hexdigest()

    write_json(
        snapshot_path,
        {
            "dataset": dataset,
            "tag": tag,
            "snapshot_id": snapshot_id,
            "frozen_at": frozen_at,
            "record_ids": list(record_ids),
        },
    )
    return SnapshotRef(dataset=dataset, tag=tag, snapshot_id=snapshot_id, frozen_at=frozen_at, record_ids=record_ids)


def resolve(workspace: Path, ref: str) -> SnapshotRef:
    """Resolve `<dataset>@<tag>` to its frozen SnapshotRef. Raises ValueError naming the
    tag if it does not exist — never falls back to the dataset's current HEAD (FR-009)."""
    dataset, _, tag = ref.partition("@")
    snapshot_path = _snapshot_path(workspace, dataset, tag)
    if not snapshot_path.exists():
        raise ValueError(f"snapshot tag {tag!r} does not exist for dataset {dataset!r}")
    data = read_json(snapshot_path)
    return SnapshotRef(
        dataset=data["dataset"],
        tag=data["tag"],
        snapshot_id=data["snapshot_id"],
        frozen_at=data["frozen_at"],
        record_ids=tuple(data["record_ids"]),
    )
