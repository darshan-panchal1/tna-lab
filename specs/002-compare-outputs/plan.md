# Implementation Plan: Compare Outputs by Case

**Branch**: none; spec 002 was written on `main`, as spec 001 was. | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md) (approved, 36916ba)

**Input**: Feature specification from `specs/002-compare-outputs/spec.md`; Constitution Article VIII (Second amendment); [research.md](research.md) R1–R9.

## Summary

Add one comparison beside the existing one, and change nothing that exists:

- **`compare_cases(workspace, run_a, run_b, evaluator_id)`**: pairs two runs' scored records by *case* (the same `input` and `expected`) across two snapshots, possibly of two datasets. It returns a per-case diff with the same classification `compare()` uses, plus two flags (`contexts_changed`, `output_changed`), plus an exact account of every record it could not pair.
- **`tna-lab compare-cases`**: the same capability as a separate CLI subcommand.

**Technical approach**:

- **Additive.** No existing type, field, file format or function behavior changes (spec FR-002, FR-006). Spec 001's test suite is the guard: it must pass with no edits.
- **Case identity is computed, never stored.** `case_id()` sits beside `record_id()` in `records.py` and is evaluated only inside a comparison (research R3).
- **One classification implementation, two callers.** `compare_cases()` lives in `compare.py`, beside `compare()`, and calls the same private classification and aggregation helpers. That makes "the two paths never disagree about *improved*" (spec FR-016) structural rather than a promise kept by duplicated code.
- **Read-only against the workspace.** `compare_cases()` resolves each scored record with a new `datasets.load_record()`, which verifies the content hash (research R9), and it writes nothing.
- **No judge, no network.** The comparison reads two finished runs. It calls no `evaluate()`, so it has no `evaluate_fn` seam to inject, and nothing to cost (spec FR-024).

## Technical Context

**Language/Version**: Python 3.12, exact, unchanged (Article VI).

**Primary Dependencies**: `trust-no-agent==1.1.0`, unchanged. No new dependency: hashing, JSON and dataclasses are the standard library's, as in v0.1.0.

**Storage**: unchanged. `compare_cases()` reads `datasets/<name>/records/<record_id>.json` and adds no file, directory or field (spec FR-002). A v0.1.0 workspace is compared as-is (spec SC-006).

**Testing**: pytest, `ruff`, `mypy --strict`. Tests build real workspaces with `ingest`/`freeze`, and run records through `run()` with a fake `evaluate_fn` (spec 001 research R6) or directly as `RunRecord` fixtures over ingested records. No test file for this feature imports `trustnoagent`, the same rule spec 001's `test_runs.py` follows.

**Target Platform**: unchanged. CPython 3.12 library plus CLI, with CI in `.github/workflows/ci.yml` and no credentials.

**Project Type**: unchanged. A Python library with a thin CLI (Article II).

**Performance goals**: none beyond spec 001's. A comparison reads one JSON file per scored record per run and hashes it once, so it is linear in the records scored and makes no network call.

**Constraints**:

- Spec 001's `record_id`, `SnapshotRef`, `RunRecord`, `Comparison`, `RecordDelta` and `ComparisonSummary`, and the behavior of `compare()`, are frozen (spec FR-006).
- `compare.py` imports no `trustnoagent`, as in spec 001 (spec 001 T024), so `compare_cases()` inherits that.
- No parameter, flag or environment variable relaxes the judge-mismatch check (spec FR-009).
- No fuzzy matching and no guessing among ambiguous records (spec FR-014, FR-020).
- The comparison never writes to the workspace.

**Scale/Scope**: 3 user stories and 27 functional requirements. The changes: one new function each in `records.py` and `datasets.py`; one new function and five new types in `compare.py`; one new CLI subcommand; exports; and a README section. There are no new modules.

## Constitution Check

*GATE: Must pass before implementation. Re-checked after design (below).* The constitution is the repo-root `CONSTITUTION.md`, as of the Second amendment (2026-09-29).

