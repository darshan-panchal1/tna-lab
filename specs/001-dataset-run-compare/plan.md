# Implementation Plan: Dataset, Run, Compare

**Branch**: none; the spec was written on `main`. Create a feature branch before implementing. | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-dataset-run-compare/spec.md`, Constitution Article VIII (First amendment).

## Summary

Build the three primitives Article VIII locks as tna-lab's v1 slice, as a Python library with a thin CLI wrapper, and nothing else:

- **`ingest`** — content-addressed, idempotent record loading into a named, mutable dataset.
- **`freeze`** — an append-only, timestamp-keyed immutable snapshot, addressable as `<dataset>@<tag>`.
- **`run`** — score a frozen snapshot with one or more trust-no-agent evaluator ids, persisting every `EvalResult` unmodified.
- **`compare`** — a structured, per-record diff between two runs against the same snapshot, classifying every record as improved/regressed/unchanged.

**Technical approach**:
- **Local, content-addressed storage.** No database. One JSON file per record identity, one per snapshot, one per run — the same "identity from content, one file per key" discipline trust-no-agent's own evidence cache uses (research R1, R4).
- **trust-no-agent is the only scorer, called exactly once per (record, evaluator) pair.** `run()` never recomputes, retries, or reinterprets a score (Article I); it takes an injectable `evaluate_fn` for testing only, defaulting to trust-no-agent's real `evaluate()` (research R6).
- **No interception of judge configuration.** `JudgeConfig.from_env()` is called as-is when a caller doesn't supply one; nothing here adds a second configuration path (Article IV).

The design notes ([research.md](research.md)) record why each storage and identity choice was made.

## Technical Context

**Language/Version**: Python 3.12, exact — matching trust-no-agent's pin (Constitution Article VI).

**Primary Dependencies**: `trust-no-agent`, exact pin (`==1.1.0` at time of writing). No other runtime dependency for v0.1.0 — the CLI uses the standard library's `argparse`, and the data model uses plain `dataclasses` (research R8), so nothing else is required to satisfy Article VI's "no dependency this feature doesn't need."

**Storage**: local, embedded — a `.tna-lab/` directory tree under the workspace root (default: current working directory). No external database (Constitution Article VI). Layout: [research.md](research.md) §R4.

**Testing**: pytest; `ruff`; `mypy --strict` (Constitution Article VI). No committed judge-cache evidence exists for tna-lab to test against — `run()`'s tests use an injected fake `evaluate_fn` (research R6), never a live NIM call and never trust-no-agent's own cache.

**Target Platform**: library on CPython 3.12, plus a CLI entry point. CI: GitHub Actions on `ubuntu-latest`, matching trust-no-agent's own setup where nothing here argues for a different choice.

**Project Type**: Python library with a thin operator CLI (Constitution Article II) — no server, no UI, in this spec.

**Performance goals**: none stated by this spec beyond FR-026 (every capability reachable with no server running). Runtime is dominated by however long trust-no-agent's own `evaluate()` calls take; this feature adds no computation heavier than JSON read/write and dataclass field comparison.

**Constraints**:
- No import of `ragas` or `deepeval` anywhere in `tna_lab/` (Constitution Article I).
- No provider abstraction, no second `JUDGE_MODEL`-shaped variable (Constitution Article IV).
- No server or UI requirement on any code path this spec defines (Constitution Article II).
- Dataset/snapshot versioning is append-only; no dataset-to-dataset diff (Constitution Article VIII; spec Assumptions).

**Scale/Scope**: 4 user stories, 28 functional requirements, roughly 7 new library modules plus a CLI module and their tests. No existing code to preserve — everything in this feature is new.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (below).*

The constitution is the repo root `CONSTITUTION.md`. No `.specify/memory/constitution.md` exists (same convention as trust-no-agent).

| Article | Gate | Pre-design | Post-design |
|---|---|---|---|
| 0: Prime Contract | Cold clone → dataset → offline eval pass → comparison, no key required until live | ✅ Nothing in this spec calls live mode by default | ✅ `run()`'s default `evaluate_fn` defers entirely to trust-no-agent's own offline/live rule; ingest/freeze/compare never touch a judge at all |
| I: One scorer | No `ragas`/`deepeval` import in `tna_lab/`; no second scoring path | ✅ | ✅ `run()` calls only `trustnoagent.evaluators.evaluate`; `tests/test_article_i_boundary.py` (new) asserts the import graph |
| II: Library first, UI optional | Every capability reachable with no server; CLI mirrors library exactly | ✅ | ✅ `cli.py` is argument parsing only — it calls the same four functions the library exports, nothing more |
| III: Self-hosted, no telemetry | No outbound call this feature doesn't ask for | ✅ | ✅ This feature makes zero network calls of its own; the only network call anywhere in the path is trust-no-agent's own judge call, which Article III already governs |
| IV: One judge path | No provider abstraction; `JudgeConfig.from_env()` used as-is | ✅ | ✅ `run()`'s `judge` parameter, when omitted, is built by calling trust-no-agent's own accessor — no re-implementation, no default supplied by tna-lab |
| V: Determinism and cost stay visible | Fingerprint and cost travel with every stored *and shown* score | ✅ | ✅ `RunRecord.results` stores trust-no-agent's `EvalResult` unmodified (fingerprint included, FR-014); `Comparison`/`RecordDelta` do not drop it — a later CLI/UI rendering of a comparison is expected to surface it, a constraint carried forward for any spec that renders a comparison |
| VI: Stack | Python 3.12; `uv`; `ruff`; `mypy --strict`; exact pins; local storage | ✅ | ✅ No dependency beyond `trust-no-agent`; storage is a local directory tree |
| VII: Out of scope | No multi-tenant auth, no SaaS mode, no second scoring engine, no plugin system, no realtime ingestion | ✅ | ✅ Nothing in this spec touches any of these |
| VIII: The v1 slice | Exactly dataset/run/compare; versioning append-only, timestamp-keyed; ingestion format and hosted view deferred | ✅ | ✅ This is the spec Article VIII names; nothing here reaches into trace ingestion or a UI |
| IX: Process | Spec-Driven Development order | ✅ | ✅ This plan follows spec 001, which followed the First amendment |

**Result: PASS.** No amendment is needed for this feature — it is the feature Article VIII already locked in, not an expansion of it.

## Project Structure

### Documentation (this feature)

```text
specs/001-dataset-run-compare/
├── spec.md                  # Draft, 2026-09-28
├── plan.md                  # this file
├── research.md              # design-decision log, R1–R8
├── data-model.md
├── contracts/
│   └── public-api.md
└── tasks.md                 # Phase 2, this session
```

### Source code (repository root)

```text
tna_lab/
├── __init__.py               NEW  public exports: ingest, freeze, run, load_run, compare
├── records.py                 NEW  DatasetRecord, record_id()  (R1)
├── storage.py                  NEW  workspace resolution, canonical_json, JSON read/write helpers  (R4)
├── datasets.py                  NEW  ingest(), IngestResult  (Story 1)
├── snapshots.py                  NEW  SnapshotRef, freeze(), resolve()  (Story 2, R2)
├── runs.py                        NEW  RunRecord, run(), load_run(), EvaluateFn  (Story 3, R5, R6)
├── compare.py                      NEW  Comparison, RecordDelta, ComparisonSummary, compare()  (Story 4, R7)
└── cli.py                           NEW  argparse subcommands: ingest, freeze, run, compare
tests/
├── test_records.py                  NEW  record identity (R1)
├── test_storage.py                   NEW  workspace resolution, JSON round-trip
├── test_datasets.py                   NEW  Story 1
├── test_snapshots.py                   NEW  Story 2
├── test_runs.py                         NEW  Story 3, using a fake evaluate_fn (R6)
├── test_compare.py                       NEW  Story 4, both score- and label-output evaluators (R7)
├── test_cli.py                            NEW  every story, via the CLI, asserting parity with the library
└── test_article_i_boundary.py              NEW  import-graph guard: no module under tna_lab/ imports ragas or deepeval
pyproject.toml                                NEW  project metadata, trust-no-agent pin, exact Python 3.12
.python-version                               NEW  "3.12"
.github/workflows/ci.yml                      NEW  uv sync, pytest, ruff, mypy on push/PR
```

**Structure Decision**: flat package, one module per primitive plus storage/records as shared foundations. No sub-packages — at 4 stories and roughly 7 modules there is nothing yet that needs a deeper layout, and Article VI's stack discipline gives no reason to add one preemptively.

## Implementation order (for tasks.md)

1. **Foundations.** `records.py` (identity), `storage.py` (workspace + JSON helpers) — nothing else can be tested without these.
2. **Story 1 (ingest).** `datasets.py`, with the idempotent-reingestion test as the load-bearing one.
3. **Story 2 (freeze).** `snapshots.py`, depending on Story 1's `head.json`.
4. **Story 3 (run).** `runs.py`, with the injectable `evaluate_fn` seam (R6) built and tested before wiring the real `trustnoagent.evaluators.evaluate` default.
5. **Story 4 (compare).** `compare.py`, covering both score- and label-output evaluators (R7) and the snapshot/evaluator-mismatch error path.
6. **CLI.** `cli.py`, one subcommand per story, each asserted to match its library call's result (Article II).
7. **Packaging and CI.** `pyproject.toml`, `.python-version`, `.github/workflows/ci.yml`, then the full gate: `uv run pytest && uv run ruff check . && uv run mypy .`.

## Complexity Tracking

*No entries.* Nothing in this plan deviates from the constitution — Article VIII names exactly this feature as v1, so there is no simpler alternative to reject and no violation to justify.
