# Data Model: Compare Outputs by Case

**Feature**: [spec.md](spec.md) · **Research**: [research.md](research.md) · **Builds on**: [spec 001 data-model.md](../001-dataset-run-compare/data-model.md)

Every type here is a frozen `dataclass` in a framework-free module, as in spec 001 (spec 001 research R8). This feature adds types and two functions. With one additive exception, `RecordDelta`'s token counts (below), **it changes no existing type, field, file format or on-disk layout**: `DatasetRecord`, `record_id()`, `SnapshotRef`, `RunRecord`, `Comparison`, `RecordDelta` and `ComparisonSummary` are exactly as spec 001's data model defines them (spec FR-002, FR-006).

The new types are named as siblings of spec 001's comparison types, so the two comparison paths read as one family:

| Spec 001 (`compare`) | This spec (`compare_cases`) |
|---|---|
| `Comparison` | `CaseComparison` |
| `RecordDelta` | `CaseDelta` |
| `ComparisonSummary` | `CaseComparisonSummary` |
| — | `UnmatchedCase` |
| — | `AmbiguousCase` |

## RecordDelta (spec 001): token counts added in v0.2.0

This closes a v0.1.0 gap against Article V, and is not part of this feature's own scope (tasks.md T000). Article V requires the token counts trust-no-agent's `EvalResult` carries to be "aggregated and shown, not dropped". v0.1.0's `RecordDelta` carried both fingerprints and neither side's tokens. v0.2.0 adds four fields to it. Every field in [spec 001's RecordDelta table](../001-dataset-run-compare/data-model.md#recorddelta) is otherwise unchanged in name, type and meaning.

| Field | Type | Notes |
|---|---|---|
| `tokens_in_a`, `tokens_in_b` | `int \| None` | Each run's `tokens_in` for this record, echoed from its `EvalResult`. `None` when the result carries none, as a non-`ok` result from trust-no-agent does. |
| `tokens_out_a`, `tokens_out_b` | `int \| None` | The same for `tokens_out`. |

The fields any two paired results share (status, score, label, delta, transition, `status_changed`, classification, fingerprints and token counts) are built by one private function in `compare.py`, which both `RecordDelta` and `CaseDelta` use. The two comparisons therefore cannot drift apart in what they show, just as they cannot in how they classify (spec FR-016). `tna-lab compare`'s table gains a `tokens a → b` column showing `in/out` per side.

## Case identity (`tna_lab/records.py`)

Not a type and not a field — a function, beside `record_id()`.

> **Computed, never stored.** A case id exists only for the duration of a `compare_cases()` call. It is not a field on `DatasetRecord`, not written into record files, not persisted in `RunRecord`, and not cached anywhere in the workspace (research R3; spec FR-002). Every `case_id` a reader sees in a `CaseComparison` was derived from record content at the moment that comparison ran.

**`case_id(record: DatasetRecord) -> str | None`**: `sha256(canonical_json({"input": record.input, "expected": record.expected}))`, full hex digest. It returns `None` when `record.input is None`: that record has no case identity and is never paired (spec FR-003).

| Field hashed | In case identity? | Why |
|---|---|---|
| `input` | yes | What the agent was asked. In trust-no-agent it comes from the golden case's `question` (research R2). |
| `expected` | yes | The reference answer. In trust-no-agent it comes from the golden case's `ground_truth` (research R2). |
| `output` | **no** | What the agent produced. Letting it differ is the point of this feature. |
| `contexts` | **no** | Agent output in trust-no-agent's own mapping (`AgentResult.retrieved_contexts`, research R2). A difference is flagged per case, not keyed on. |
| `metadata` | **no** | Never sent to a judge, so it cannot move a score. It is also where a user labels the output set. |

Values are compared exactly, with no whitespace trimming or case folding (spec FR-020). `expected=None` and `expected=""` are different, as every absent-versus-empty distinction is in spec 001.

## Record resolution (`tna_lab/datasets.py`)

**`load_record(workspace, dataset, record_id) -> DatasetRecord`**: reads `datasets/<dataset>/records/<record_id>.json`, rebuilds the `DatasetRecord`, and recomputes `record_id()` over it. It raises `ValueError` naming the dataset and the record id if the file does not exist, or if the recomputed id differs from the one asked for (research R9; spec FR-010). It is read-only.

## CaseComparison (`tna_lab/compare.py`)

The outcome of `compare_cases()`. Every record either run scored for `evaluator_id` appears in exactly one of `cases`, its side's unmatched list, or an entry of `ambiguous` (spec FR-011).

| Field | Type | Notes |
|---|---|---|
| `run_a`, `run_b` | `str` | The two `run_id`s compared. |
| `evaluator_id` | `str` | One evaluator per comparison, as in spec 001. Both runs must hold results for it (spec FR-008). |
| `cases` | `tuple[CaseDelta, ...]` | One entry per paired case (spec FR-012), ordered by `case_id`. |
| `unmatched_a` | `tuple[UnmatchedCase, ...]` | Records from run A that were not paired and are not ambiguous, ordered by `record_id`. |
| `unmatched_b` | `tuple[UnmatchedCase, ...]` | The same for run B. |
| `ambiguous` | `tuple[AmbiguousCase, ...]` | One entry per case id carried by more than one record within either run, ordered by `case_id`. |
| `summary` | `CaseComparisonSummary` | |

The accounting identity each side must satisfy (spec SC-002): `summary.paired + summary.unmatched_a + sum(len(e.record_ids_a) for e in ambiguous) == len(run_a.results[evaluator_id])`, and symmetrically for B.

Every list is sorted by an id rather than by input order, so the same two runs always produce the same `CaseComparison`. The library call and the CLI therefore agree, and swapping `run_a` and `run_b` changes only which side each field names.

### CaseDelta

One paired case. Every field shared with `RecordDelta` carries exactly the meaning spec 001's data model gives it, computed by the same code (spec FR-015, FR-016).

| Field | Type | Notes |
|---|---|---|
| `case_id` | `str` | **Computed at comparison time from both records' `input` + `expected`; never stored anywhere** (see Case identity above). The same on both sides by construction. |
| `record_id_a`, `record_id_b` | `str` | The record each run scored for this case. They are equal only when both runs scored the identical record, in which case `output_changed` and `contexts_changed` are both false. |
| `status_a`, `status_b` | `str` | As `RecordDelta`. |
| `score_a`, `score_b` | `float \| None` | As `RecordDelta`. |
| `label_a`, `label_b` | `str \| None` | As `RecordDelta`. |
| `delta` | `float \| None` | As `RecordDelta`: `score_b - score_a` when both are scores. |
| `transition` | `str \| None` | As `RecordDelta`: `f"{label_a} → {label_b}"` when both are labels and they differ. |
| `status_changed` | `bool` | As `RecordDelta` (spec 001 FR-023). |
| `classification` | `"improved" \| "regressed" \| "unchanged"` | As `RecordDelta`, including the status-change and ordered pass/fail rules. It is computed by the same function spec 001's `compare()` uses, so the two paths cannot disagree (spec FR-016). |
| `contexts_changed` | `bool` | The two records' `contexts` differ, with absent and empty treated as different (spec FR-017). A case with this flag set is still classified and counted in every aggregate. |
| `output_changed` | `bool` | The two records' `output` values differ (spec FR-018). |
| `fingerprint_a`, `fingerprint_b` | `str \| None` | As `RecordDelta`. Each run's `judge_fingerprint` for its record (Article V; spec 001 FR-027). |
| `tokens_in_a`, `tokens_in_b`, `tokens_out_a`, `tokens_out_b` | `int \| None` | As `RecordDelta` (see above). Each run's token counts for its record, so cost is shown beside every score (Article V). |

No field records a `metadata` difference (spec FR-019).

### UnmatchedCase

One scored record that could not be paired (spec FR-013). It carries its own result, so an unpaired case is never a bare id.

| Field | Type | Notes |
|---|---|---|
| `record_id` | `str` | |
| `case_id` | `str \| None` | **Computed at comparison time; never stored.** `None` exactly when `reason == "no_input"`. |
| `reason` | `"no_counterpart" \| "no_input"` | `no_counterpart`: no record in the other run carries this case id. `no_input`: the record has no `input`, so it has no case id (spec FR-003). |
| `status` | `str` | This record's result, echoed from its `EvalResult`. |
| `score` | `float \| None` | |
| `label` | `str \| None` | |
| `fingerprint` | `str \| None` | This record's `judge_fingerprint` (Article V). |
| `tokens_in`, `tokens_out` | `int \| None` | This record's token counts (Article V). An unpaired score is shown with its cost, as a paired one is. |

### AmbiguousCase

One case id carried by more than one record within either run (spec FR-014). It produces no pair and no delta.

| Field | Type | Notes |
|---|---|---|
| `case_id` | `str` | **Computed at comparison time; never stored.** |
| `record_ids_a` | `tuple[str, ...]` | Every record in run A carrying this case id, sorted. Can be empty, when the ambiguity is on B's side only and A has no record for the case. |
| `record_ids_b` | `tuple[str, ...]` | The same for run B. |

A case is ambiguous if either tuple has more than one entry. A case with exactly one record on each side is a pair and never appears here.

### CaseComparisonSummary

| Field | Type | Notes |
|---|---|---|
| `paired` | `int` | `len(cases)`. |
| `improved`, `regressed`, `unchanged` | `int` | Counts over `cases` only. Unmatched and ambiguous records are counted below, never here (spec FR-021). |
| `contexts_changed` | `int` | Paired cases with `contexts_changed` true. |
| `output_changed` | `int` | Paired cases with `output_changed` true. |
| `unmatched_a`, `unmatched_b` | `int` | `len(unmatched_a)` and `len(unmatched_b)`. |
| `ambiguous` | `int` | `len(ambiguous)`, a count of case ids, not of records. |
| `mean_score_delta` | `float \| None` | Mean of `delta` over **all** paired cases where both scores are present, `contexts_changed` included (spec FR-022). `None` when there is no such case, never `0.0` (spec FR-023). |
| `pass_rate_delta` | `float \| None` | As `ComparisonSummary`, computed over all paired cases, and only for the ordered pass/fail label set. `None` otherwise. |

**`compare_cases(workspace: Path, run_a: RunRecord, run_b: RunRecord, evaluator_id: str) -> CaseComparison`**: reads the record files both runs scored and writes nothing. It raises `ValueError`, before building anything, in this order:

1. Either run lacks results for `evaluator_id` (spec FR-008). The error names the evaluator and the run.
2. The runs' `judge_model` or `generator_model` differ (spec FR-009). The error names both values of the one that differs. No parameter relaxes this.
3. A scored record does not resolve in `workspace`, or resolves to content with a different hash (spec FR-010, research R9). The error names the run and the record.