| Article | Gate | Pre-design | Post-design |
|---|---|---|---|
| 0: Prime Contract | Cold clone → dataset → offline eval pass → comparison, with no key required until live | ✅ Comparing by case needs no key | ✅ `compare_cases()` reads two finished runs and never reaches a judge, so it adds nothing a cold clone needs a key for. *Inherited, not introduced:* Article 0 names `uv run tna-lab init`, which no spec has built. That is unchanged here and out of this spec's scope. |
| I: One scorer | No `ragas`/`deepeval` import in `tna_lab/`; no second scoring path | ✅ | ✅ `compare_cases()` computes only what Article I allows ("aggregates over results trust-no-agent already returned … deltas between experiments") and makes no `evaluate()` call. `tests/test_article_i_boundary.py` covers the changed modules unchanged. |
| II: Library first, UI optional | Every capability reachable with no server; the CLI mirrors the library exactly | ✅ | ✅ `tna-lab compare-cases` parses arguments, calls `load_run` ×2 and then `compare_cases`, and formats the result. `--json` equals the library result (spec FR-025). |
| III: Self-hosted, no telemetry | No outbound call this feature doesn't ask for | ✅ | ✅ Zero network calls, by design (spec FR-024). *Improved here:* Article III's socket-level guard is marked "to be built", and spec 001 never built it. This plan adds a narrow version for this feature's own tests: `compare_cases()` runs with `socket.socket` patched to raise (T019). It does not extend to the whole test suite; that remains open. |
| IV: One judge path | No provider abstraction; `JudgeConfig.from_env()` used as-is | ✅ | ✅ `compare_cases()` takes no `judge` and reads no judge configuration. It compares the `judge_model`/`generator_model` strings the runs already recorded, and adds no configuration surface. |
| V: Determinism and cost stay visible | Fingerprint and cost travel with every stored *and shown* score | ✅ | ✅ for fingerprints: every `CaseDelta` carries both, and every `UnmatchedCase` carries its own, so even an unpaired score is shown with its judge. The judge-mismatch error (spec FR-009) is this article applied to attribution. *Inherited, not introduced:* Article V's third bullet asks that token counts be "aggregated and shown". Spec 001's `compare()` does not surface them, and neither does `compare_cases()`. They stay in each run record, unmodified. The comparison itself costs nothing (spec FR-024). A spend view across runs is a separate feature. |
| VI: Stack | Python 3.12; `uv`; `ruff`; `mypy --strict`; exact pins; local storage | ✅ | ✅ No new dependency or storage. The version bumps to `0.2.0` in `pyproject.toml` and `tna_lab/__init__.py`. |
| VII: Out of scope | No multi-tenant auth, SaaS mode, second scoring engine, plugin system or realtime ingestion | ✅ | ✅ Nothing here touches any of these. |
| VIII: The v1 slice *(Second amendment)* | Exactly dataset/run/compare; a spec beyond it names which deferred item it un-defers | ✅ spec.md names the third deferred item and only that one | ✅ This extends the *compare* primitive and adds no fourth. Trace/OTel ingestion and a hosted view stay deferred. **Follow-up needed, not a violation:** once v0.2.0 ships, Article VIII's deferred list will still name output comparison as deferred, which will then be false. Recording it as delivered is a constitution amendment, so it is left for your decision (T030) rather than folded into implementation. |
| IX: Process | Spec-Driven Development order | ✅ | ✅ Second amendment → research.md (99d7651) → spec.md (36916ba, approved) → this plan and tasks.md → implementation, after review. |

**Result: PASS.** Two gaps from v0.1.0 are carried forward unchanged and named above: Article 0's `init` and Article V's token counts. One is partly closed: Article III gets a socket guard for this feature's tests. One constitutional follow-up (Article VIII's deferred list) waits on your decision in T030.

## Project Structure

### Documentation (this feature)

```text
specs/002-compare-outputs/
├── research.md               R1–R8 (99d7651), plus R9 added by this plan
├── spec.md                   approved (36916ba)
├── plan.md                   this file
├── data-model.md             CaseComparison, CaseDelta, UnmatchedCase, AmbiguousCase, CaseComparisonSummary
├── contracts/
│   └── public-api.md         the v0.2.0 surface: 5 unchanged functions (linked) + compare_cases
├── quickstart.md             self-contained walkthrough in its own fresh directory
└── tasks.md
```

### Source code (repository root)

