# Tasks: Dataset, Run, Compare

**Input**: Design documents from `specs/001-dataset-run-compare/`: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Requested, TDD. In every phase, write the phase's tests first and watch them fail (red) before implementing.

**Gate**: every phase ends with **GATE**:

```bash
uv run pytest && uv run ruff check . && uv run mypy .
```

Expected: green, `mypy --strict` clean. There is no prior baseline — Phase 1 starts from an empty package, so "green" at Phase 1 means "the two smoke tests pass, nothing else exists yet."

## Rules that apply to every task (from `CONSTITUTION.md`)

1. **No module under `tna_lab/` may import `ragas` or `deepeval`, or construct a model client** (Article I, Article IV). `tests/test_article_i_boundary.py` enforces the first half by import graph; the second half has no automated check beyond code review, since there is only one place (`runs.py`'s default `evaluate_fn`) where a judge is ever reached, and it reaches trust-no-agent's own `evaluate()`, not a client.
2. **No provider abstraction of any kind** — no `provider=` parameter, no second `JUDGE_MODEL`-shaped environment variable, anywhere in this feature (Article IV). `run()`'s `judge` parameter accepts trust-no-agent's own `JudgeConfig` and nothing else.
3. **Every capability is reachable from the library with no server running, and the CLI calls the same function the library exposes — never a second implementation** (Article II). `test_cli.py`'s job is to prove this by asserting CLI output matches the equivalent library call's result for every story.
4. **Append-only, ever.** Re-ingesting an existing record id overwrites with byte-identical content only (never silently accepts different content under the same id without erroring — see T010). Freezing an existing tag is an error, not an overwrite (Article VIII, FR-007).
5. **Exact pins, Python 3.12 exactly** (Article VI). `pyproject.toml`'s `trust-no-agent` pin is exact, not a range.
6. **`mypy --strict` clean, `ruff` clean, at every GATE.** No per-module opt-out.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task).
- **[Story]**: US1–US4 from [spec.md](spec.md).

---

## Phase 1: Setup

**Purpose**: a package that imports and an empty CI gate to grow into.

