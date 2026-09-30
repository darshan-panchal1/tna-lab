# Feature Specification: Compare Outputs by Case

**Feature Branch**: n/a (no branch hook is configured; the spec was written on `main`)

**Created**: 2026-09-30

**Status**: Draft

**Target release**: v0.2.0

**Input**: Constitution Article VIII (Second amendment), which deferred comparing two different sets of outputs for the same inputs, and [research.md](research.md) (R1–R8), which chose how to build it. Evidence: trust-no-agent's own case model (`evals/golden/schema.py`, `evals/adapters/ragas_adapter.py`), and `docs/research/landscape-2026-09-28.md`, "Datasets decouple from traces".

## Context

v0.1.0 compares two runs of *one frozen snapshot*. Because a record's identity is a hash over all five of its fields, `output` included (spec 001 research R1), an improved answer to the same question is a different record in a different snapshot. So v0.1.0 can tell a developer whether a *judge* change moved their scores, and it cannot tell them whether their *agent* got better. That second question is the one a team most wants answered. Article VIII's Second amendment named it as deferred, and its "Enforced by" clause requires the spec that takes it up to say so. This is that spec, and it un-defers that one item only: trace/OTel ingestion and a hosted view remain deferred.

The approach is research.md's: add a second comparison beside the first, rather than changing the first. Two runs are paired by **case**, meaning the same `input` and the same `expected`, across two different snapshots, possibly of two different datasets. Every spec 001 guarantee stays as it is: record identity, snapshots, run records and `compare()` itself, including its same-snapshot requirement (spec 001 FR-021). What this spec adds is a sibling comparison with a deliberately different, weaker matching guarantee, plus the reporting needed to make that weaker guarantee safe: every case that could not be paired is accounted for by name, and a comparison across different judges is refused.

The two comparisons, side by side:

| | `compare` (spec 001) | `compare-cases` (this spec) |
|---|---|---|
| Question answered | Did the *judging* change the scores? | Did the *outputs* get better? |
| Held fixed | The records (one shared snapshot) | The judge (same judge and generator model) |
| Free to differ | Judge model, evaluator config | Outputs, contexts, snapshot, dataset |
| Pairs records by | `record_id`, identical content | Case identity, the same `input` + `expected` |
| Unpaired records | Impossible by construction | Expected, and listed individually |

## User Scenarios & Testing *(mandatory)*

### User Story 1: Compare two output sets for the same test cases (Priority: P1)

A developer has baseline outputs from version 1 of their agent and new outputs from version 2, for the same questions. They ingest each set into its own dataset, freeze each, and score both runs with the same evaluator and judge. They then compare the two runs by case and get back a per-case diff: which cases got better, which got worse, which are unchanged, and the aggregate movement.

**Why this priority**: This is the whole feature. It is the capability Article VIII deferred, and without it the other two stories have nothing to report on.

**Independent Test**: Ingest three records into dataset `agent-v1` and freeze it as `agent-v1@base`. Ingest into `agent-v2` three records with the same `input` and `expected` but different outputs, one of them deliberately worse, and freeze it as `agent-v2@base`. Run both under the same judge and evaluator. Compare by case. Confirm all three cases pair, the worse one is named individually as regressed with both scores shown, and the other two appear as improved or unchanged rather than omitted.

**Acceptance Scenarios**:

1. **Given** two runs that scored different snapshots (of different datasets) containing records with the same `input` and `expected`, **When** compared by case with the same evaluator id, **Then** each such pair is reported as one case entry carrying both records' ids, both statuses, and both scores (or labels) with a computed delta.
2. **Given** a case whose score improved between the two runs, **When** the comparison is built, **Then** that case is classified `improved` and named individually, by the same rules spec 001's `compare()` uses (spec 001 FR-022). The two comparison paths never disagree about what "improved" means.
3. **Given** a paired case whose two records differ in `contexts`, as when a retriever changed between agent versions, **When** compared, **Then** the case is still paired, still classified, and still counted in the aggregate, and it carries `contexts_changed: true`. The flag is how a caller decides what to trust. Being excluded is never how the difference shows up.
4. **Given** a case whose status changed between runs (for example `ok` in one, `invalid_output` in the other), **When** compared, **Then** the status transition is reported as such, in addition to any score delta (spec 001 FR-023).
5. **Given** a comparison, **When** it completes, **Then** an aggregate summary accompanies the per-case list: counts of improved, regressed and unchanged cases among the paired ones, and a mean-score or pass-rate delta over all paired cases where the evaluator's output type supports one.
6. **Given** the same comparison performed via the library and via the CLI, **When** compared, **Then** they produce identical results (Article II).

