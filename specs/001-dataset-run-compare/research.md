# Research: Dataset, Run, Compare

**Feature**: [spec.md](spec.md)

Unlike trust-no-agent's research phase, there is no existing library behavior to verify by execution — this repo has no code yet. What follows is a design-decision log: each choice, why it was made, and what it costs. Cite `docs/research/landscape-2026-09-28.md` (§R-cite) where the market-landscape research bears on the choice.

## R1 — Record identity is content, not position

**Decision.** A dataset record's identity is `sha256(canonical_json({"input":…, "output":…, "expected":…, "contexts":[…], "metadata":{…}}))`, full hex digest. Ingestion order and source-file formatting never affect it.

**Why.** FR-003 requires re-ingesting an identical record to be a no-op. Content-addressing is the only way to make that check O(1) per record without loading the whole dataset and diffing — it mirrors trust-no-agent's own Article III cache-key discipline (`sha256(call_kind ‖ model_identity ‖ prompt_hash)`), which is a deliberate consistency choice, not a coincidence: both are "identity is derived from content, never from when or how it arrived."

**Rejected alternative.** A sequential/UUID id assigned at ingestion time. Rejected because it makes re-ingestion detection require a full-content scan of the existing dataset, and it makes two independently-ingested copies of the same record look like different records — which breaks FR-003 outright.

**Consequence — this is why `compare()` can only re-judge, never diff two output sets.** Because `output` is one of the hashed fields, an improved answer to the same question is not the same record with a new value; it is a different `record_id`, reachable only in a different snapshot. `compare()` requires both runs to carry the same `snapshot_id` and pairs records by that id (FR-021, R7), so what it compares is two *judgings* of one frozen set of input/output pairs — a different judge model, evaluator, or rubric. It cannot answer "same inputs, before and after my agent changed," which is the question a team actually wants. That is a deliberate v1 deferral, not an oversight: CONSTITUTION.md Article VIII (Second amendment, 2026-09-29) names it and sketches the two ways out — separate input identity from output so an output belongs to a run rather than to a record's identity, or teach `compare()` to pair by input identity across two snapshots instead of requiring one shared `snapshot_id`. Spec 002's natural scope.

## R2 — Snapshot identity is independent of its human-readable tag

**Decision.** `snapshot_id = sha256(canonical_json({"dataset": name, "record_ids": sorted(record_ids), "frozen_at": <ISO-8601 UTC timestamp with microsecond precision>, "nonce": <16 random hex chars>}))`. The human-readable `<dataset>@<tag>` is a pointer to this id, stored in `snapshots/<tag>.json`, never the id itself.

**Nonce, added during implementation.** The formula above originally had no `nonce` field — `frozen_at`'s microsecond precision was assumed sufficient on its own. `test_two_freezes_of_identical_content_have_different_snapshot_ids` (two `freeze()` calls back to back, same HEAD) made the real risk concrete: two freezes issued fast enough to land in the same microsecond tick would otherwise collide. `secrets.token_hex(8)` closes that regardless of clock resolution, at the cost of `snapshot_id` no longer being a pure function of dataset content and time — it was never meant to be reproducible across freezes anyway (FR-007: freezing is an event, not a derivation), so this doesn't give up anything the design needed.

**Why (FR-010).** A dataset can be deleted and a new, unrelated one created under the same name later. If snapshot identity were derived only from `(dataset name, tag)`, a run record referencing an old, deleted snapshot could resolve against a coincidentally-same-named new one — silently comparing two unrelated datasets in Story 4. Including `frozen_at` at microsecond precision makes every freeze event's id practically unique even when record content is identical across two freezes (Edge Cases: comparing a run to itself; freezing an empty dataset).

