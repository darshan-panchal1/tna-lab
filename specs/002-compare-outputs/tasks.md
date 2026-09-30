# Tasks: Compare Outputs by Case

**Input**: Design documents from `specs/002-compare-outputs/`: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/public-api.md](contracts/public-api.md), [quickstart.md](quickstart.md)

**Tests**: TDD, as in spec 001. In every phase, write the phase's tests first and watch them fail (red) before implementing.

**Gate**: every phase ends with **GATE**:

```bash
uv run pytest -q && uv run ruff check . && uv run mypy .
```

Expected: green, with `mypy --strict` clean. **Unlike spec 001, there is a baseline.** v0.1.0's suite (92 tests at spec approval, 36916ba) must stay green at every GATE, and `tests/test_compare.py`, `tests/test_runs.py` and `tests/test_snapshots.py` must pass *without edits*. A GATE that only passes because an existing test was changed is a failed GATE.

## Rules that apply to every task

1. **Spec 001 is frozen** (spec FR-002, FR-006). `record_id()`, `SnapshotRef`, `RunRecord`, `Comparison`, `ComparisonSummary`, the on-disk layout, and the behavior of `ingest`/`freeze`/`run`/`load_run`/`compare` do not change. **The one exception is T000**: it adds token-count fields to `RecordDelta` and a tokens column to `tna-lab compare`'s table. That closes a v0.1.0 Article V gap, is additive only, and changes no existing field, error, classification or aggregate. Changes to existing test files are additive only: new test functions, never edits to existing ones.
2. **`compare_cases()` needs the workspace, and must treat it as read-only.** Unlike `compare()`, which works from two `RunRecord`s alone, `compare_cases()` reads the record files each run scored, because a `RunRecord` stores results by `record_id` and not the records' `input`/`expected`. It reads them through `datasets.load_record()` only, which verifies each file's content hash (research R9). It creates, modifies and deletes nothing in the workspace (T020 asserts this).
3. **Case identity is computed, never stored** (research R3). `case_id()` is called inside a comparison and nowhere else. No field, file, cache entry or run-record key holds one.
4. **Report, never guess** (research R4; spec FR-014, FR-020). No fuzzy or normalized matching, and no picking one record out of an ambiguous case. Anything not paired lands in `unmatched_a`, `unmatched_b` or `ambiguous`, never nowhere.
5. **No judge, no network, no second scorer** (Articles I, III, IV; spec FR-024). `compare.py` imports no `trustnoagent`, as in spec 001. `compare_cases()` has no `evaluate_fn`, no `judge` parameter, and no override of any kind for the judge check (spec FR-009). No module under `tna_lab/` imports `ragas` or `deepeval`; `tests/test_article_i_boundary.py` already enforces this and needs no change.
6. **One classification implementation** (spec FR-016). `compare_cases()` calls the same private helpers in `compare.py` that `compare()` does. A second copy of the classification or pass-rate logic anywhere is a defect, even if it agrees today.
7. **The CLI calls the library and nothing else** (Article II). `tna-lab compare-cases` is `load_run` ×2 then `compare_cases`, plus formatting. `tna-lab compare` gains no flag, option or mode (spec FR-005).
8. **No test file for this feature imports `trustnoagent`.** Run records come from `run()` with a fake `evaluate_fn` (spec 001 research R6), or are built directly as `RunRecord` fixtures over records ingested for real, so that `load_record()` resolves them.
9. **`mypy --strict` clean, `ruff` clean, exact pins, Python 3.12**, at every GATE (Article VI).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task).
- **[Story]**: US1–US3 from [spec.md](spec.md).

---

## Phase 0: Close v0.1.0's Article V token-count gap

**Purpose**: Article V requires that the token counts trust-no-agent's `EvalResult` carries be "aggregated and shown, not dropped". v0.1.0's `RecordDelta` shows each side's judge fingerprint and neither side's token counts. That gap predates this spec. It is closed here, before implementation starts, so that `CaseDelta` (Phase 3) is born with the same cost-visibility fields as `RecordDelta` rather than copying an incomplete struct. One task, tests first, with its own GATE.

