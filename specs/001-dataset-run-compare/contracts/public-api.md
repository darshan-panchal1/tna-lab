# Public API: `tna_lab`, v0.1.0

**Feature**: [../spec.md](../spec.md) · **Types**: [../data-model.md](../data-model.md)

Every function below is synchronous, importable with no server or UI running (Constitution Article II), and reachable identically from the CLI (`tna-lab ...`). None constructs a model client or reads a judge-related environment variable beyond what `trustnoagent.evaluators.JudgeConfig.from_env()` itself reads (Article IV).

## `tna_lab.ingest`

```python
def ingest(
    workspace: Path,
    dataset: str,
    records: Iterable[DatasetRecord],
) -> IngestResult:
    """Add records to a dataset, deduplicating by content identity (FR-001–FR-005)."""
```

CLI: `tna-lab ingest <records.jsonl> --dataset <name> [--workspace <path>]`

## `tna_lab.freeze`

```python
def freeze(workspace: Path, dataset: str, tag: str) -> SnapshotRef:
    """Freeze a dataset's current record set as an immutable, named snapshot (FR-006–FR-010).

    Raises ValueError if `tag` already exists for this dataset — freezing never overwrites.
    """
```

CLI: `tna-lab freeze <dataset> <tag> [--workspace <path>]`

## `tna_lab.run`

```python
def run(
    workspace: Path,
    snapshot: str,                      # "<dataset>@<tag>"
    evaluator_ids: Sequence[str],
    judge: JudgeConfig | None = None,   # defaults to JudgeConfig.from_env()
    evaluate_fn: EvaluateFn = trustnoagent.evaluators.evaluate,  # test seam only, R6
) -> RunRecord:
    """Score a frozen snapshot with one or more evaluators via trust-no-agent (FR-011–FR-018).

    Raises ValueError if `snapshot` does not resolve (FR-009).
    Never raises for a per-record scoring failure — every EvalResult, whatever its status,
    is persisted (FR-012, FR-017).
    """
```

CLI: `tna-lab run <dataset>@<tag> --evaluator <id> [--evaluator <id> ...] [--workspace <path>]`

## `tna_lab.load_run`

```python
def load_run(workspace: Path, run_id: str) -> RunRecord:
    """Read a persisted run record back. Raises ValueError if `run_id` does not exist."""
```

## `tna_lab.compare`

```python
def compare(run_a: RunRecord, run_b: RunRecord, evaluator_id: str) -> Comparison:
    """Diff two runs' results for one evaluator (FR-019–FR-025).

    Raises ValueError if the two runs reference different snapshot ids, or if either
    lacks results for `evaluator_id` — the error names which condition failed.
    """
```

CLI: `tna-lab compare <run_a_id> <run_b_id> --evaluator <id> [--workspace <path>]`

## What this feature does not export

No function here accepts a `provider=` argument, a second model-selection env var, or a credential beyond what `JudgeConfig.from_env()` itself reads (Article IV). No function here imports `ragas` or `deepeval` (Article I) — `tests/test_article_i_boundary.py` asserts this over the import graph, the same discipline trust-no-agent's own `tests/test_article_ii_facade.py` uses for its routing facade.