---

### User Story 2: Account for every case that could not be compared (Priority: P1)

Output sets evolve. Cases get added, dropped, or have their reference answer corrected, so two runs rarely cover exactly the same cases. The developer needs the comparison to say exactly which cases it could not pair and why, so that a headline of "5 improved, 0 regressed" can never quietly mean "5 improved, and 40 were not looked at".

**Why this priority**: The weaker matching guarantee is what makes this feature possible, and this reporting is what makes that guarantee safe. A comparison that paired what it could and dropped the rest silently would be precisely the "lie by omission" Article V forbids. It ships with Story 1, not after it.

**Independent Test**: Run A covers cases {1, 2, 3}. Run B covers cases {2, 3, 4}, plus a second record for case 3 with a different output. Compare by case. Confirm that case 2 is paired; case 1 is listed as unmatched on side A; case 4 as unmatched on side B; case 3 as ambiguous, with its one record id from A and both from B, and no delta computed; and that the counts reconcile exactly to the number of records each run scored.

**Acceptance Scenarios**:

1. **Given** a record in run A whose case identity matches no record in run B, **When** compared, **Then** it is listed in `unmatched_a` with its record id, its case id, the reason `no_counterpart`, and its own result's status, score or label, and fingerprint. The same applies symmetrically to run B.
2. **Given** a case identity carried by more than one record within either run, **When** compared, **Then** that case is listed once in `ambiguous`, naming every record id carrying it on each side, and no pair and no delta is produced for it. The comparison never picks one.
3. **Given** a record whose `input` is absent, **When** compared, **Then** it has no case identity and is listed as unmatched on its side with the reason `no_input` and a case id of none. It is never pooled with other input-less records into one shared case.
4. **Given** two runs with no case in common, **When** compared, **Then** the comparison succeeds with zero case entries, every scored record appears in an unmatched list, and the aggregate score figures are absent rather than zero. Zero overlap is a result, not an error.
5. **Given** any comparison, **When** it completes, **Then** every record each run scored for the evaluator appears in exactly one place: a case entry, its side's unmatched list, or an ambiguous entry.

---

### User Story 3: Refuse to compare across different judging (Priority: P1)

The developer runs version 1's outputs under one judge model and version 2's under another, by accident or on purpose. A score difference between them would mix two causes, an agent change and a judge change, with no way to separate them. The comparison refuses.

**Why this priority**: Attribution is the entire point of this comparison. Without this guard, the feature's headline number could credit the agent with the judge's variance, silently, which is the failure this project's restraint exists to prevent. Spec 001's `compare()` has the mirror-image guard (a snapshot mismatch is an error, spec 001 FR-021), and neither has an override.

**Independent Test**: Produce two runs of case-matched output sets, one with `JUDGE_MODEL=model-a` and one with `JUDGE_MODEL=model-b`. Compare by case. Confirm it fails with an error naming both judge models, and that no comparison is produced.

**Acceptance Scenarios**:

1. **Given** two runs whose recorded judge models differ, **When** compared by case, **Then** the comparison fails with an error naming both values, and nothing is produced.
2. **Given** two runs whose recorded generator models differ, **When** compared by case, **Then** the comparison fails the same way, naming both values.
3. **Given** a run that has no results for the requested evaluator id, **When** compared by case, **Then** the comparison fails with an error naming the evaluator id and the run that lacks it (the evaluator half of spec 001 FR-021).
4. **Given** any of these errors, **When** the developer looks for a way past it, **Then** there is none: no parameter, flag or environment variable relaxes the check. Both run records remain readable directly (`load_run`, or the run files) for anyone who wants to inspect them by hand.

---

### Edge Cases