- [ ] T000 **Token counts on `RecordDelta`, shown by `tna-lab compare`.**
  - *Tests first*, as new functions only in `tests/test_compare.py` and `tests/test_cli.py`:
    - `RecordDelta` carries `tokens_in_a`, `tokens_in_b`, `tokens_out_a` and `tokens_out_b`, echoed from each run's `EvalResult` for that record, and `None` where the result has none (every non-`ok` result from trust-no-agent, and every existing `test_compare.py` fixture);
    - classification, deltas and the summary are unchanged by the new fields;
    - `tna-lab compare`'s table has a `tokens a → b` column showing `in/out` for each side, with `-` where a side has none, and `--json` carries the four fields.
  - *Implementation*: in `tna_lab/compare.py`, factor the fields any two paired results share (status, score, label, delta, transition, `status_changed`, classification, fingerprints, token counts) into one private builder that `RecordDelta` uses now and `CaseDelta` reuses in T008 (rule 6). Then add the column in `tna_lab/cli.py`'s comparison table.
  - *Guard*: every existing test passes **unmodified**, including `tests/test_compare.py`'s and `tests/test_cli.py`'s existing compare tests.
  - GATE.

**Checkpoint**: both comparisons will carry fingerprints *and* token counts on every pair. Aggregating token counts into a summary total is not part of this task (see plan.md, Article V).

---

## Phase 1: Setup

**Purpose**: confirm the baseline before anything changes. There is no scaffolding to create; the package, CI and tooling exist.

- [ ] T001 Confirm `main` is clean and GATE is green at the approved spec commit (or later docs-only commits). Record the passing test count. This is the number that must only grow from here.

**Checkpoint**: baseline recorded.

---

## Phase 2: Foundational (blocks every story)

**Purpose**: case identity and hash-verified record resolution. Every story depends on both.

### Tests first

- [ ] T002 [P] Add to `tests/test_records.py` (new functions only) for `records.case_id()`:
  - two records with equal `input` and `expected` have equal `case_id`, even when `output`, `contexts` (including `None` versus a tuple) and `metadata` all differ;
  - changing `expected` changes `case_id`, and `expected=None` differs from `expected=""`;
  - `input=None` returns `None`, whatever the other fields;
  - no normalization: `"What is X?"` and `"What is X? "` differ, and so do `"what is x?"` and `"What is X?"` (spec FR-020);
  - a `case_id` is a 64-character lowercase hex string, and never equals the same record's `record_id` (the two hash different payloads).
- [ ] T003 [P] Add to `tests/test_datasets.py` (new functions only) for `datasets.load_record()`:
  - it returns a `DatasetRecord` equal to the one ingested, `contexts` tuple and `metadata` included;
  - a missing record file raises `ValueError` naming the dataset and the record id;
  - a missing dataset directory raises the same way;
  - a record file whose content was edited after ingestion, so that it no longer hashes to its file name, raises `ValueError` naming the record id (research R9);
  - calling it creates no file or directory.

### Implementation

- [ ] T004 [P] Add `case_id(record) -> str | None` to `tna_lab/records.py`, beside `record_id()`, per data-model.md. Its docstring states that it is computed, never stored.
- [ ] T005 [P] Add `load_record(workspace, dataset, record_id) -> DatasetRecord` to `tna_lab/datasets.py`, per data-model.md and research R9: read-only, rebuilding `contexts` as a tuple, and verifying by recomputing `record_id()`.
- [ ] T006 GATE. T002 and T003 must now be green, with v0.1.0's tests untouched.

**Checkpoint**: a case can be identified and a scored record can be resolved and trusted.

---

## Phase 3: User Story 1 — Compare two output sets for the same cases (Priority: P1)

**Goal**: `compare_cases()` pairs two runs' records by case across two datasets and reports a per-case diff that classifies exactly as `compare()` does (spec FR-004, FR-007, FR-012, FR-015–FR-019, FR-021, FR-022).

### Tests first

