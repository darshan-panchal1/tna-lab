<!--
SYNC IMPACT REPORT — First amendment, 2026-09-28
Ordinal step: Initial ratification (DRAFT) → First amendment. Under semver this step would
be MINOR — one article added, one existing rule strengthened with evidence; nothing removed,
nothing this repo's zero lines of code could regress.
Modified: Article IV gains a dated-evidence clause. The "no multi-provider abstraction" rule
  was a design preference on 2026-09-28's draft; it is now backed by primary-source evidence
  that every platform researched which built one has documented, still-open breakage from it,
  on exactly the shape of endpoint tna-lab depends on (an unlisted OpenAI-compatible model).
Added: Article VIII — The v1 Slice, locking the first three primitives (dataset, run,
  compare) as what a first version builds, naming the versioning model the category already
  converged on (append-only, timestamp-keyed snapshots — not a git-like diff/branch model),
  and stating explicitly that a trace/OTel ingestion format is a deferred decision, not a
  rejected one — the standard itself is unsettled (see the cited evidence).
Renumbered: former Article VIII (Process) → Article IX. No article's rule changed as a
  result of renumbering.
Evidence source: a dated deep-research pass, committed at
  docs/research/landscape-2026-09-28.md, covering Arize Phoenix, Langfuse, Helicone,
  TruLens, OpenLLMetry, Comet Opik, TensorZero, Braintrust, W&B Weave, LangSmith,
  Confident AI, Galileo and PromptLayer. Cited inline where it bears on a rule, the same
  convention trust-no-agent uses for docs/research/brief.md and docs/api-notes.md.