- **A case present in one run and absent from the other.** Listed individually in that side's unmatched list, with reason `no_counterpart`, its record id, case id, and its own result (FR-013). It contributes to neither side's improved, regressed or unchanged counts, and appears in the unmatched counts (FR-021).
- **A corrected reference answer.** `expected` is part of case identity (FR-001), so a case whose reference changed between the two output sets has a different case id on each side. Both records are listed as unmatched, one per side, and no delta is computed across two different yardsticks (research R2). The cost is that a reference correction removes that case from the comparison; it does so visibly, not silently.
- **Two output sets ingested into one dataset.** A dataset's current record set never shrinks (spec 001 data-model: "no delete operation exists"). Ingesting version 2's outputs into version 1's dataset and freezing it therefore captures both, and every case appears twice in the run. Each such case is listed as ambiguous and nothing is paired for it. That is the correct, loud outcome of the one-dataset-per-output-set workflow not being followed (research R7).
- **Whitespace or letter-case differences in `input` or `expected`.** Not normalized. `"What is X?"` and `"What is X? "` are different cases, and each is listed as unmatched on its side. Fuzzy matching would be a guess about equivalence, which FR-020 forbids (research R4: report, never guess).
- **`contexts` absent on one side and present-but-empty on the other.** These are different, as they are for record identity (spec 001 research R1), so `contexts_changed` is true.
- **`metadata` differs within a pair.** Neither flagged nor excluded. Metadata is never sent to a judge (trust-no-agent spec 001 data-model), so it cannot move a score, and it is where a user would naturally label the agent version that produced an output.
- **Comparing two runs of the same snapshot.** Permitted. Each record pairs with itself, so `output_changed` and `contexts_changed` are false throughout. This is valid but uninformative: spec 001's `compare()` is the tool for a same-snapshot comparison, and this feature does not redirect to it or refuse.
- **Comparing a run to itself.** Permitted. Every case is `unchanged` with zero delta, as with spec 001 FR-025.
- **A run whose scored records cannot be found in the given workspace.** For example, the run file was copied from another workspace without its dataset. This is an error naming the run and the record id (FR-010). It is never reported as unmatched, which would silently shrink the comparison to whatever happened to resolve.
- **An evaluator that produces labels, not scores.** Case deltas carry a label transition instead of a numeric delta, and the summary's pass-rate figure applies, by the same rules as spec 001's `compare()`.

## Requirements *(mandatory)*

### Functional Requirements

FR and SC numbers in this section are this spec's own. A requirement from spec 001 is always cited as "spec 001 FR-0xx".

**Case identity**

- **FR-001**: Two records MUST be treated as the same case if and only if their `input` values are equal and their `expected` values are equal, compared exactly. `output`, `contexts` and `metadata` MUST NOT be part of case identity (research R2).
- **FR-002**: Case identity MUST be derived from record content at comparison time and MUST NOT be stored: no new field on dataset records, no change to record identity, snapshot identity or the run record format, and no migration of any workspace created by v0.1.0 (research R1, R3).
- **FR-003**: A record whose `input` is absent MUST have no case identity and MUST NOT be paired with any record.

**Entry point**

- **FR-004**: The library MUST expose one entry point, `compare_cases(workspace, run_a, run_b, evaluator_id)`, returning a `CaseComparison`. It takes the workspace because a run record stores results keyed by record id but not the records' content, and case identity is computed from that content.
- **FR-005**: The CLI MUST expose the same capability as a separate subcommand, `tna-lab compare-cases <run_a> <run_b> --evaluator <id> [--workspace <path>] [--json]`. It MUST NOT be a flag or mode on `tna-lab compare`: the two carry different guarantees, and the weaker one must not be one option away from the stronger one under the same command name.
- **FR-006**: Spec 001's `compare()` and `tna-lab compare` MUST be unchanged in behavior, including the snapshot-mismatch error (spec 001 FR-021). There is one additive exception, which closes a v0.1.0 gap against Article V rather than adding to this feature: each `RecordDelta` also carries both runs' token counts, and `tna-lab compare` shows them. No existing field, error, classification or aggregate changes.
- **FR-007**: The two runs MUST NOT be required to share a snapshot identity, a snapshot tag, or a dataset.