- [ ] T007 [US1] Create `tests/test_compare_cases.py`, with fixtures that ingest and freeze two datasets (`agent-v1`, `agent-v2`) in `tmp_path` and produce run records with the same judge, either via `run()` with a fake `evaluate_fn` whose score depends on `record.output`, or directly as `RunRecord`s over the ingested ids. Cover:
  - three cases with equal `input`/`expected` in both datasets pair across the two snapshots: three `CaseDelta`s, each carrying both record ids, and the runs share no `snapshot_id` (spec FR-007);
  - scores `[0.5, 0.8, 0.5]` against `[0.7, 0.8, 0.3]` classify `improved`/`unchanged`/`regressed`, with deltas `+0.2`/`0.0`/`-0.2` (`pytest.approx`) and summary counts 1/1/1;
  - **classification parity** (spec FR-016): for several result pairs (score up, score down, equal, `ok → invalid_output`, `invalid_output → ok`, `error → skipped`, `fail → pass` labels, unordered labels), the `CaseDelta.classification` equals the `RecordDelta.classification` that `compare()` produces for the same two results;
  - `contexts_changed` is true when contexts differ, including `None` against `()`, and that case is still classified and still included in `mean_score_delta` (spec FR-017, FR-022), with the summary's `contexts_changed` count matching;
  - `output_changed` is true exactly when outputs differ, and when both runs scored the identical record, `record_id_a == record_id_b` and both flags are false (spec FR-018);
  - records differing only in `metadata` pair with no flag set (spec FR-019);
  - a status change is reported via `status_changed`, in addition to any delta;
  - a labels-based evaluator yields transitions and a `pass_rate_delta` over all paired cases, with `mean_score_delta` of `None`;
  - both fingerprints and all four token counts (`tokens_in_a`/`_b`, `tokens_out_a`/`_b`) appear on every `CaseDelta`, with the same values `RecordDelta` would carry for the same two results (Article V; T000);
  - comparing a run to itself gives every case `unchanged`, zero delta, and no flags.

### Implementation

- [ ] T008 [US1] Add the frozen dataclasses `CaseDelta`, `UnmatchedCase`, `AmbiguousCase`, `CaseComparisonSummary` and `CaseComparison` to `tna_lab/compare.py`, exactly per data-model.md, including the lists that stay empty until Phase 4. `CaseDelta` gets its shared fields, token counts included, from T000's builder, not from a second copy.
- [ ] T009 [US1] Generalize `compare.py`'s `_pass_rate_delta()` to take `(label_a, label_b)` pairs, so both comparisons share it, and keep `_classify()` shared as-is. `compare()`'s results must not move: `tests/test_compare.py` passes **unmodified**. This is the refactor's only guard, so run it before and after.
- [ ] T010 [US1] Implement `compare_cases(workspace, run_a, run_b, evaluator_id)` for the pairing path: resolve both runs' scored records via `load_record()` (the dataset is `snapshot_ref.partition("@")[0]`, research R9), group by `case_id()`, build a `CaseDelta` per case with exactly one record per side, and compute the summary with the shared helpers, ordering `cases` by `case_id`.
- [ ] T011 GATE. T007 must now be green, and `tests/test_compare.py` unmodified.

**Checkpoint**: two agent versions' outputs can be compared case by case. Anything unpaired is not yet reported, which Phase 4 closes before this feature is usable.

---

## Phase 4: User Story 2 — Account for every case that could not be compared (Priority: P1)

**Goal**: every scored record lands in exactly one of `cases`, its side's unmatched list, or an ambiguous entry, with the exact shape spec FR-011 to FR-014 and FR-023 define.

### Tests first

- [ ] T012 [US2] Add to `tests/test_compare_cases.py` the spec's Story 2 scenario: run A covers cases {1, 2, 3}, and run B covers {2, 3, 4} plus a second record for case 3 with a different output. Assert the exact shape:
  - case 2 is the only `CaseDelta`;
  - `unmatched_a` is exactly case 1, with its `record_id`, `case_id`, `reason="no_counterpart"`, and its own status, score, fingerprint and token counts;
  - `unmatched_b` is exactly case 4, likewise;
  - `ambiguous` is exactly one entry for case 3, with one id in `record_ids_a` and both ids in `record_ids_b`, sorted, and no delta computed anywhere for case 3;
  - the summary counts are `paired=1, unmatched_a=1, unmatched_b=1, ambiguous=1`.