**Cost.** Freezing the same dataset twice in immediate succession with no intervening ingestion produces two snapshots with identical record sets but different ids — by design (FR-007's append-only rule: neither overwrites the other).

## R3 — Run identity is time-ordered, not content-derived

**Decision.** `run_id = "<compact ISO-8601 UTC timestamp>-<8 hex chars>"`, for example `20260928T063000Z-a1b2c3d4`.

**Why.** Unlike a record or a snapshot, a run's *content* (its results) is not what should determine whether two runs are "the same run" — running the identical evaluator against the identical snapshot twice must produce two distinct, independently comparable run records (Story 4's "compare a run to itself" edge case is about comparing one run's *record* to itself, not about deduplicating runs). A timestamp-prefixed id keeps runs sortable on disk and in listings for free, which a content hash would not.

## R4 — Workspace layout: one hidden directory, content-addressed within it

**Decision.**
```
.tna-lab/
├── datasets/<name>/records/<record_id>.json     one file per unique record
├── datasets/<name>/head.json                    {"record_ids": [...]}  current mutable set
├── datasets/<name>/snapshots/<tag>.json          {"tag", "snapshot_id", "frozen_at", "record_ids"}
├── runs/<run_id>.json                            snapshot ref, evaluator ids, judge summary, results
└── cache/<key>.json                              trust-no-agent's judge-call evidence (R6), its own format
```
The workspace root defaults to `.tna-lab/` under the current working directory and is overridable by a `workspace` parameter (library) or `--workspace` flag (CLI) — never an environment variable, to avoid ever looking like a second `JUDGE_MODEL`-shaped configuration surface (Article IV's discipline extends in spirit to this feature's own configuration, even though Article IV itself is only about the judge).

**Why.** This is deliberately the smallest thing that satisfies Article VIII: no external database (Constitution Article VI), one file per identity (mirrors trust-no-agent's own "one JSON file per key… so a cache refresh is a reviewable diff" — Article III), and every write is a plain file write with no partial-update hazard, since records and snapshots are append-only and a run record is written once, atomically, at the end of a run.

## R5 — `run()` never raises for a scoring failure, ever

**Decision.** `runs.run()` calls trust-no-agent's `evaluate()` once per `(record, evaluator)` pair and persists whatever `EvalResult` comes back — `ok`, `error`, `skipped`, or `invalid_output` — unmodified. It does not catch exceptions from `evaluate()` itself, because trust-no-agent's own contract already guarantees `evaluate()` does not raise for an evaluation-time failure (trust-no-agent spec FR-004); a `try/except` here would be dead code hiding a contract trust-no-agent already keeps.

**Why (FR-012, FR-017).** Re-implementing failure handling that trust-no-agent's own `evaluate()` already provides would be exactly the kind of duplicated logic Article I forbids in spirit — tna-lab's job is to persist and compare results, not to re-decide what counts as a failure.

## R6 — Testability without a real judge or a committed cache

**Decision.** `runs.run()` takes an optional `evaluate_fn` parameter, defaulting to `trustnoagent.evaluators.evaluate`. Tests inject a fake with the same signature; the CLI and the default library path never override it.

**Why.** tna-lab's own test suite has no access to trust-no-agent's committed judge-cache evidence (that evidence lives in the trust-no-agent repo, keyed to trust-no-agent's own golden records) and Article III's determinism budget is trust-no-agent's to keep, not tna-lab's to duplicate. An injectable scoring function lets `test_runs.py` exercise every status class (`ok`, `error`, `skipped`, `invalid_output`) deterministically and for $0.00, without either vendoring trust-no-agent's cache or making a live call.

**Why this is not a provider abstraction (and does not violate Article IV).** Article IV forbids abstracting *which model or provider* answers a judge call — a `provider=` parameter, a second env var, a client tna-lab constructs itself. `evaluate_fn` abstracts *which function scores a record*, for testing only; it carries no model selection, no credential, and the shipped default is always trust-no-agent's own `evaluate()` with configuration built exactly as `JudgeConfig.from_env()` would build it (FR-013). A caller who overrides it to something other than trust-no-agent's `evaluate()` has stepped outside Article I's contract, which is their choice to make in their own code, not a capability tna-lab is designed to encourage.

**Addendum — `run()` must supply a `cache_dir`, in every mode.** trust-no-agent's `evaluate(evaluator, record, judge, cache_dir)` needs a cache directory whether the judge is offline or live. Given none, it falls back to its own committed store, but only when its package sits inside a trust-no-agent repo checkout (`evals/cache/location.py`, `default_cache_dir`: a `.git` and `pyproject.toml` beside the installed package). An installed dependency never passes that check, so without a `cache_dir` every call returns an `error` result naming the missing directory, before mode or credentials are even consulted. A previous version of this addendum called `cache_dir` a fixture-replay detail that tna-lab didn't need, and treated `--live` as the fix. That was wrong: confirmed with a real `NVIDIA_API_KEY`, `--live` runs failed identically.

`cache_dir` is trust-no-agent's evidence store, and its purpose is caching and cost control, not fixture replay. Live mode goes through `read_or_call`: a hit is served from disk with no call, a miss calls the judge once and writes the entry. Offline mode goes through `read_or_raise`: a hit is served, a miss is a cache-miss `error` result and never a call.

**Decision.** `EvaluateFn` takes `cache_dir` as a fourth argument, matching `evaluate()`. `run()` takes `cache_dir: Path | None = None`, defaulting to `<workspace>/cache` (created if missing), and passes that one path to every call. One stable location per workspace means a repeated live call for the same record, evaluator and judge is served from disk rather than billed again, and an offline run can replay whatever that workspace already scored live. The CLI gets no `--cache-dir` flag: `--workspace` already moves the cache, so the CLI reaches every location the library can (Article II). `test_runs_integration.py` asserts an offline run over an empty workspace cache reports a cache miss, never the missing directory.

## R7 — Comparison deltas branch on output type, not on a single numeric assumption

**Decision.** `compare()` inspects each record's two results' output type. Score-producing evaluators get a numeric delta (`score_b - score_a`); label-producing evaluators get a transition string (`"pass" → "fail"`); a status change (e.g. `ok → invalid_output`) is reported as its own field regardless of output type, per FR-023.

**Scope.** Both branches diff two judgings of the *same* frozen record, per R1's consequence note above — never two different outputs for one input, which Article VIII defers to a later spec. A `Comparison`'s per-record rows therefore always pair a `record_id` with itself.

**Why (FR-020, FR-024).** Not every evaluator trust-no-agent ships produces a score — rubric judges with `labels` set produce a label, not a number (trust-no-agent's own `OutputType` literal is `"score" | "label" | "bool"`). A comparison that assumed numeric scores everywhere would either crash or silently misreport label-based evaluators — Article VIII names comparison as this feature's differentiator, and getting it wrong here is the sharpest possible way to fail at that.

**Addendum — where a status change fits in `classification`.** The spec left undefined how `classification` treats a `status_a != status_b` pair, since status isn't a score or a label. Implemented rule: moving into `"ok"` is `"improved"`, moving out of `"ok"` is `"regressed"`, and a change between two non-`"ok"` statuses is `"unchanged"` — `status_changed` still reports it, but `classification` doesn't rank one error kind over another. `RecordDelta` also gained `fingerprint_a`/`fingerprint_b` (not in the original data-model.md table) to satisfy FR-027 for comparisons, not only single runs; both are now documented in data-model.md.

## R8 — Data types stay framework-free, plain dataclasses, matching trust-no-agent's own contract style

**Decision.** `DatasetRecord`, `SnapshotRef`, `RunRecord`, and `Comparison` are frozen `dataclasses`, serialized to and from JSON with plain `dataclasses.asdict`/manual constructors — no `pydantic`, no ORM, no new dependency beyond `trust-no-agent` itself.

**Why.** trust-no-agent's own public contract types (`EvalRecord`, `EvalResult`, `EvaluatorInfo`) are frozen dataclasses, not pydantic models (`data-model.md`, trust-no-agent spec 001: "All public types are frozen dataclasses… No Ragas or DeepEval type appears in any field"). Matching that keeps tna-lab from introducing a second serialization convention for what is, in a run record, largely trust-no-agent's own result shape passed straight through (FR-014). It also keeps the dependency list for v0.1.0 as small as Article VI's reasoning argues for: one real dependency, `trust-no-agent`, plus the standard library.

## Landscape evidence cited by this plan

- **R1's content-addressing choice** is the same principle the market-landscape research found underlying trust-no-agent's own cache key, extended to this feature's dataset layer — not independently re-derived from a platform in the research, since none of the surveyed tools document a content-addressed dataset-record scheme (`docs/research/landscape-2026-09-28.md`, "Datasets decouple from traces" — every surveyed tool assigns an id at ingestion/promotion time, not a content hash).
- **R2's append-only, timestamp-keyed snapshot model** mirrors what LangSmith and Langfuse independently converged on (`docs/research/landscape-2026-09-28.md`, same section): "an append-only, timestamp-keyed history, not a git-like DAG with diffs or branches." tna-lab adopts the same shape deliberately, per Constitution Article VIII.
- **R7's per-row, per-status comparison shape** is the feature the research flagged as the category's actual gap: "none of the free-tier self-hostable tools… document [a compare primitive] as a first-class code-level API" (`docs/research/landscape-2026-09-28.md`, "Datasets decouple from traces… Comparison is a code-first primitive everywhere").
