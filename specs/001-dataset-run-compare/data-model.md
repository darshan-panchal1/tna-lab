# Data Model: Dataset, Run, Compare

**Feature**: [spec.md](spec.md) · **Research**: [research.md](research.md)

All public types are frozen `dataclasses`, defined in framework-free modules (Constitution Article I: no `ragas` or `deepeval` type appears in any field — and no `trustnoagent` type either, beyond the plain `EvalRecord`/`EvalResult` shapes this feature passes through unmodified).

## DatasetRecord (`tna_lab/records.py`)

The same five fields trust-no-agent's own `EvalRecord` accepts — this feature adds no sixth field.

| Field | Type | Default | Notes |
|---|---|---|---|
| `input` | `str \| None` | `None` | |
| `output` | `str \| None` | `None` | |
| `expected` | `str \| None` | `None` | |
| `contexts` | `tuple[str, ...] \| None` | `None` | Ordered; a tuple so the record is hashable. |
| `metadata` | `Mapping[str, str]` | empty | Carried through, never sent to a judge. |

**`record_id(record: DatasetRecord) -> str`**: `sha256(canonical_json({"input":…, "output":…, "expected":…, "contexts": list(contexts) if contexts is not None else None, "metadata": dict(metadata)}))`, full hex digest (R1). Two records with identical field values always produce the same id, regardless of ingestion order or source formatting.

## Dataset (`tna_lab/datasets.py`)

Not a type with its own file — a *name* plus the record files and `head.json` manifest under `datasets/<name>/`.

| Concept | On disk | Rule |
|---|---|---|
| HEAD | `datasets/<name>/head.json`: `{"record_ids": [...]}` | The current, mutable set. Grows only by ingestion (FR-004). Never shrinks in this spec — no delete operation exists. |
| A record | `datasets/<name>/records/<record_id>.json` | Written once; re-ingesting the same `record_id` overwrites with byte-identical content, a safe no-op (FR-003). |

**`ingest(workspace, name, records: Iterable[DatasetRecord]) -> IngestResult`**: computes each record's id, writes any not already present, adds new ids to `head.json`. Returns `IngestResult(added: int, already_present: int)`.

## SnapshotRef (`tna_lab/snapshots.py`)