- [ ] T013 [P] [US2] Add to `tests/test_compare_cases.py`:
  - a record with `input=None` lands in its side's unmatched list with `reason="no_input"` and `case_id=None`, and two such records on one side are two unmatched entries, never one ambiguous case (spec FR-003);
  - a case whose `expected` was corrected between the datasets is unmatched on *both* sides, `no_counterpart` each, with no delta;
  - whitespace-only and letter-case-only differences in `input` are unmatched on both sides (spec FR-020);
  - **two output sets in one dataset** (quickstart step 7): ingesting v2's file into v1's dataset and freezing it makes each shared case ambiguous;
  - **zero overlap**: two runs with no case in common return successfully, with `cases == ()`, every record in an unmatched list, and `mean_score_delta` and `pass_rate_delta` both `None`, not `0.0` (spec FR-023).
- [ ] T014 [P] [US2] Add a determinism test: the same two runs always yield an equal `CaseComparison`, and swapping `run_a`/`run_b` swaps the `_a`/`_b` fields (unmatched lists, record ids, `record_ids_a`/`_b`) while `cases` and `ambiguous` keep the same case ordering.
- [ ] T015 [US2] Add an **accounting-identity** test, parametrized over every run-pair fixture in `tests/test_compare_cases.py`: on each side, `paired + len(unmatched_side) + (record ids that side contributes to ambiguous)` equals the number of records that run scored for the evaluator, and no record id appears in two places (spec FR-011, SC-002).

### Implementation

- [ ] T016 [US2] Complete `compare_cases()`: an `AmbiguousCase` per case id carried by more than one record on either side; an `UnmatchedCase` (`no_counterpart` or `no_input`) for every other unpaired record, carrying its own result; the ordering per data-model.md; and the summary counts. A comparison with zero pairs returns normally.
- [ ] T017 GATE. T012–T015 must now be green.

**Checkpoint**: the comparison's weaker matching guarantee is fully accounted for. Nothing it could not pair is silent.

---

## Phase 5: User Story 3 — Refuse to compare across different judging (Priority: P1)

**Goal**: the three preconditions fail loudly, in the documented order, before any pairing, with no override. The comparison is read-only and makes no network call (spec FR-008–FR-010, FR-024).

### Tests first

- [ ] T018 [US3] Add to `tests/test_compare_cases.py`:
  - a run lacking results for `evaluator_id`, on either side, raises `ValueError` naming the evaluator id and that run (spec FR-008);
  - differing `judge_model` raises `ValueError` naming both models; differing `generator_model` does the same for both generator models (spec FR-009);
  - **no escape hatch**: `inspect.signature(compare_cases)` has exactly the parameters `workspace, run_a, run_b, evaluator_id`;
  - **error order**: runs with both a missing evaluator and a judge mismatch report the evaluator error; runs with both a judge mismatch and an unresolvable record report the judge error;
  - a scored record whose file was deleted raises `ValueError` naming the run and the record. It is **not** reported as unmatched (spec FR-010);
  - a scored record whose file was edited so its hash no longer matches raises the same way (research R9);
  - a run whose dataset directory is absent (a run file copied from another workspace) raises the same way.
- [ ] T019 [P] [US3] **No network** (Article III; spec FR-024): with `socket.socket` monkeypatched to raise on construction, `compare_cases()` over the Story 1 fixtures completes normally. This is the narrow Article III socket guard plan.md commits to: this feature's tests only, not the whole suite.
- [ ] T020 [P] [US3] **Read-only** (rule 2): snapshot every path, with its size and bytes, under the workspace before `compare_cases()`, and assert that the tree is identical afterwards, both for a successful comparison and for one that raises.

### Implementation

- [ ] T021 [US3] Add the preconditions to `compare_cases()` in the documented order (evaluator, then judge and generator, then resolution), all before pairing, with error messages naming what data-model.md says they name.
- [ ] T022 GATE. T018–T020 must now be green.

**Checkpoint**: the library feature is complete. A comparison either attributes a delta to the outputs under one fixed judge, or refuses.

---

## Phase 6: CLI

**Purpose**: `tna-lab compare-cases`, mirroring the library exactly (Article II), and impossible to mistake for `tna-lab compare` (spec FR-005, FR-026).

### Tests first

