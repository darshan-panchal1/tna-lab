# Feature Specification: Dataset, Run, Compare

**Feature Branch**: n/a (no branch hook is configured; the spec was written on `main`)

**Created**: 2026-09-28

**Status**: Draft

**Target release**: v0.1.0 (first working version)

**Input**: Constitution Article VIII (First amendment), locking the v1 slice to exactly three primitives: dataset (ingest, freeze, version), run (score a frozen snapshot through trust-no-agent), compare (structured per-row diff between two runs). Evidence: `docs/research/landscape-2026-09-28.md`.

## Context

tna-lab does not exist yet. This is its first feature, and by Article VIII's rule it is also its *only* feature for v0.1.0 — nothing here reaches into ingestion formats, a UI, or provider selection, because Article VIII places all of that out of scope for this spec by name.

The problem this spec solves: a developer already has `trust-no-agent` installed and already knows how to call `evaluate()` on one record. What evaporates the moment their script ends is *which* records were scored, *what config* scored them, and *whether the next run did better or worse* — exactly the bookkeeping the research found every mature platform in this category actually earns its reputation on, not on scoring math (`docs/research/landscape-2026-09-28.md`, "The minimal defensible slice"). This spec builds that bookkeeping and nothing more.

## User Scenarios & Testing *(mandatory)*

### User Story 1: Ingest records into a versioned dataset (Priority: P1)

A developer has a batch of records — the same shape trust-no-agent's `EvalRecord` already accepts: `input`, `output`, `expected`, `contexts`, `metadata`. They ingest the batch into a named local dataset. Ingesting the same records again is a no-op, not a duplicate.

**Why this priority**: Without a dataset to run against, there is nothing for the other two primitives to operate on. Everything else in this spec depends on this story existing first.

**Independent Test**: Ingest a batch of ten records into a fresh dataset named `smoke`. Confirm ten records exist. Ingest the identical batch again. Confirm the count is still ten, not twenty.

**Acceptance Scenarios**:

1. **Given** a JSONL file of records matching trust-no-agent's `EvalRecord` fields, **When** the developer runs `tna-lab ingest records.jsonl --dataset smoke`, **Then** a dataset named `smoke` exists locally with one entry per input record.
2. **Given** a dataset that already contains a record, **When** the identical record (byte-identical field values) is ingested again, **Then** no second copy is created and the dataset's record count is unchanged.
3. **Given** a record missing a field trust-no-agent's `EvalRecord` allows to be absent (for example, no `contexts`), **When** it is ingested, **Then** ingestion succeeds — Article I's contract already treats every field but the identity of the record itself as optional, and this feature adds no new required field.
4. **Given** the same ingestion, **When** performed via the library call instead of the CLI, **Then** the result is identical (Article II: no capability exists only in one surface).

---

### User Story 2: Freeze a named, immutable dataset snapshot (Priority: P1)

A developer's dataset keeps growing as they ingest more records. Before running an eval they want reproducible results against, they freeze the dataset's current state under a name. That name always resolves to exactly the same set of records, even after more records are ingested later.

**Why this priority**: A run must be reproducible (Article V: determinism), and a dataset that keeps changing underneath a run cannot be. Freezing is what makes "run" (Story 3) point at something stable. It ships alongside Story 1, not after it, because Story 3 cannot be tested without it.

**Independent Test**: Ingest five records, freeze the dataset as `v1`. Ingest five more records. Confirm `v1` still resolves to the original five, and the dataset's unversioned HEAD now has ten.

**Acceptance Scenarios**:

1. **Given** a dataset with records ingested, **When** the developer runs `tna-lab freeze smoke v1`, **Then** an immutable snapshot is created, timestamped, and addressable as `smoke@v1`.
2. **Given** a snapshot `smoke@v1`, **When** more records are ingested into `smoke` afterward, **Then** `smoke@v1` still resolves to exactly the records present at freeze time — no addition, removal, or reordering.
3. **Given** two freezes of the same dataset at different times, **When** each is inspected, **Then** each has its own timestamp and its own immutable record set, and both remain resolvable — freezing is append-only, per Article VIII: no earlier snapshot is overwritten or deleted by a later one.
4. **Given** a snapshot name that does not exist, **When** it is referenced by any other command, **Then** the command fails with an error naming the missing snapshot — never a silent fallback to HEAD.