- [ ] T001 Create `pyproject.toml`: project name `tna-lab`, `requires-python = "==3.12.*"`, dependency `trust-no-agent` pinned exactly to the version this session's `trust-no-agent` checkout reports (`1.1.0` as of 2026-09-28), dev dependencies `pytest`, `ruff`, `mypy`. Console script `tna-lab = "tna_lab.cli:main"`.
- [ ] T002 [P] Create `.python-version` (`3.12`) and `.gitignore` entries for `__pycache__/`, `.venv/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.tna-lab/` (a workspace directory created by running the tool should never be committed from a working checkout that isn't itself a test fixture).
- [ ] T003 [P] Create `tna_lab/__init__.py` with `__version__ = "0.1.0"` and no other content yet — the public exports land as each story's module does (T0xx below updates it additively).
- [ ] T004 Run `uv sync`. Confirm `uv run python -c "import tna_lab"` succeeds. Run GATE — expected: no tests collected yet, `ruff`/`mypy` clean on the one-line package.

**Checkpoint**: the package installs and imports. Nothing else works yet.

---

## Phase 2: Foundational (blocks every story)

**Purpose**: record identity and on-disk storage helpers — every other module depends on both (research R1, R4).

### Tests first

- [ ] T005 [P] Write `tests/test_records.py` for `tna_lab/records.py`:
  - two `DatasetRecord`s with identical field values (including `contexts` as a tuple built two different ways, e.g. from a list vs. a generator) produce the same `record_id`;
  - changing any one field (including `metadata`) changes the id;
  - `contexts=None` and `contexts=()` produce different ids — presence-vs-absence matters, an empty tuple is not the same as no contexts (mirrors trust-no-agent's own "empty is present" rule for `EvalRecord`);
  - `record_id` is a 64-character lowercase hex string (full sha256).
- [ ] T006 [P] Write `tests/test_storage.py` for `tna_lab/storage.py`:
  - `canonical_json` is independent of dict key order and produces the same bytes for equal structures;
  - `workspace_root(explicit=None)` defaults to `Path.cwd() / ".tna-lab"`; `workspace_root(explicit=some_path)` returns `some_path` unchanged;
  - `write_json`/`read_json` round-trip a dataclass-shaped dict exactly;
  - `write_json` refuses (raises) to overwrite an existing file with *different* content at the same path, and is a silent no-op when the content is byte-identical (rule 4 — this is the shared primitive both `datasets.py` and `snapshots.py` build on).

### Implementation

- [ ] T007 [P] Create `tna_lab/records.py`: frozen `@dataclass DatasetRecord(input, output, expected, contexts, metadata)` and `record_id(record) -> str` per data-model.md.
- [ ] T008 [P] Create `tna_lab/storage.py`: `canonical_json(obj) -> str`, `workspace_root(explicit: Path | None) -> Path`, `write_json(path, data)`, `read_json(path) -> dict`, each per T006's tests.
- [ ] T009 GATE. T005 and T006 must now be green.

**Checkpoint**: identity and storage are solid. Every story below builds on these two modules only.

---

## Phase 3: User Story 1 — Ingest (Priority: P1)

**Goal**: `tna-lab ingest records.jsonl --dataset <name>` loads records idempotently (spec Story 1, FR-001–FR-005).

### Tests first

- [ ] T010 [P] [US1] Write `tests/test_datasets.py` for `tna_lab/datasets.py`:
  - ingesting 5 records into a fresh dataset creates 5 record files and a `head.json` listing all 5 ids;
  - re-ingesting the identical 5 records reports `added=0, already_present=5`, and the dataset's record count is still 5 (SC-002);
  - ingesting a record missing `contexts` (present as `None`) succeeds — no field beyond the record's own identity is required (spec Edge Cases, FR-002/FR-003);
  - ingesting into an existing dataset with 3 new records and 2 already-present ones reports `added=3, already_present=2`.

### Implementation

- [ ] T011 [US1] Create `tna_lab/datasets.py`: `@dataclass IngestResult(added: int, already_present: int)` and `ingest(workspace, dataset, records) -> IngestResult`, using `records.py` and `storage.py` only.
- [ ] T012 [US1] Add `ingest` to `tna_lab/__init__.py`'s exports.
- [ ] T013 GATE. T010 must now be green.

**Checkpoint**: a developer can build a dataset. Nothing can be scored yet — that needs Stories 2 and 3.

---

## Phase 4: User Story 2 — Freeze a snapshot (Priority: P1)

**Goal**: `tna-lab freeze <dataset> <tag>` creates an immutable, reproducible snapshot (spec Story 2, FR-006–FR-010).

### Tests first

- [ ] T014 [P] [US2] Write `tests/test_snapshots.py` for `tna_lab/snapshots.py`:
  - freezing a 5-record dataset as `v1` produces a `SnapshotRef` with 5 `record_ids`, a `snapshot_id`, and a `frozen_at` timestamp;
  - ingesting more records afterward does not change what `resolve(workspace, "smoke@v1")` returns — re-reading it is byte-identical to the freeze-time content (SC-003);
  - freezing the same dataset twice under two different tags (`v1`, `v2`) produces two independently resolvable snapshots with different `snapshot_id`s, even when the record set is identical between the two freezes (research R2);
  - freezing under a tag that already exists for that dataset raises `ValueError` naming the existing tag — it does not overwrite (rule 4, FR-007);
  - `resolve(workspace, "smoke@does-not-exist")` raises `ValueError` naming the missing tag — it never falls back to HEAD (FR-009).

### Implementation

- [ ] T015 [US2] Create `tna_lab/snapshots.py`: frozen `@dataclass SnapshotRef(dataset, tag, snapshot_id, frozen_at, record_ids)`, `freeze(workspace, dataset, tag) -> SnapshotRef`, `resolve(workspace, ref: str) -> SnapshotRef` per data-model.md and research R2.
- [ ] T016 [US2] Add `freeze` to `tna_lab/__init__.py`'s exports.
- [ ] T017 GATE. T014 must now be green.

**Checkpoint**: a developer can produce something reproducible to run against. Story 3 needs this.

---

## Phase 5: User Story 3 — Run a snapshot through trust-no-agent (Priority: P1)

**Goal**: `tna-lab run <dataset>@<tag> --evaluator <id> [...]` scores every record via trust-no-agent, persisting every result unmodified (spec Story 3, FR-011–FR-018).

### Tests first

- [ ] T018 [P] [US3] Write `tests/test_runs.py` for `tna_lab/runs.py`, using a fake `evaluate_fn` (research R6) — **no import of `trustnoagent` in this file**:
  - a fake `evaluate_fn` that always returns a fixed `ok` result is called once per `(record, evaluator)` pair for a 3-record snapshot and 1 evaluator id — 3 calls total, and the run record's `results["<id>"]` has 3 entries keyed by record id;
  - a run against 2 evaluator ids produces a run record whose `results` has 2 top-level keys, each with all snapshot records (FR-016);
  - a fake `evaluate_fn` that returns `error`, `skipped`, and `invalid_output` results (one each, for three different records) — the run record persists all three, unmodified, and the run does not raise (FR-012, FR-017 — this is the load-bearing test for research R5's "never re-implement failure handling" decision);
  - the run record's `snapshot_id` matches the snapshot's exact identity, not just its `<dataset>@<tag>` name (FR-015);
  - `run()` called with no `judge` argument builds one via the injected `evaluate_fn`'s own default path — assert the fake receives *a* `JudgeConfig`-shaped object, not that any particular model is chosen (this feature doesn't choose one — Article IV);
  - `load_run(workspace, run_id)` returns a `RunRecord` equal to what `run()` returned.
- [ ] T019 [P] [US3] Write `tests/test_runs_integration.py`, marked to skip unless `trust-no-agent`'s own offline evidence is reachable (mirrors trust-no-agent's own live-vs-offline separation, Article III of *its* constitution) — this is the one place this feature's tests touch the real `trustnoagent.evaluators.evaluate`, to prove the default wiring (not the fake) actually works end to end. If no committed evidence resolves for the chosen record/evaluator pair, the test should assert on the *shape* of the `error` result (a cache-miss `error`, not an exception) rather than a specific score, so it does not require live credentials to pass.

### Implementation

- [ ] T020 [US3] Create `tna_lab/runs.py`: `EvaluateFn` type alias, frozen `@dataclass RunRecord(run_id, snapshot_id, snapshot_ref, evaluator_ids, judge_model, generator_model, created_at, results)`, `run(workspace, snapshot, evaluator_ids, judge=None, evaluate_fn=trustnoagent.evaluators.evaluate) -> RunRecord`, `load_run(workspace, run_id) -> RunRecord`. This is the one file in the package that imports `trustnoagent` (as the default value only — T018's tests never trigger that default).
- [ ] T021 [US3] Add `run` and `load_run` to `tna_lab/__init__.py`'s exports.
- [ ] T022 GATE. T018 must now be green; T019 passes or skips per its own guard, never errors.

**Checkpoint**: a developer can produce two runs to compare. Story 4 needs this.

---

## Phase 6: User Story 4 — Compare two runs (Priority: P1)

**Goal**: `tna-lab compare <run_a> <run_b> --evaluator <id>` produces a structured, per-record diff (spec Story 4, FR-019–FR-025).

### Tests first

- [ ] T023 [P] [US4] Write `tests/test_compare.py` for `tna_lab/compare.py`, building `RunRecord` fixtures directly (no `evaluate_fn`, no `trustnoagent` import needed):
  - two runs against the same snapshot, same evaluator, scores `[0.5, 0.8, 0.5]` vs. `[0.7, 0.8, 0.3]` → record 1 `improved` (delta `+0.2`), record 2 `unchanged` (delta `0.0`), record 3 `regressed` (delta `-0.2`); summary counts `1/1/1` and a correct `mean_score_delta` (research R7);
  - the same shape for a `labels`-based evaluator with an ordered pass/fail set: `["pass","fail","pass"]` vs. `["pass","pass","pass"]` → record 2 `improved` (`"fail" → "pass"`), others `unchanged`; summary's `pass_rate_delta` set, `mean_score_delta` is `None`;
  - a record whose status differs between the two runs (`ok` in one, `invalid_output` in the other) reports `status_changed=True` regardless of what the score/label fields say (FR-023);
  - comparing a run to itself: every record `unchanged`, zero delta, summary `improved=0, regressed=0`;
  - two runs with different `snapshot_id`s raise `ValueError` naming the mismatch (FR-021);
  - a run missing results for the requested `evaluator_id` raises `ValueError` naming it (FR-021).

### Implementation

- [ ] T024 [US4] Create `tna_lab/compare.py`: frozen `@dataclass`es `RecordDelta`, `ComparisonSummary`, `Comparison`, and `compare(run_a, run_b, evaluator_id) -> Comparison` per data-model.md and research R7. No import of `trustnoagent` — everything it needs is already plain data on the two `RunRecord`s.
- [ ] T025 [US4] Add `compare` to `tna_lab/__init__.py`'s exports.
- [ ] T026 GATE. T023 must now be green.

**Checkpoint**: all four library primitives exist and are tested independently. The CLI (Phase 7) is the only thing standing between this and the quickstart.

---

## Phase 7: CLI

**Purpose**: `tna-lab` on the command line, mirroring the library exactly (Article II).

### Tests first

- [ ] T027 [P] Write `tests/test_cli.py`, invoking `tna_lab.cli.main` with `argv` directly (no subprocess needed) against a `tmp_path` workspace:
  - `ingest`, `freeze`, `run` (with a monkeypatched `evaluate_fn` — the CLI must expose a way to reach the same test seam T018 used, or the test uses `trust-no-agent`'s own offline error-result path exactly as T019 does), and `compare` each produce a result identical to the equivalent library call, for every story's happy path and at least one error path (an unknown snapshot tag, a mismatched comparison);
  - every subcommand accepts `--workspace <path>` and none reads an environment variable for it (research R4).

### Implementation

- [ ] T028 Create `tna_lab/cli.py`: one `argparse` parser, four subcommands (`ingest`, `freeze`, `run`, `compare`), each parsing arguments and calling the matching library function — no logic beyond argument parsing and result formatting lives here (Article II's "route handler" prohibition, applied to a CLI instead of a web framework).
- [ ] T029 GATE. T027 must now be green.

**Checkpoint**: the quickstart's CLI walkthrough works end to end (modulo a real `JUDGE_MODEL`/`GENERATOR_MODEL` and, for live evaluators, `NVIDIA_API_KEY`).

---

## Phase 8: Boundary enforcement and packaging

**Purpose**: the constitution's import-boundary rule becomes a real, checked test, and the package is CI-ready.

- [ ] T030 [P] Write `tests/test_article_i_boundary.py`: walk every `.py` file under `tna_lab/`, parse its imports, and assert none imports `ragas` or `deepeval`, directly or via `import ragas.<anything>` (rule 1). This test must pass by construction, since no task above ever imports either — it exists so a *future* change that violates Article I fails CI, not code review.
- [ ] T031 [P] Create `.github/workflows/ci.yml`: `uv sync`, then `uv run pytest`, `uv run ruff check .`, `uv run mypy .`, on push and pull_request — mirroring trust-no-agent's own default-offline CI job in spirit (no live credentials in this job's environment at all, since nothing in this feature's default test path needs one).
- [ ] T032 Final GATE: `uv run pytest && uv run ruff check . && uv run mypy .`. Then run the full [quickstart.md](quickstart.md) by hand once, end to end, with real `JUDGE_MODEL`/`GENERATOR_MODEL` values, to confirm the default `evaluate_fn` wiring (not just the fake) actually reaches trust-no-agent.

**Checkpoint**: v0.1.0 is feature-complete for spec 001. Tag and release are a separate, later decision — not part of this task list.
