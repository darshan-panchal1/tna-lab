# Public API: `tna_lab`, v0.2.0

**Feature**: [../spec.md](../spec.md) · **Types**: [../data-model.md](../data-model.md) · **v0.1.0 contract**: [spec 001 contracts/public-api.md](../../001-dataset-run-compare/contracts/public-api.md)

v0.2.0 is v0.1.0's public API plus one function. The five v0.1.0 functions are unchanged in signature and behavior (spec FR-006). They are listed here so the whole surface reads in one place, and their full contracts stay in spec 001's file rather than being copied, so the two cannot drift.

| Function | CLI | Contract |
|---|---|---|
| `ingest(workspace, dataset, records) -> IngestResult` | `tna-lab ingest` | [spec 001](../../001-dataset-run-compare/contracts/public-api.md#tna_labingest), unchanged |
| `freeze(workspace, dataset, tag) -> SnapshotRef` | `tna-lab freeze` | [spec 001](../../001-dataset-run-compare/contracts/public-api.md#tna_labfreeze), unchanged |
| `run(workspace, snapshot, evaluator_ids, judge=None, cache_dir=None, evaluate_fn=...) -> RunRecord` | `tna-lab run` | [spec 001](../../001-dataset-run-compare/contracts/public-api.md#tna_labrun), unchanged |
| `load_run(workspace, run_id) -> RunRecord` | — | [spec 001](../../001-dataset-run-compare/contracts/public-api.md#tna_labload_run), unchanged |
| `compare(run_a, run_b, evaluator_id) -> Comparison` | `tna-lab compare` | [spec 001](../../001-dataset-run-compare/contracts/public-api.md#tna_labcompare), unchanged, including its snapshot-mismatch error |
| **`compare_cases(workspace, run_a, run_b, evaluator_id) -> CaseComparison`** | **`tna-lab compare-cases`** | **below, new in v0.2.0** |

## `tna_lab.compare_cases`

```python
def compare_cases(
    workspace: Path,
    run_a: RunRecord,
    run_b: RunRecord,
    evaluator_id: str,
) -> CaseComparison:
    """Diff two runs' results for one evaluator, pairing records by case — the same `input`
    and `expected` — across two snapshots, which may belong to two datasets (spec FR-001,
    FR-004, FR-007).

    Where `compare()` holds the records fixed and lets the judging differ, this holds the
    judging fixed and lets the outputs differ. It does not require a shared snapshot, and so
    it cannot promise that every record pairs: anything it could not pair is reported in
    `unmatched_a`, `unmatched_b` or `ambiguous`, never dropped (spec FR-011–FR-014).

    `workspace` is needed because a RunRecord stores results by record id, not the records'
    content, and a case is computed from content. The function reads record files and
    writes nothing. It makes no `evaluate()` call, reads no judge configuration, needs no
    credential and touches no network (spec FR-024).

    Raises ValueError, naming what failed:
      - if either run has no results for `evaluator_id` (spec FR-008);
      - if the runs' judge models or generator models differ; there is no parameter to
        relax this (spec FR-009);
      - if a scored record is missing from `workspace`, or its content no longer hashes to
        its id (spec FR-010, research R9).

    A comparison with zero paired cases is a result, not an error (spec FR-023).
    """
```

There is deliberately no `judge`, `force`, `allow_judge_mismatch` or `match=` parameter. Case identity is fixed by spec FR-001 and is not configurable per call. The judge check has no override (spec FR-009). And `compare()` keeps its own signature, rather than gaining a mode that switches it to case matching (spec FR-005).

CLI: `tna-lab compare-cases <run_a_id> <run_b_id> --evaluator <id> [--workspace <path>] [--json]`

- A separate subcommand, not a flag on `tna-lab compare`: the weaker matching guarantee is never one option away from the stronger one under the same command name (spec FR-005).
- The human-readable output states its matching basis before any case row, so a pasted table cannot be mistaken for `compare`'s (spec FR-026).
- `--json` prints the full `CaseComparison` as `dataclasses.asdict` would render it: `unmatched_a`, `unmatched_b` and `ambiguous` included, identical to the library result (spec FR-025).
- Exit status is 0 on a comparison, including one with zero pairs, and 1 with `tna-lab: error: <message>` on stderr for any error above, matching the other subcommands.

## New public names

Importable from `tna_lab`: `compare_cases`, `CaseComparison`, `CaseDelta`, `CaseComparisonSummary`, `UnmatchedCase`, `AmbiguousCase`.

Importable from their modules, and not re-exported from `tna_lab`, following v0.1.0's placement of `record_id` and `load_jsonl`:

- `tna_lab.records.case_id(record) -> str | None`. Computed, never stored (data-model.md).
- `tna_lab.datasets.load_record(workspace, dataset, record_id) -> DatasetRecord`. Read-only, and verifies the content hash (research R9).

## What this feature does not export

Everything spec 001's contract rules out stays ruled out: no `provider=` argument, no second model-selection variable, no `ragas` or `deepeval` import (Articles I, IV). In addition, nothing here stores a case id, normalizes or fuzzy-matches case text, compares across different judges, or deletes or subsets records (spec Assumptions, Out of scope).
