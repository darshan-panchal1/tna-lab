"""tna-lab: dataset, run, compare — built on trust-no-agent (Constitution Article VIII)."""

from __future__ import annotations

from tna_lab.compare import Comparison, ComparisonSummary, RecordDelta, compare
from tna_lab.datasets import IngestResult, ingest
from tna_lab.runs import EvaluateFn, RunRecord, load_run, run
from tna_lab.snapshots import SnapshotRef, freeze, resolve

__version__ = "0.1.0"

__all__ = [
    "Comparison",
    "ComparisonSummary",
    "EvaluateFn",
    "IngestResult",
    "RecordDelta",
    "RunRecord",
    "SnapshotRef",
    "__version__",
    "compare",
    "freeze",
    "ingest",
    "load_run",
    "resolve",
    "run",
]