Unchanged on purpose: Articles 0, I, II, III, V, VI, VII — none needed evidence to be
  correct; they follow from what tna-lab has already decided not to be (Article X of
  trust-no-agent's own constitution), not from what the market currently does.

Prior report — Initial ratification (DRAFT), 2026-09-28
This is the founding version. No prior articles exist, no amendment history to report, no
recorded evidence to preserve or invalidate. Unlike trust-no-agent's constitution, nothing
below is backed by a measurement, a bisection, or a named enforcing test yet — the repo it
governs does not exist. Every "Enforced by" clause below says so explicitly: it names the
mechanism this repo commits to building, not one that exists today. Treat this file as a
proposal awaiting review, not a settled document — amend it before the first line of code
lands, not after.
-->

# CONSTITUTION — `tna-lab`

**Purpose.** This repository is the platform trust-no-agent's own Article X refuses to become: a self-hostable LLM evaluation and observability system — trace ingestion, dataset curation, offline and online evals, LLM-as-judge, experiment comparison — built *on top of* trust-no-agent rather than beside it. trust-no-agent proves one claim on camera; tna-lab is where that proof becomes a tool someone runs against their own agent, every day, on their own infrastructure.

**Audience.** A team that already has an agent in production and needs to know, continuously, whether a change made it better or worse — without sending their traces to a vendor.

**Relationship to trust-no-agent.** tna-lab does not compete with trust-no-agent; it consumes it. trust-no-agent answers "does this one record pass?" through its per-record evaluator contract (`evaluate()`, one `EvalRecord` in, one `EvalResult` out, `REGISTRY`/`INFOS` naming what's available). tna-lab answers "across a dataset, over time, did this get better?" — ingestion, storage, comparison, presentation. Neither question is the other's job.

These principles are non-negotiable during implementation. A convenient violation is still a violation.

---

## Article 0 — The Prime Contract

A stranger who has never seen this repo runs:

```
git clone <repo> && cd tna-lab && uv sync && uv run tna-lab init
```

On a cold machine, with no API key required until they deliberately configure a live judge, they get: a place to load a dataset of traces, an offline eval pass scored through trust-no-agent's per-record contract against the committed judge cache trust-no-agent already ships, and a comparison of two experiments — entirely on their own machine, with nothing leaving it unless they choose to.

**Article 0 outranks every article below it.** A principle that collides with the Prime Contract is amended in the open, never violated in silence.

---

## Article I — One Scorer, Never a Second One

**Rule.** trust-no-agent is the only thing in this system that computes a score. tna-lab never reimplements a metric, never wraps Ragas or DeepEval directly, and never scores a record by any path that does not end in a call to `trustnoagent.evaluators.evaluate()`.

- tna-lab depends on trust-no-agent as an ordinary installed package, pinned like any other dependency (Article VI). It is not vendored, forked, or partially copied in.
- A new metric belongs in trust-no-agent, as a new evaluator id, registered in *its* `REGISTRY`. tna-lab adds no scoring logic of its own — it adds storage, retrieval, and comparison of scores that already exist.
- What tna-lab *is* allowed to compute: aggregates over results trust-no-agent already returned — pass rates, score distributions, deltas between experiments. Aggregation is not scoring. A new way to combine existing `EvalResult`s stays in tna-lab; a new way to produce one does not.

**Forbidden.** Importing `ragas` or `deepeval` directly, anywhere in tna-lab. A local copy of a metric "just for now." A second judge-calling path that does not route through `JudgeConfig`.

**Enforced by (to be built alongside the first evaluator call).** A test over the import graph, in trust-no-agent's own style: the only modules that import `ragas` or `deepeval` are ones inside the `trust-no-agent` dependency itself, never inside `tna_lab/`.

---

## Article II — Library First, UI Optional, Never Required

**Rule.** Everything tna-lab does must be reachable from an installed library and a CLI with no server running. A web UI may exist, but nothing — not ingestion, not scoring, not comparison — requires it.

- `tna_lab` is importable and usable headless: load a dataset, run an eval pass, get results back as data, in a script with no process listening on a port.
- A CLI (`tna-lab ...`, one entry point, same discipline as trust-no-agent's Article I.a) covers the same ground for a terminal user.
- The web UI, if and when it exists, is a client of the library's own APIs — not a second implementation of ingestion or comparison logic living in route handlers. It renders what the library already computed; it does not compute anything the library can't.
- CI, tests, and the Prime Contract's cold-clone path never require the UI to be running.

**Forbidden.** Business logic that lives only in a route handler. A "you must use the dashboard for X" feature with no library equivalent. A required database migration step that only the UI can trigger.

---

## Article III — Self-Hosted Means Nothing Leaves Without Being Told To

**Rule.** tna-lab runs entirely on infrastructure the operator controls. No trace, no dataset row, no score is sent anywhere outside the process unless the operator explicitly configured that destination.

- No telemetry, no analytics, no "anonymous usage" phone-home, by default or otherwise. trust-no-agent's Article III.a (DeepEval's PostHog hazard) is inherited wholesale: any dependency that tries to call home gets opted out before it's ever imported, and that opt-out is asserted by a test, not assumed from a flag.
- The only outbound network calls are the ones the operator asked for: a live judge/generator call through NVIDIA NIM (Article IV), or a storage backend the operator configured themselves. Nothing else reaches a socket.
- License is permissive (MIT or Apache-2.0 — pick one before the first commit and don't revisit it casually). A self-hostable tool with a license that restricts self-hosting is a contradiction.

**Enforced by (to be built).** trust-no-agent's `no_network` socket-patch pattern, extended to tna-lab's own default test run.

---

## Article IV — One Judge Path, Inherited Not Reinvented

**Rule.** tna-lab does not choose a model provider. It asks trust-no-agent to, and trust-no-agent's rules (Article III, VI.a of *its* constitution) are binding here by inheritance, not by restatement.

- Judge and generator selection happens exactly where trust-no-agent already put it: `JUDGE_MODEL` and `GENERATOR_MODEL`, read through trust-no-agent's own accessors, routed to NVIDIA NIM. tna-lab never adds a second env var, a second provider client, or a config file that duplicates what `JudgeConfig.from_env()` already does.
- A live eval run needs `NVIDIA_API_KEY`, present because the operator set it, absent otherwise. tna-lab asserts its absence is safe on the default path exactly as trust-no-agent does on its own.
- **No multi-provider abstraction.** The instant tna-lab adds "pick your own judge provider" as a feature, it has rebuilt the thing trust-no-agent's Article X explicitly refuses to be, one layer up. If that feature is ever wanted, it is trust-no-agent's decision to make, not tna-lab's to route around.

**Forbidden.** A `provider=` parameter. A second `JUDGE_MODEL`-shaped env var under a different name. Constructing an NVIDIA client, or any other model client, directly inside `tna_lab/`.

**This is not an unexamined preference — every platform researched that built the thing this article forbids has documented, still-open breakage from it, on exactly the shape of endpoint tna-lab depends on.** *(First amendment, dated evidence, 2026-09-28.)* DeepEval's `OpenAIModel` performs a lookup against a hand-maintained model catalog and crashes outright on an unrecognized OpenAI-compatible model id — structurally the same situation as pointing a judge at an NVIDIA NIM endpoint (`docs/research/landscape-2026-09-28.md`, citing DeepEval issue #3133, open as of the research date). Langfuse's server-side "LLM Connections" abstraction shows the identical failure from a different angle: a user pointing an evaluator at an OpenAI-compatible endpoint behind a LiteLLM proxy hit a persistent, unresolved validation-step failure despite confirmed network reachability (Langfuse discussion #8689). Deferring to *someone else's* abstraction does not avoid this either — LiteLLM itself, which several of these tools lean on to be the universal provider layer, carries over 1,000 open issues including cross-provider parameter-leakage bugs, and Ragas' own LangChain-deferred approach still surfaces local-model failures traceable to that layer. **The lesson is not "build a better abstraction" — it is that interception of judge/generator configuration is where mature, well-resourced projects are still visibly bleeding, and the fix is not to intercept it at all.** This clause does not change the rule above; it is the reason the rule is not up for reconsideration when a "just one convenience flag" feature request eventually arrives.

---

## Article V — Determinism and Cost Stay Visible

**Rule.** An eval pass run through tna-lab is exactly as cheap to re-run and exactly as honest about cost as one run through trust-no-agent directly — the platform layer must not hide either property.

- Every cached `EvalResult` tna-lab stores keeps trust-no-agent's fingerprint (model, template version, decoding params, schema) intact. tna-lab may index and query by it; it may not strip it, average it away, or store a score without the configuration that produced it.
- A comparison view that shows "v2 is better than v1" without also showing which judge produced both numbers is a lie by omission. The judge fingerprint travels with every score tna-lab displays, not just every score tna-lab stores.
- Cost and token counts trust-no-agent's `EvalResult` carries are aggregated and shown, not dropped. A dashboard that shows pass rate but hides spend has rebuilt the exact hazard trust-no-agent's Article VIII exists to prevent.

---

## Article VI — Stack

Python, matching trust-no-agent's pinned version. **uv** for everything; `uv.lock` committed. **ruff** and **mypy --strict**, no per-module opt-outs. Exact pins, no ranges — trust-no-agent's Article IX reasoning applies unchanged: a package imported directly is pinned directly, never inherited transitively.

If a web UI is built (Article II), its backend is Python; the frontend framework is a separate, later decision and is not pre-committed here.

Storage is embedded/local by default (Article 0's cold clone must not require standing up a database). A pluggable backend for teams that want Postgres or similar is a reasonable later addition — it is not a requirement of the first working version.

---

## Article VII — Out of Scope

Deliberately absent, at least for a first version: multi-tenant auth/RBAC; a hosted/SaaS offering — this is a self-host tool, and if a hosted version ever exists it is a separate product, not a mode of this repo; a second metric-scoring engine of any kind (Article I); a plugin system for arbitrary third-party evaluators that bypass trust-no-agent's registry; realtime streaming ingestion — batch/pull ingestion is enough for a first version; anything that requires an operator to give tna-lab a credential trust-no-agent itself wouldn't need.

---

## Article VIII — The v1 Slice *(First amendment)*

**Rule.** A first version builds exactly three primitives — dataset, run, compare — and nothing else. This is not an incomplete first draft of a bigger plan; it is the deliberately smallest thing that is already more useful than calling `trustnoagent.evaluators.evaluate()` by hand, chosen because it is where the evidence says this category's durable value actually sits, not where its scoring math sits (`docs/research/landscape-2026-09-28.md`).

- **Dataset.** Normalize raw records into a local dataset and freeze named, immutable snapshots. **Versioning is append-only and timestamp-keyed** — every mutation creates a new version, a name or tag can point at one, and a run can pin to a specific version for reproducible re-runs later. This is not a git-like DAG with diffs or branches between versions, and it is not supposed to be: no platform surveyed built that either, which is either a category-wide gap nobody has needed yet or a feature nobody has justified — either way, tna-lab does not build it first.
- **Run.** Iterate a frozen snapshot, call trust-no-agent's `evaluate()` per Article I with `JUDGE_MODEL`/`GENERATOR_MODEL` passed through exactly as Article IV requires, and persist the result as a run record keyed to the dataset snapshot it scored.
- **Compare.** Given two run records against the same dataset snapshot, return a structured, per-row score-delta diff — regressions and improvements named individually, not just an aggregate that moved. This is the one primitive in this list with the least existing prior art among the free-tier self-hostable tools (Phoenix and Opik expose comparison only as a UI feature, not a documented SDK object) — building it well is where tna-lab adds something the free tier of this category does not yet have, not where it reimplements something already solved.

**Explicitly deferred, not rejected.**
- **A trace/span ingestion format.** The standard itself is unsettled: OpenTelemetry's GenAI semantic conventions carry no stable, tagged release, and Arize's competing OpenInference vocabulary has an open, unanswered question about its own relationship to that work. Committing tna-lab to either now would be picking a side in an argument neither party has finished having. If and when ingestion is built, the evidence points at Langfuse's posture — accept raw OTLP, branch on whichever attribute is present — over committing to one vocabulary as canonical (`docs/research/landscape-2026-09-28.md`).
- **A shared or hosted view of results.** Every platform surveyed that started library-first eventually grew a server component. *When* users of a local-first tool outgrow that model is a real question this research could not answer — nothing in the evidence says how quickly. That transition is a future, deliberate decision, made once the dataset/run/compare core has actually proven itself, not pulled forward into v1 on the same instinct that produced the provider-abstraction hazard Article IV documents.
- Everything Article VII already places out of scope remains out of scope; this article does not reopen it.

**Enforced by (to be built).** A spec for anything beyond dataset/run/compare cites which of these two deferred items it is un-deferring, and why, the same discipline Article II.c of trust-no-agent's constitution required of its own scope expansion.

---

## Article IX — Process

Built with Claude Code, Spec-Driven Development, the same approach used for trust-no-agent and pr-mci-checker: constitution first, then specs, then tasks, then implementation — each amendable in the open when reality disagrees with the plan.

**This document was the proposal; it is now the working constitution.** Spec Kit's `/specify` step targets Article VIII's v1 slice. A future amendment is still open at any time — it is amended in the open, per Article 0, not violated in silence.