**Preconditions (errors)**

- **FR-008**: Both runs MUST have results for `evaluator_id`. If either does not, the comparison MUST fail with an error naming the evaluator id and the run lacking it.
- **FR-009**: Both runs MUST carry the same judge model and the same generator model. If either differs, the comparison MUST fail with an error naming both values of whichever differs. No parameter, flag, environment variable or other mechanism MAY relax this check (Article V; research R6).
- **FR-010**: Every record a run scored for the evaluator MUST resolve to its content in the given workspace. If one does not, the comparison MUST fail with an error naming the run and the record id. A record that cannot be resolved MUST NOT be reported as unmatched.

**Pairing and the reported shape**

- **FR-011**: Every record each run scored for the evaluator MUST appear in exactly one of: a case entry (FR-015), that run's unmatched list (FR-013), or an ambiguous entry (FR-014).
- **FR-012**: A case MUST be paired if and only if its case identity is carried by exactly one record in run A and exactly one record in run B.
- **FR-013**: The comparison MUST carry two unmatched lists, `unmatched_a` and `unmatched_b`. Each entry MUST name, individually: the record id; the case id (absent when the reason is `no_input`); the reason, which is exactly one of `no_counterpart` (its case identity has no record in the other run) or `no_input` (FR-003); and that record's own result, meaning its status, its score or label, its judge fingerprint, and its token counts.
- **FR-014**: A case identity carried by more than one record within either run MUST be reported as exactly one ambiguous entry, naming its case id and every record id carrying it on each side (a side may name none). No pair and no delta MAY be produced for it.
- **FR-015**: Each paired case MUST be reported as a case entry carrying: the case id; both record ids; both runs' status; both scores or labels; the score delta or label transition; `status_changed`; the classification; both judge fingerprints; and both runs' token counts (`tokens_in`, `tokens_out`). Each field carries the meaning spec 001 gives it for a record (spec 001 FR-020, FR-023, FR-027), and the fields shared with `RecordDelta` are built by the same code (FR-016).
- **FR-016**: Classification (`improved`, `regressed`, `unchanged`) MUST follow exactly the rules spec 001's `compare()` uses, including its treatment of status changes and of the ordered pass/fail label set, so that the two comparison paths never classify the same pair of results differently.
- **FR-017**: Each case entry MUST carry `contexts_changed: bool`, true when the two records' `contexts` differ, with absent and empty treated as different. A case with `contexts_changed` true MUST still be paired, classified and counted in every aggregate.
- **FR-018**: Each case entry MUST carry `output_changed: bool`, true when the two records' `output` values differ, so that "unchanged because the agent gave the same answer" is distinguishable from "unchanged because a different answer scored the same".
- **FR-019**: A difference in `metadata` within a pair MUST be neither flagged nor used to exclude the pair.
- **FR-020**: Case matching MUST use exact equality. No whitespace trimming, case folding, or similarity matching.

**Summary**

- **FR-021**: The comparison MUST include a summary carrying: the number of paired cases; the improved, regressed and unchanged counts over paired cases; the number of paired cases with `contexts_changed` true; the number with `output_changed` true; the lengths of `unmatched_a` and `unmatched_b`; and the number of ambiguous entries.
- **FR-022**: The summary's mean-score or pass-rate delta MUST be computed over all paired cases, including those with `contexts_changed` true, by the same rules spec 001's `compare()` applies to its records (spec 001 FR-024). It MUST be absent, not zero, when no paired case supports one.
- **FR-023**: A comparison with zero paired cases MUST succeed, reporting its unmatched and ambiguous lists and a summary whose score figures are absent.

**Cross-cutting (Articles I, II, IV, V)**

