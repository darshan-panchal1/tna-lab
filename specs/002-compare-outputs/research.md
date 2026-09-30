# Research: Compare Two Output Sets for the Same Inputs

**Feature**: spec 002, not yet written. This document is the research that precedes it. · **Un-defers**: the third item of CONSTITUTION.md Article VIII's "Explicitly deferred, not rejected" list (Second amendment, 2026-09-29) — comparing two different sets of outputs for the same inputs. Article VIII's "Enforced by" clause requires a spec beyond the v1 slice to name which deferred item it takes up; this is that item, and only that one. Trace/OTel ingestion and a hosted view stay deferred.

This is a design-decision log in the same shape as spec 001's research.md, with one difference: spec 001 designed on an empty repo, while this one designs against shipped code (v0.1.0, on PyPI) and against trust-no-agent's own source, both of which constrain the answer. Where a claim rests on code, it names the file. Where it rests on market evidence, it cites `docs/research/landscape-2026-09-28.md` by section. The brief for this research also named promptfoo; promptfoo is not in the committed landscape research, and nothing below relies on it.

The brief asked for a choice among three routes:

- **A.** Split record identity: output stops being part of what identifies a record.
- **B.** Cross-snapshot matching: `compare()` pairs records across two snapshots by input identity instead of requiring one shared `snapshot_id`.
- **C.** Keep `record_id` exactly as it is, add a weaker `case_id` over input + expected + contexts + metadata, and add a new comparison entry point that pairs by `case_id` across snapshots.

**Summary of the decision.** C's architecture, with its case key corrected. The key C proposed includes `contexts`, and trust-no-agent's own code treats `contexts` as agent output (R2). It also includes `metadata`, the field a user would label an agent version in (R2). Both would make exactly the comparison this feature exists for produce zero pairs. The corrected key is `input` + `expected`, derived at comparison time and never stored (R3). A pair's differences are reported rather than hidden (R4, R5), and the judge is held constant so a delta is attributable to the output (R6).

## R1 — Build it additively beside spec 001, not by changing record identity

**Decision.** Spec 001's model is untouched: `record_id` stays a hash over all five fields, snapshots still freeze sets of `record_id`s, and `compare()` keeps requiring one shared `snapshot_id` with records paired by `record_id` (FR-021). Output comparison is a separate, additive entry point that pairs the records two runs scored by a weaker *case identity* (R2), across two snapshots, which may belong to two different datasets.

**Why (Article VIII, Article II, v0.1.0 is published).** The two comparisons answer different questions, and each needs a different guarantee:

- *Same snapshot, different judging* — "did my judge change move my numbers?". This is spec 001's `compare()`. Its guarantee, identical content on both sides by construction, is what makes a delta attributable to the judging.
- *Same cases, different outputs* — "did my agent get better?". This is the new entry point. Its guarantee is that both sides are the same test case, with the output free to differ.

Merging them into one function with a mode switch would make FR-021's exact-content guarantee conditional on a flag, which is the weakening the brief itself warned against for B. Keeping them separate costs one more public function and nothing else. Every spec 001 test, stored record, snapshot and run stays valid, and a workspace created by v0.1.0 needs no migration.

**Why not A (split record identity).** A has the better long-term shape, and it is what the category and trust-no-agent itself both do (R8). It still loses on three counts:

1. **It breaks the published data format.** `record_id` is the content address of every record file and the member list of every snapshot. Removing `output` from it changes the meaning of every id already on disk in v0.1.0 users' workspaces. This is not a refactor, it is a storage migration, which Article VIII's append-only rule makes awkward by design.
2. **It needs a second ingestion surface.** Where a platform separates a dataset example from an experiment output, the experiment *produces* the output by running the user's task function over each example (`landscape-2026-09-28.md`, "Datasets decouple from traces": Phoenix's and Langfuse's `run_experiment()`, LangSmith's `evaluate()`). tna-lab has no task step. Outputs arrive already paired with their inputs in one EvalRecord-shaped JSONL line, which `trustnoagent.evaluators.evaluate()` consumes whole: it scores a complete record, output included. Under A, a run would need its outputs supplied separately and keyed back to cases, so users would split one file into two. Otherwise tna-lab would have to start running agents, a capability no article grants and Article VII's spirit of a narrow, non-generating tool argues against.
3. **It is not needed to get the capability.** R7 shows the case key C uses is the same identity A's dataset examples would carry, so C delivers the comparison now and forecloses nothing.