```text
tna_lab/
├── __init__.py       CHANGED  export compare_cases + 5 new types; __version__ = "0.2.0"
├── records.py        CHANGED  + case_id(record) -> str | None            (computed, never stored)
├── datasets.py       CHANGED  + load_record(workspace, dataset, record_id)  (read-only, hash-verified, R9)
├── compare.py        CHANGED  + CaseDelta, UnmatchedCase, AmbiguousCase, CaseComparisonSummary,
│                              CaseComparison, compare_cases(); classification and aggregation
│                              helpers shared with compare(), whose behavior does not change
├── cli.py            CHANGED  + `compare-cases` subcommand; `compare` untouched
├── runs.py           unchanged
├── snapshots.py      unchanged
└── storage.py        unchanged
tests/
├── test_records.py           CHANGED  additive: case_id
├── test_datasets.py          CHANGED  additive: load_record
├── test_compare_cases.py     NEW      Stories 1–3
├── test_cli.py               CHANGED  additive: compare-cases
├── test_compare.py           unchanged; must pass unmodified (the refactor's guard)
└── (every other test file)   unchanged
README.md                     CHANGED  compare-cases section; "does not do" section updated for v0.2.0
pyproject.toml                CHANGED  version = "0.2.0"
```

**Structure decision**: no new module. `compare_cases()` goes in `compare.py`, not a new `cases.py`. The two comparisons share classification and aggregation code, and keeping that code private to one module is what enforces spec FR-016 without exporting helpers whose only purpose is to be shared. `load_record()` goes in `datasets.py`, which already owns the record-file layout (`dataset_dir`), rather than in `compare.py`, so record-file knowledge stays in one place.

## Design notes that tasks.md depends on

- **Shared helpers.** `compare.py`'s `_classify()` already takes plain values (statuses, delta, labels) and is reused as-is. `_pass_rate_delta()` takes `tuple[RecordDelta, ...]` today. It is generalized to take `(label_a, label_b)` pairs, and `compare()` calls it the same way it does now. `tests/test_compare.py`, unmodified, proves `compare()`'s results did not move.
- **Locating records** (research R9). The dataset name is `run.snapshot_ref.partition("@")[0]`, the same split `snapshots.resolve()` uses. `load_record()` recomputes `record_id()` over what it read and raises if it differs.
- **Error order** (data-model.md): evaluator present in both runs, then judge and generator equal, then every scored record resolves. Checks run before any pairing, so an error never comes with a partial result.
- **Pairing algorithm**. For each run: take the results for `evaluator_id`, load each record, and group record ids by `case_id()`, with `None` meaning `no_input`. A case id with exactly one record per side is a `CaseDelta`. A case id with more than one record on either side is an `AmbiguousCase`. Every remaining record is an `UnmatchedCase` (`no_counterpart`, or `no_input` for `None`). This satisfies the accounting identity in data-model.md by construction, and T015 also tests it.
- **Ordering**. `cases` and `ambiguous` are ordered by `case_id`; the unmatched lists by `record_id`. The result depends only on content, never on dict or file order.
- **CLI output** (spec FR-026). The first line reads `matched by case (input + expected) across snapshots — no same-snapshot guarantee`. Next comes one header line naming both run ids, their `snapshot_ref`s and the shared judge model. Then the case table (`case`, `status`, `a`, `b`, `delta`, `class`, `ctx`, `out`, `fingerprint a → b`), `unmatched in a (n):` and `unmatched in b (n):` sections listing record, reason, status and score or label, an `ambiguous (n):` section listing each case with its record ids per side, and one `summary:` line with every count from `CaseComparisonSummary`. An empty section prints its header with `(0)`, so the absence of unmatched cases is stated, not implied.

## Implementation order (for tasks.md)

1. **Foundations**: `records.case_id()` and `datasets.load_record()`, tested first. Nothing else can be tested without them.
2. **Story 1 (pair and diff)**: the new types, `compare_cases()` for fully paired runs, and the shared-helper refactor, with `test_compare.py` as the refactor's guard.
3. **Story 2 (account for everything)**: unmatched, ambiguous and `no_input`, the accounting identity, and zero overlap.
4. **Story 3 (refuse different judging)**: the three preconditions and their error order, plus the read-only and no-network guards.
5. **CLI**: `compare-cases`, with parity against the library, and `compare` asserted unchanged.
6. **Exports, docs, version**: `__init__.py`, README, `0.2.0`, then the final GATE. Then two items for you: the live quickstart run, and the Article VIII amendment decision.

## Complexity Tracking

*No entries.* Nothing here deviates from the constitution. The Article VIII follow-up in the Constitution Check is a record-keeping amendment triggered by shipping this feature, not a deviation from the article: this spec does what that article's "Enforced by" clause requires.