- **FR-024**: Comparing by case MUST NOT call `evaluate()`, read judge configuration, need a credential, or touch the network. It reads two completed runs and the records they scored, and costs nothing (Articles I, IV, V).
- **FR-025**: Every capability in this spec MUST be reachable from the library with no server or UI running, and the CLI MUST produce identical results to the library call. `--json` MUST print the full `CaseComparison` (Article II).
- **FR-026**: The CLI's human-readable output MUST state its matching basis before any case row: that cases are matched by `input` + `expected` across snapshots, with no same-snapshot guarantee. A pasted `compare-cases` table can then never be mistaken for a `compare` table.
- **FR-027**: No requirement in this spec may be satisfied by importing `ragas` or `deepeval` or by constructing a model client anywhere in `tna_lab/` (Articles I, IV; spec 001 FR-028).

### Key Entities

Named as siblings of spec 001's `Comparison` / `RecordDelta` / `ComparisonSummary`, so the two comparison paths read as one family.

- **Case identity**: A value derived from a record's `input` and `expected`. It is computed, never stored, and absent for a record with no `input`. Many records, meaning different outputs over time, can share one.
- **CaseComparison**: The outcome of comparing two runs by case: both run ids, the evaluator id, the case entries, `unmatched_a`, `unmatched_b`, the ambiguous entries, and a summary. The sibling of `Comparison`.
- **CaseDelta**: One paired case (FR-015, FR-017, FR-018). The sibling of `RecordDelta`, carrying two record ids where `RecordDelta` carries one.
- **UnmatchedCase**: One record that could not be paired, with its reason and its own result (FR-013).
- **AmbiguousCase**: One case identity carried by more than one record within a run, with every record id on each side (FR-014).
- **CaseComparisonSummary**: The aggregate counts and score figures (FR-021, FR-022). The sibling of `ComparisonSummary`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can go from two JSONL files of outputs for the same cases to a per-case comparison in seven commands (`ingest` ×2, `freeze` ×2, `run` ×2, `compare-cases`) or the equivalent library calls, with no server or UI process running at any point.
- **SC-002**: For every comparison, on each side, the paired count plus that side's unmatched count plus the record ids that side contributes to ambiguous entries equals exactly the number of records that run scored for the evaluator, 100% of the time.
- **SC-003**: A case whose output was deliberately degraded in the second output set, scored under the same judge, is named individually as `regressed` in the comparison, with both scores shown, and is not merged into an aggregate that could hide it.
- **SC-004**: A case whose `contexts` changed between the two output sets but whose `input` and `expected` did not is paired, with `contexts_changed` true, 100% of the time. It is never reported as unmatched.
- **SC-005**: Comparing two runs with different judge or generator models fails with an error naming both values 100% of the time, and never produces a comparison.
- **SC-006**: Spec 001's full test suite passes unmodified, and a workspace created by v0.1.0 is readable and comparable by case with no migration.
- **SC-007**: Every user story is exercised by both a library-level test and a CLI-level test, and both produce identical results.

## Assumptions

- **Audience.** As spec 001: a developer calling tna-lab as a library or a CLI, with trust-no-agent installed.
- **Outputs are ingested, not produced.** tna-lab does not run the developer's agent. Each output set arrives as EvalRecord-shaped records, one per case, exactly as in v0.1.0 (research R1).
- **One dataset per output set.** The supported workflow ingests each output set into its own dataset. Two output sets in one dataset produce ambiguous cases rather than pairs (see Edge Cases; research R7). This spec adds nothing to ingestion or freezing to support another workflow.
- **One workspace.** Both runs and the records they scored live in the workspace passed to the comparison.
- **What a case is.** Case identity follows trust-no-agent's own model, in which a test case supplies the question and the reference answer while the agent produces the answer and the retrieved contexts (`evals/adapters/ragas_adapter.py`). Developers whose `contexts` are fixed fixtures rather than retrieval output get pairs with `contexts_changed` set wherever the fixtures differ (FR-017).
- **Out of scope**: storing case identity; fuzzy or normalized matching; comparing across different judge or generator models, or normalizing scores across judges; separating outputs from records so that an output belongs to a run (research R1, route A, which this spec keeps open rather than forecloses); running the developer's agent to produce outputs; any way to delete records or freeze a subset of a dataset; trace or OTel ingestion; a hosted or shared view; any change to spec 001's `compare()`.
- **Dependencies**: trust-no-agent v1.1.0, unchanged. Spec 001's record identity, snapshot model, run record format and `compare()` classification rules exactly as shipped in v0.1.0.