**Why not B as stated.** B, read literally, relaxes `compare()` itself: "instead of requiring one shared `snapshot_id`". That removes FR-021's guarantee from the path that depends on it, as above. B done additively is C. B also leaves the input identity unnamed and undefined, and defining it is the hard part (R2).

## R2 — The case key is `input` + `expected`; `contexts` and `metadata` are excluded

**Decision.** Two records are the same *case* if and only if their `input` and `expected` are equal:

`case_id = sha256(canonical_json({"input": …, "expected": …}))`

`output`, `contexts` and `metadata` are not part of it. Records with `input is None` have no case identity and are never paired (R4).

**Why include `expected`, and nothing else beside `input`.** Take the field semantics from the code that scores these records, not from the field names. trust-no-agent's own golden case (`evals/golden/schema.py`, `GoldenCase`) carries `question`, `ground_truth`, `reference_contexts` (filenames) and `category`, and **no output**. When trust-no-agent builds a scoring sample, `evals/adapters/ragas_adapter.py`'s `to_single_turn_sample` takes:

- `user_input` from the case's `question`, which becomes `EvalRecord.input`;
- `reference` from the case's `ground_truth`, which becomes `EvalRecord.expected`;
- `response` from the *agent's* `AgentResult.answer`, which becomes `EvalRecord.output`;
- `retrieved_contexts` from the *agent's* `AgentResult.retrieved_contexts`, which becomes `EvalRecord.contexts`.

`record_to_sample`, the per-record path tna-lab calls through, maps `EvalRecord` onto the same four sample fields and is documented as equal to that mapping field for field. So in the dependency tna-lab is bound to (Article I), a test case is input + expected, and output and contexts are both what the agent produced. The case key follows the dependency's own semantics rather than inventing a second opinion about them.

**Why not C's key (input + expected + contexts + metadata).**

- **`contexts` is agent output in RAG.** The retriever is part of the system under test, and improving it changes `contexts`. Under C's key, a version-2 agent that retrieves differently has a different `case_id` for every case where retrieval moved, so its best improvements would come back as "no matching case". This is not an edge case. `tna.ragas.faithfulness`, the evaluator the quickstart uses, scores an answer against exactly these contexts.
- **`metadata` is where a user labels the output.** An `{"agent_version": "v2"}` tag is the natural thing to put there, and it would give every case a different `case_id` from its baseline, so zero pairs. Metadata also cannot affect a score: trust-no-agent's data model says of `EvalRecord.metadata` that it is "never sent to a judge" (trust-no-agent `specs/001-per-record-evaluators/data-model.md`). A field that cannot move the score has no reason to decide which scores are compared.

**Why not `input` alone.** A corrected reference answer would then pair two scores measured against different yardsticks. That could only be flagged, and a flag is easy to read past. With `expected` in the key, a reference change *unpairs* the case: it appears in the unpaired lists on both sides (R4), visibly, and no delta is computed across two different references. That matches FR-021's rule that a comparison is never produced silently across different data, applied per case instead of per snapshot.

**Cost.** A typo fix in `expected` between two ingests means that case is not compared, and the user sees it listed as unpaired rather than scored. Some users treat `contexts` as fixed fixtures rather than retrieval output, and for them two records with different contexts will pair. R5 makes that visible on the pair. Neither cost is silent.

## R3 — Case identity is derived at comparison time, never stored

**Decision.** `case_id` is a pure function of a record, computed from the record files each run scored when the comparison runs. It is the same kind of object as `record_id(record)` today. It is not a field on `DatasetRecord`, not written into record files, and not persisted in run records. The new entry point therefore needs the workspace, unlike `compare()`, which works from two `RunRecord`s alone. A run's `snapshot_ref` names its dataset, and the dataset's record files hold the content.

**Why.**

