"""DatasetRecord: the same five fields trust-no-agent's EvalRecord accepts, plus a
content-derived identity (research R1). This module imports no framework — stdlib only."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field

from tna_lab.storage import canonical_json


@dataclass(frozen=True)
class DatasetRecord:
    input: str | None = None
    output: str | None = None
    expected: str | None = None
    contexts: tuple[str, ...] | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


def record_id(record: DatasetRecord) -> str:
    """A full sha256 hex digest over the record's normalized field values.

    Ingestion order and source formatting never affect it (spec FR-003). `contexts=None`
    and `contexts=()` are distinct — absence is not the same as an empty, present list.
    """
    payload = {
        "input": record.input,
        "output": record.output,
        "expected": record.expected,
        "contexts": list(record.contexts) if record.contexts is not None else None,
        "metadata": dict(record.metadata),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
