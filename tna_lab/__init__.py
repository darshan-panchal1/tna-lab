"""tna-lab: dataset, run, compare — built on trust-no-agent (Constitution Article VIII)."""

from __future__ import annotations

import os

# trust-no-agent's evaluate() imports ragas and deepeval, both of which phone home on
# import unless opted out. Article III ("nothing leaves without being told to") applies
# to tna-lab's own dependency tree, not just tna-lab's own code, so these are set before
# any submodule import below can pull ragas/deepeval in. setdefault: a caller's own
# explicit choice (env already set) is never overridden.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

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