- **No sixth field.** `DatasetRecord` is deliberately "The same five fields trust-no-agent's own `EvalRecord` accepts — this feature adds no sixth field" (spec 001 data-model.md). A stored `case_id` would be a sixth field, or a sidecar that must be kept consistent with the five.
- **The definition can change without stale data.** If `case_id` were stored, any later change to the key (R2 is a judgment call a future spec may revisit) would leave every stored id wrong, with nothing to detect it. Derived identity is recomputed from immutable content, so it is always current.
- **The inputs are immutable, so deriving is safe.** Record files are content-addressed and append-only. A snapshot's records can never change after freezing (spec 001 R2, SC-003), so a `case_id` computed today is the one that would have been computed at run time.

**Rejected alternative.** Persisting case ids into `RunRecord` at run time, so the comparison works from two run records alone the way `compare()` does. That is neater to call, but it freezes the R2 definition into every run file and adds a field to a persisted type for a value that is always recomputable.

## R4 — Pairing is exact, and anything it cannot pair is reported, never guessed

**Decision.** For each run, group the records it scored for the evaluator by `case_id`. The comparison then reports three things:

- **Paired cases**: a `case_id` present exactly once on each side. These are compared.
- **Unpaired cases**: present on one side only. These are listed individually per side, with their record ids.
- **Ambiguous cases**: a `case_id` carried by more than one record within one run. These are listed individually and never paired.

Records with `input is None` are reported as unpairable. They are not pooled under a shared hash of `None`, which would make them all look like one ambiguous case.

**Why (FR-021, FR-022; spec 001 R7's "report, don't hide").** FR-022 already requires every improved and regressed record to be named individually rather than folded into an aggregate. The same principle applies one level up: a case that could not be compared is also information, and a summary that silently dropped it would overstate coverage. Ambiguity is the dangerous case, since two records in run B for one case could be paired either way and a guess would fabricate a delta. Refusing to pair is the only choice that never reports a number trust-no-agent did not justify. Counts of paired, unpaired-A, unpaired-B and ambiguous belong in the summary, so partial coverage is visible at a glance.

**Why not an error.** Unlike a snapshot mismatch in spec 001, partial overlap is the normal case here: output sets evolve, and cases get added and dropped. Failing the whole comparison because one case is new would make the feature unusable. Reporting per case keeps FR-021's intent (nothing silent) without its all-or-nothing form.

## R5 — Within a pair, a changed `contexts` is reported, not used to refuse

**Decision.** A paired case can still differ in `contexts` (R2 excludes it from the key) and in `metadata`. Each pair carries `contexts_changed: bool`, and the summary counts pairs where it is true. A metadata difference is not flagged, because metadata never reaches a judge (R2). The per-pair fields spec 001's `RecordDelta` already carries are kept: status on each side, `status_changed`, score delta or label transition, classification, and both judge fingerprints (FR-023, FR-027, Article V).

**Why.** tna-lab cannot know whether a user's contexts are retrieved (agent output, as in trust-no-agent's own mapping) or fixed fixtures. Excluding them from the key and flagging when they differ is correct in both worlds:

- For retrieval, `contexts_changed` is simply part of what the new agent did differently.
- For fixtures, it warns that the two scores were grounded against different evidence.

Refusing such pairs would reintroduce R2's RAG failure. Hiding the difference would make the fixture case a silent confound. This is spec 001 R7's pattern (FR-023 reports a status change "distinct from and in addition to" the score delta) applied to one more field.

## R6 — Judging is held constant: a judge or evaluator mismatch is an error

**Decision.** Both runs must have scored the requested `evaluator_id` (as FR-021 already requires) *and* must carry the same `judge_model` and `generator_model` on their `RunRecord`s. A mismatch fails with an error naming both values. Per-result fingerprints are still surfaced on every pair (Article V), so a judge that drifted under an unchanged model name is visible even when the names match.

**Why.** The question this feature answers is attribution: did the *outputs* get better? If the judge changed too, every delta mixes two causes, with no way to separate them from the result. Spec 001's `compare()` exists precisely for the judge-changed, output-fixed case. This entry point is its mirror, output changed and judge fixed, and it keeps that fixed half as strictly as FR-021 keeps the snapshot fixed. A deliberate cross-judge, cross-output comparison changes two variables at once. If anyone needs it, it is an explicit opt-in for the spec to consider, not a default.