- [ ] T023 Add to `tests/test_cli.py` (new functions only), invoking `tna_lab.cli.main` with `argv` against a `tmp_path` workspace:
  - `compare-cases <a> <b> --evaluator <id> --json` prints JSON equal to `asdict(compare_cases(...))` for the same runs, unmatched and ambiguous lists included (spec FR-025);
  - the human output's **first line** is the matching-basis line from plan.md (spec FR-026), the case table has the same `tokens a → b` column T000 gives `compare`'s table, and the output contains the `unmatched in a (n):`, `unmatched in b (n):` and `ambiguous (n):` sections, each present with `(0)` when empty, plus a `summary:` line carrying every `CaseComparisonSummary` count;
  - error paths exit with status 1 and print `tna-lab: error: …` to stderr, with nothing on stdout: judge mismatch naming both models, missing evaluator, unknown run id, and an unresolvable record;
  - zero overlap exits with status 0;
  - `--workspace` is honored, and no environment variable is read for it (as spec 001's CLI tests assert);
  - **`compare` is untouched**: its subparser's option set is exactly what it was in v0.1.0, and `tna-lab compare` on two runs of different snapshots still fails naming the snapshot mismatch (spec FR-006).

### Implementation

- [ ] T024 Add the `compare-cases` subcommand to `tna_lab/cli.py`: `load_run` ×2, then `compare_cases`, then the human format from plan.md or `--json`. There is no logic beyond parsing and formatting, and the `compare` subparser gets no edits.
- [ ] T025 GATE. T023 must now be green.

**Checkpoint**: the feature is reachable from the terminal, and the two comparison commands cannot be confused.

---

## Phase 7: Exports, docs, version

- [ ] T026 [P] Export `compare_cases`, `CaseComparison`, `CaseDelta`, `CaseComparisonSummary`, `UnmatchedCase` and `AmbiguousCase` from `tna_lab/__init__.py`, keeping `__all__` sorted as it is today. Add an import test in `tests/test_compare_cases.py`.
- [ ] T027 [P] Update `README.md`: add `compare-cases` to the commands table, and add a short "Compare outputs by case" section, condensed from quickstart.md steps 1–4, with a one-line contrast between `compare` and `compare-cases`. Update the existing sample `compare` table to show T000's tokens column. Replace the "What v0.1.0 deliberately does not do" section, whose first paragraph becomes false with this feature, with what v0.2.0 does not do: trace/OTel ingestion, a hosted view, cross-judge comparison, fuzzy case matching. Keep every link an absolute GitHub URL, since this README is also the PyPI long description.
- [ ] T028 Bump the version to `0.2.0` in `pyproject.toml` and `tna_lab/__init__.py`, and run `uv lock` so `uv.lock`'s entry for the project matches. CI's `uv sync --frozen` would not catch a stale entry, but the next `uv lock --check` would. **Tagging and publishing are not part of this task list**: as for v0.1.0, the `v0.2.0` tag is a separate decision, and it publishes to PyPI with no approval step.
- [ ] T029 Final GATE, plus `uv build` and `twine check` on both artifacts, as was done for v0.1.0.

---

## Checkpoint: stop, and hand back

These two items need you. Implementation stops here until they are done.

- [ ] T030 **Article VIII amendment, your decision.** With v0.2.0 built, Article VIII's "Explicitly deferred, not rejected" list still names comparing two different sets of outputs for the same inputs as deferred, which is now false. Recording it as delivered is a constitution amendment (a Third amendment, in the SYNC IMPACT REPORT convention). Constitution changes are yours to approve, so this task drafts the amendment text for review and **does not commit it** until you approve.
- [ ] T031 **Manual quickstart, run by hand.** Walk [quickstart.md](quickstart.md) steps 1–7 end to end, with real `JUDGE_MODEL`, `GENERATOR_MODEL` and `NVIDIA_API_KEY`, in a fresh directory. Confirm each step's "Expected" against real output, especially step 4's scores and step 7's cache-served offline run. This is spec 001's T032 discipline: the tests use a fake `evaluate_fn`, and only this run proves the feature against real scores.

**Checkpoint**: v0.2.0 is feature-complete for spec 002. Tag and release follow only after T030 and T031, as a separate decision.
