"""tna-lab: dataset, run, compare — built on trust-no-agent (Constitution Article VIII)."""

from __future__ import annotations

from tna_lab.datasets import IngestResult, ingest
from tna_lab.snapshots import SnapshotRef, freeze, resolve

__version__ = "0.1.0"

__all__ = [
    "IngestResult",
    "SnapshotRef",
    "__version__",
    "freeze",
    "ingest",
    "resolve",
]