## R7 — One dataset (or one snapshot) per output set; ambiguity detection catches the mistake

**Decision.** The supported workflow is to ingest each output set into its own dataset (for example `support-agent-v1` and `support-agent-v2`), freeze each, run each under the same judge, and compare the two runs. Nothing new is built to support a different workflow.

**Why this is a real constraint, not a preference.** A dataset's HEAD "grows only by ingestion… Never shrinks in this spec — no delete operation exists" (spec 001 data-model.md). Ingesting version 2's outputs into the dataset that already holds version 1's means HEAD holds both. A freeze then captures both, and every case appears twice in the run: R4 reports it as ambiguous and pairs nothing. That is the loud, correct outcome. The alternative, a way to freeze a subset or replace records, would be a new capability of `freeze` or `ingest` that Article VIII's append-only model argues against, and that this feature does not need. The workflow constraint goes in spec 002's quickstart, and R4's ambiguity report is the guard rail.

**Forward compatibility with A.** The case key `input` + `expected` is, field for field, what trust-no-agent's `GoldenCase` supplies to a record (R2). It is also what a dataset example would be identified by if tna-lab ever adopts A's shape, where outputs belong to runs. If that happens, "pair by case" is unchanged: the cases just stop being recomputed from records and start being stored. Choosing C now therefore does not foreclose A. It is A's comparison semantics without A's migration.

## R8 — The rest of the stack is unaffected: no new scorer, no new judge path, no new cost

**Decision and why.** The new entry point makes no `evaluate()` call. It reads two completed runs and the record files they scored, so it adds no cost and no score of its own (Article I, Article V). trust-no-agent's evidence cache is keyed by the rendered prompt (`sha256(call_kind ‖ model_identity ‖ prompt_hash)`, spec 001 research R1), and the rendered prompt contains the output and contexts. Two output sets therefore already produce distinct cache entries, and nothing here changes caching. There is no provider parameter, no new environment variable, and no new configuration surface (Article IV). The CLI mirrors the library function exactly (Article II).

## Landscape evidence cited by this research

- **The category keys comparison per dataset example, with outputs belonging to the run.** Phoenix's and Langfuse's `run_experiment()` and LangSmith's `evaluate()` each run over a dataset and return "per-example and aggregate scores", and LangSmith's pairwise `evaluate()` takes "two existing experiments" and returns a per-run score mapping (`landscape-2026-09-28.md`, "Datasets decouple from traces"). Spec 001's research already notes that every surveyed tool "assigns an id at ingestion/promotion time, not a content hash", so an example's identity there is independent of any output by construction. That is route A's shape, and it confirms the target semantics R2 adopts: pair by test case, let outputs differ. It does not transfer as mechanism, because each of those tools *executes a task function* to produce the outputs it compares, and tna-lab has no such step (R1). So this research adopts the category's comparison semantics and not its data model.
- **Comparison stays code-first.** The same section records that experiment comparison is "universally code-first", and that among the free self-hostable tools Phoenix's flip detection between two runs is documented only as UI behavior. Adding output comparison as a library function with a mirroring CLI (R8) extends the gap spec 001 set out to fill, rather than reimplementing something solved.
- **Not covered by the committed evidence.** The brief named promptfoo, which the landscape research does not cover. No decision here rests on it. None of the surveyed tools' treatment of *retrieved* contexts is covered either. R2's handling of `contexts` rests entirely on trust-no-agent's own source, which is primary evidence for the one dependency this system is bound to (Article I), not on market practice.

## Left for spec.md

Decided here and not reopened by the spec: route (R1), case key (R2), derived identity (R3), report-not-guess pairing (R4), contexts flagged per pair (R5), judge held constant (R6), and workflow (R7).

Genuinely open for spec.md: the entry point's name and exact signature (it takes a workspace, per R3); whether a pass-rate or mean-score delta is computed over all paired cases or only over pairs with `contexts_changed` false; and whether R6's judge-mismatch error warrants an explicit opt-in override.