| Field | Type | Notes |
|---|---|---|
| `dataset` | `str` | The dataset name at freeze time. |
| `tag` | `str` | The human-readable name, unique per dataset (re-freezing under an existing tag is an error, not an overwrite — Article VIII's append-only rule). |
| `snapshot_id` | `str` | `sha256(canonical_json({"dataset": dataset, "record_ids": sorted(record_ids), "frozen_at": frozen_at}))` (R2). This, not `f"{dataset}@{tag}"`, is what a run record stores. |
| `frozen_at` | `str` | ISO-8601 UTC, microsecond precision. |
| `record_ids` | `tuple[str, ...]` | The frozen record set, sorted for a deterministic on-disk form. |

On disk at `datasets/<dataset>/snapshots/<tag>.json`. Immutable once written (FR-007): the file is created once and never rewritten.

**`freeze(workspace, dataset, tag) -> SnapshotRef`**: reads `head.json`, writes the snapshot file. Fails if `tag` already exists for this dataset.

**`resolve(workspace, ref: str) -> SnapshotRef`**: parses `<dataset>@<tag>`, reads the snapshot file, fails with a named error if the tag does not exist (FR-009) — never falls back to HEAD.

## RunRecord (`tna_lab/runs.py`)

| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | `<compact ISO-8601 UTC>-<8 hex>` (R3). |
| `snapshot_id` | `str` | The exact snapshot identity scored (FR-015) — not the dataset name, not the tag alone. |
| `snapshot_ref` | `str` | `<dataset>@<tag>`, kept for human readability only; never used for comparison equality (FR-021 compares `snapshot_id`). |
| `evaluator_ids` | `tuple[str, ...]` | Every evaluator id this run was asked to score (FR-016). |
| `judge_model` | `str` | From the `JudgeConfig` used — echoed for audit, never the credential. |
| `generator_model` | `str` | Same. |
| `created_at` | `str` | ISO-8601 UTC. |
| `results` | `Mapping[str, Mapping[str, EvalResultDict]]` | `{evaluator_id: {record_id: <trust-no-agent's EvalResult, as a plain dict, unmodified>}}` (FR-014, FR-016). |

On disk at `runs/<run_id>.json`, written once, atomically, when the run completes.

**`run(workspace, snapshot: SnapshotRef, evaluator_ids: Sequence[str], judge: JudgeConfig | None = None, evaluate_fn: EvaluateFn = trustnoagent.evaluators.evaluate) -> RunRecord`** (R5, R6): for every `(record_id, evaluator_id)` pair, loads the record, calls `evaluate_fn(evaluator_id, record, judge)`, and stores the returned `EvalResult` unmodified. `judge` defaults to `JudgeConfig.from_env()` if not given (FR-013).

**`load_run(workspace, run_id) -> RunRecord`**: reads a persisted run record back.

## Comparison (`tna_lab/compare.py`)

| Field | Type | Notes |
|---|---|---|
| `run_a`, `run_b` | `str` | The two `run_id`s compared. |
| `evaluator_id` | `str` | Which evaluator's results this comparison covers (FR-021: one evaluator id per comparison). |
| `records` | `tuple[RecordDelta, ...]` | One entry per record present in both runs' results for this evaluator. |
| `summary` | `ComparisonSummary` | Aggregate counts and, where applicable, a mean-score or pass-rate delta. |

### RecordDelta

| Field | Type | Notes |
|---|---|---|
| `record_id` | `str` | |
| `status_a`, `status_b` | `Status` | trust-no-agent's own status literal, echoed. |
| `score_a`, `score_b` | `float \| None` | Present only for `output_type == "score"` evaluators. |
| `label_a`, `label_b` | `str \| None` | Present only for `output_type == "label"` evaluators. |
| `delta` | `float \| None` | `score_b - score_a`, when both are scores (R7). `None` for label-producing or status-mismatched pairs. |
| `transition` | `str \| None` | `f"{label_a} → {label_b}"` when both are labels and they differ; `None` otherwise. |
| `status_changed` | `bool` | `status_a != status_b` (FR-023) — reported independently of `delta`/`transition`. |
| `classification` | `"improved" \| "regressed" \| "unchanged"` | Derived: a `delta > 0` or a label transition toward the rubric's better label is `"improved"`; the reverse is `"regressed"`; anything else, including any case where a rubric's labels have no defined ordering, is `"unchanged"` unless `status_changed` (see note below). |

**Note on label ordering.** A `labels`-based rubric (trust-no-agent's `RubricJudge`) has no built-in notion of "better" — `{"pass", "fail"}` has an obvious order, but a caller-defined rubric might not. This spec's FR-024 only requires a pass-rate delta *when the evaluator's output type supports one*; for label sets with no declared order, `classification` reports `"unchanged"` for any non-identical-but-unordered transition, and the raw `transition` string is still present so nothing is lost — only the ordering judgment is withheld where it would be a guess.

### ComparisonSummary

| Field | Type | Notes |
|---|---|---|
| `improved`, `regressed`, `unchanged` | `int` | Counts over `records` (FR-022, FR-024). |
| `mean_score_delta` | `float \| None` | Mean of `delta` over records where both scores are present, for `output_type == "score"` evaluators only. |
| `pass_rate_delta` | `float \| None` | For `output_type == "label"` evaluators with an ordered pass/fail-style label set only (see note above); otherwise `None`. |

**`compare(run_a: RunRecord, run_b: RunRecord, evaluator_id: str) -> Comparison`** (FR-019–FR-025): fails if the two runs' `snapshot_id` differ, or if either run lacks results for `evaluator_id` — both named in the error (FR-021).