---

### User Story 3: Run a frozen snapshot through trust-no-agent (Priority: P1)

A developer runs one or more named evaluators against a frozen dataset snapshot. Each record in the snapshot is scored by calling trust-no-agent's `evaluate()` — nothing else computes a score. The full set of results, plus the configuration that produced them, is persisted as one run record.

**Why this priority**: This is the story that actually produces something worth comparing. Stories 1 and 2 exist to feed it.

**Independent Test**: Run `tna-lab run smoke@v1 --evaluator tna.ragas.faithfulness` against a snapshot with cached judge evidence already available to trust-no-agent. Confirm a run record is written containing one `EvalResult` per snapshot record, the evaluator id and version, the judge fingerprint, and the snapshot's identity.

**Acceptance Scenarios**:

1. **Given** a frozen snapshot and one evaluator id, **When** the developer runs it, **Then** trust-no-agent's `evaluate()` is called once per record in the snapshot, and every returned `EvalResult` — including its status, score, fingerprint and token counts — is persisted unmodified (Article I: tna-lab does not recompute or reinterpret a score).
2. **Given** `JUDGE_MODEL` and `GENERATOR_MODEL` set in the environment, **When** a run executes, **Then** those values reach trust-no-agent's `JudgeConfig` exactly as `from_env()` would build it, with no interception, translation, or validation by tna-lab (Article IV).
3. **Given** more than one evaluator id passed to one run, **When** it completes, **Then** the run record separates results by evaluator — a comparison (Story 4) must be able to tell which evaluator produced which delta.
4. **Given** a run against a snapshot, **When** the run record is written, **Then** it names the exact snapshot (by its immutable identity, not the dataset's mutable name) it was run against, so a later comparison can verify two runs are comparable (Story 4, Acceptance Scenario 3).
5. **Given** a record for which `evaluate()` returns a non-`ok` status (`error`, `skipped`, `invalid_output`), **When** the run record is written, **Then** that result is persisted exactly as trust-no-agent returned it — never coerced to a score, never dropped from the run record.
6. **Given** the same run performed via the library and via the CLI, **When** compared, **Then** they produce identical run records (Article II).

---

### User Story 4: Compare two runs against the same snapshot (Priority: P1)

A developer has two run records — before and after some change to their agent — both against the same dataset snapshot. They compare the two and get back a structured, per-row diff: which records got better, which got worse, which are unchanged, and the aggregate movement.

**Why this priority**: This is the story the research identified as the actual differentiation opportunity — the free-tier self-hostable category exposes comparison only as a UI feature, not as a documented library primitive (`docs/research/landscape-2026-09-28.md`). It is P1, not P2, because a tool that only runs evals and never tells you whether the second run was better is not yet doing the job Article VIII commits this v1 slice to.

**Independent Test**: Produce two run records against the same snapshot, one with a deliberately worse score on at least one record. Compare them. Confirm the comparison names that record as a regression, with both scores shown, and confirms every unchanged record is reported as unchanged, not omitted.

**Acceptance Scenarios**:

1. **Given** two run records referencing the same snapshot identity and the same evaluator id, **When** compared, **Then** the result is a per-record list, each entry carrying both runs' status and score (or label) for that record and a computed delta.
2. **Given** a record whose score improved between the two runs, **When** the comparison is built, **Then** that record is flagged as an improvement, not just a nonzero delta buried in a list — Article VIII requires regressions and improvements to be named individually.
3. **Given** two run records that do *not* reference the same snapshot identity, **When** a comparison is attempted, **Then** it fails with an error naming the mismatch — comparing runs against different data is not this feature's job, and doing it silently would misrepresent what changed.
4. **Given** a record whose status changed between runs (for example, `ok` in one run and `invalid_output` in the other), **When** compared, **Then** the status transition itself is reported, not just a score delta with a missing value on one side.
5. **Given** a comparison, **When** it completes, **Then** an aggregate summary accompanies the per-record list: counts of improved, regressed, and unchanged records, and the pass-rate or mean-score delta if the evaluator's output type supports one.
6. **Given** the same comparison performed via the library and via the CLI, **When** compared, **Then** they produce identical results (Article II).

---

### Edge Cases

- **Re-ingesting a record with the same content but different field order or whitespace in a JSON value.** Identity is defined over the record's normalized field values (Article I's five fields plus metadata), not over the raw bytes of the input file. Two records with the same values in different textual form are the same record.
- **Freezing an empty dataset.** Allowed — it produces a snapshot with zero records, and a run against it produces a run record with zero results. This is a valid, if useless, state; the feature does not special-case it.
- **Running an evaluator id that trust-no-agent's listing does not recognize.** The run proceeds record-by-record and trust-no-agent's `evaluate()` returns its own `error` result naming the unknown id for every record (per trust-no-agent's own FR-017-class behavior) — tna-lab does not pre-validate the id itself, because that validation already exists one layer down and duplicating it risks the two checks disagreeing.
- **Comparing a run to itself.** Permitted. Every record reports zero delta and "unchanged" — a valid, if trivial, sanity check a developer might reasonably run.
- **A run record from an evaluator that produces labels, not scores (for example a rubric with allowed labels rather than a numeric range).** The comparison reports a label transition (`"pass" → "fail"`, etc.) rather than a numeric delta, and the aggregate summary's pass-rate figure — not a mean-score figure — applies.
- **Two runs against the same snapshot but different evaluator ids.** Comparable only if the developer explicitly says so is out of scope for this spec's default path: FR-021 requires the same evaluator id on both sides, and a mismatch is an error, not a silent cross-evaluator diff.
- **Snapshot identity versus dataset name collision.** A dataset can be deleted and a new one created under the same name later; snapshot identities are never reused across that boundary, so an old run record can never be silently compared against an unrelated new snapshot that happens to share a name (see FR-010).

## Requirements *(mandatory)*

### Functional Requirements

**Ingestion (Story 1)**

- **FR-001**: The library MUST expose one entry point to ingest a batch of records into a named dataset. The CLI MUST expose the same capability as `tna-lab ingest <file> --dataset <name>`.
- **FR-002**: An ingested record MUST accept exactly the fields trust-no-agent's `EvalRecord` accepts (`input`, `output`, `expected`, `contexts`, `metadata`), each optional except as trust-no-agent itself requires. This feature MUST NOT add a new required field.
- **FR-003**: Record identity MUST be computed from the normalized field values, not from ingestion order or source-file formatting. Re-ingesting an identical record MUST NOT create a duplicate entry in the dataset.
- **FR-004**: Ingesting into a dataset name that does not yet exist MUST create it. Ingesting into an existing dataset MUST add only records not already present by identity (FR-003).
- **FR-005**: Ingestion MUST require no network access, no credentials, and no judge/generator model configuration — nothing in this story calls trust-no-agent's `evaluate()`.

**Dataset versioning (Story 2)**

- **FR-006**: The library and CLI MUST support freezing a named dataset's current record set as an immutable, timestamped snapshot addressable as `<dataset>@<tag>`.
- **FR-007**: A frozen snapshot's record set MUST NOT change after later ingestion into the same dataset name. Snapshot history MUST be append-only: freezing never overwrites or deletes an earlier snapshot.
- **FR-008**: Two different tags freezing the same dataset at different times MUST each remain independently resolvable, each with its own timestamp.
- **FR-009**: Referencing a snapshot tag that does not exist, in any command that accepts one, MUST fail with an error naming the missing tag — never silently substituting the dataset's current (unfrozen) state.
- **FR-010**: A snapshot's identity MUST be derived from its content and freeze time, not solely from its human-readable `<dataset>@<tag>` name, so that a run record referencing a snapshot can be distinguished from a later, unrelated snapshot that happens to reuse the same dataset name after deletion and recreation.

**Run (Story 3)**

- **FR-011**: The library MUST expose one entry point to run one or more named evaluators against one frozen snapshot. The CLI MUST expose the same capability as `tna-lab run <dataset>@<tag> --evaluator <id> [--evaluator <id> ...]`.
- **FR-012**: A run MUST score every record in the referenced snapshot by calling trust-no-agent's `evaluate()` once per (record, evaluator) pair. This feature MUST NOT compute, adjust, or reinterpret any score — Article I applies without exception.
- **FR-013**: A run MUST build its `JudgeConfig` exactly as trust-no-agent's own `JudgeConfig.from_env()` would, reading `JUDGE_MODEL`, `GENERATOR_MODEL` and (live mode only) `NVIDIA_API_KEY`. This feature MUST NOT add a configuration path, parameter, or environment variable that duplicates or overrides those three (Article IV).
- **FR-014**: A run record MUST persist, for every (record, evaluator) pair scored: the full `EvalResult` returned by trust-no-agent, unmodified, including its status, score or label, judge fingerprint, token counts, and latency.
- **FR-015**: A run record MUST persist the exact snapshot identity (FR-010) it was run against, not merely the dataset's human-readable name.
- **FR-016**: A run against more than one evaluator id MUST keep each evaluator's results distinguishable within the run record — a later comparison (Story 4) MUST be able to select results by evaluator id.
- **FR-017**: A non-`ok` result from trust-no-agent (`error`, `skipped`, `invalid_output`) MUST be persisted in the run record exactly as returned. It MUST NOT be dropped, coerced to a numeric score, or silently excluded from the record count.
- **FR-018**: Running MUST require no credential beyond what trust-no-agent's own offline/live mode already requires for the evaluators requested (Article IV) — no additional credential is introduced by this feature.

**Compare (Story 4)**

- **FR-019**: The library MUST expose one entry point to compare two run records. The CLI MUST expose the same capability as `tna-lab compare <run_a> <run_b>`.
- **FR-020**: A comparison MUST produce a per-record list. Each entry MUST carry both runs' status and score (or label) for that record, plus a computed delta (numeric for score-producing evaluators, a transition for label-producing ones).
- **FR-021**: A comparison MUST require both runs to reference the same snapshot identity (FR-015) and the same evaluator id. A mismatch on either MUST fail with an error naming which one differs — this feature MUST NOT produce a comparison across different data or different evaluators silently.
- **FR-022**: A comparison MUST classify every record as improved, regressed, or unchanged, and MUST name records in the first two categories individually — a diff that only reports an aggregate number does not satisfy this requirement.
- **FR-023**: A comparison MUST report a status transition (for example `ok → invalid_output`) as such, distinct from and in addition to any score delta, when the two runs' statuses for a record differ.
- **FR-024**: A comparison MUST include an aggregate summary: counts of improved/regressed/unchanged records, and a pass-rate or mean-score delta appropriate to the evaluator's output type (`score`, `label`, or `bool`).
- **FR-025**: Comparing a run to itself MUST succeed, reporting every record unchanged with zero delta.

**Cross-cutting (Article II, V)**

- **FR-026**: Every capability in FR-001 through FR-025 MUST be reachable from the library with no server or UI process running, and MUST be reachable from the CLI producing identical results to the equivalent library call.
- **FR-027**: A run record MUST retain the judge fingerprint trust-no-agent attached to each result (Article V). A comparison built from two run records MUST surface both runs' fingerprints, not only their scores — Article V's "no lie by omission" rule applies to the comparison output, not only to storage.
- **FR-028**: No functional requirement in this spec may be satisfied by importing `ragas` or `deepeval` directly, or by constructing a model client directly, anywhere in `tna_lab/` (Articles I, IV).

### Key Entities

- **Dataset record**: One normalized unit with the same shape as trust-no-agent's `EvalRecord` (`input`, `output`, `expected`, `contexts`, `metadata`), plus a content-derived identity used for deduplication (FR-003).
- **Dataset**: A named, mutable collection of dataset records, growing only by ingestion (Story 1). Has no identity of its own beyond its name and its current record set.
- **Dataset snapshot**: An immutable, timestamped, content-addressed freeze of a dataset's record set at a point in time, addressable by a human-readable `<dataset>@<tag>` and carrying its own durable identity independent of that name (FR-010).
- **Run record**: The persisted outcome of scoring one dataset snapshot with one or more evaluators: the snapshot identity, the evaluator id(s), and one `EvalResult` (unmodified, as trust-no-agent returned it) per (record, evaluator) pair.
- **Comparison**: The structured outcome of diffing two run records that share a snapshot identity and evaluator id: a per-record list of status/score pairs and deltas, classified as improved/regressed/unchanged, plus an aggregate summary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can go from a JSONL file of records to a structured comparison of two runs in four commands or fewer (`ingest`, `freeze`, `run` ×2, `compare`) or the equivalent library calls, with zero server or UI process running at any point.
- **SC-002**: Re-ingesting an identical batch of records into the same dataset never changes its record count.
- **SC-003**: A snapshot's record set is provably unchanged by later ingestion — verified by freezing, ingesting more records, and re-reading the frozen snapshot to confirm byte-identical contents to what was frozen.
- **SC-004**: 100% of `EvalResult` fields trust-no-agent returns (status, score, label, fingerprint, token counts, latency) survive a full ingest → freeze → run → compare cycle unmodified in the run record.
- **SC-005**: Every non-`ok` result in a run (across `error`, `skipped`, `invalid_output`) appears in that run's record count — none are silently dropped, and comparing two runs containing them never crashes or coerces them to a score.
- **SC-006**: Comparing two runs against mismatched snapshots or mismatched evaluator ids fails with a named reason 100% of the time; it never silently produces a comparison.
- **SC-007**: Scoring one frozen snapshot twice under different judging (a different judge model, evaluator, or rubric) surfaces any resulting classification change per record in the comparison output, not merged into an aggregate figure that could hide it.
- **SC-008**: Every capability this spec defines is exercised by both a library-level test and a CLI-level test, and both produce identical results, for every user story.

## Assumptions

- **Audience.** The "user" here is a developer with `trust-no-agent` already installed, calling tna-lab as a library or a CLI — not yet a team wanting a shared dashboard (Article VIII explicitly defers that).
- **Storage.** Local, embedded, no external database required for this spec (Constitution Article VI). The exact on-disk layout (content-addressed JSONL, a manifest per snapshot, one file per run) is an implementation decision for `/plan`, not fixed by this spec — only the *properties* (append-only versioning, immutable snapshots, identity independent of human-readable names) are requirements here.
- **No trace or OTel ingestion.** Article VIII defers this explicitly; `ingest` in this spec means "load already-structured records," not "receive spans from an instrumented agent." That is a later, separate spec.
- **No dataset-to-dataset diff.** Only "a snapshot as of version X" is required (FR-009, FR-010), not a diff between two snapshots of the same dataset — the research found no prior art for this feature anywhere in the category, and Article VIII does not manufacture a requirement the evidence doesn't support.
- **Evaluator selection is by id, passed through.** This spec does not validate evaluator ids against trust-no-agent's registry before calling it — trust-no-agent's own `evaluate()` already returns a typed `error` for an unknown id, and re-validating here risks the two checks disagreeing (see Edge Cases).
- **Out of scope**: any trace/span ingestion format or OTel compatibility; a web UI of any kind; multi-tenant auth; a plugin system for evaluators; a diff view between two dataset versions (as opposed to a run comparison); cost ceilings beyond what trust-no-agent itself enforces; comparing runs against different snapshots or different evaluators without an explicit, separate future feature to do so deliberately.
- **Dependencies**: `trust-no-agent`, pinned as an ordinary dependency (Constitution Article VI); its `evaluate()` entry point, `JudgeConfig.from_env()`, and `EvalResult`/`EvalRecord` shapes exactly as they exist in trust-no-agent v1.1.0.
