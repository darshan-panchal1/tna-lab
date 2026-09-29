# Quickstart: Dataset, Run, Compare

**Feature**: [spec.md](spec.md) · **API**: [contracts/public-api.md](contracts/public-api.md) · **Types**: [data-model.md](data-model.md)

This walks the CLI path end to end; every library call has the identical shape (Article II). No step here needs `NVIDIA_API_KEY` unless the evaluator requested is run in live mode.

Steps 3, 5 and 6 pass `--live` to `tna-lab run`, so `NVIDIA_API_KEY` is required for this walkthrough. `run` keeps trust-no-agent's judge-call evidence in `.tna-lab/cache/`: `--live` calls the judge on a cache miss and saves the result there, so repeating a call is not billed again. Without `--live`, `run` only replays what that cache already holds; any record it doesn't hold comes back `status=error` naming a cache miss, not a score.

## Prerequisites

```bash
uv sync
export JUDGE_MODEL=<a trust-no-agent-recognized judge model id>
export GENERATOR_MODEL=<a trust-no-agent-recognized generator model id>
```

## 1. Ingest a batch of records

```bash
cat > records.jsonl <<'EOF'
{"input": "What is the refund window?", "output": "30 days from delivery.", "expected": "30 days.", "contexts": ["Refunds: 30 days from delivery, unopened."]}
{"input": "Do you ship internationally?", "output": "No, US only.", "expected": "US only.", "contexts": ["Shipping: currently US only."]}
EOF

tna-lab ingest records.jsonl --dataset smoke
```

**Expected**: `.tna-lab/datasets/smoke/` now exists with two record files and a `head.json` listing both ids.

```bash
tna-lab ingest records.jsonl --dataset smoke   # re-ingest the same file
```

**Expected**: dataset record count is still 2 (SC-002) — the command reports `added=0, already_present=2`.

## 2. Freeze a reproducible snapshot

```bash
tna-lab freeze smoke v1
```

**Expected**: `.tna-lab/datasets/smoke/snapshots/v1.json` is created, carrying a `snapshot_id` and the two record ids frozen at this moment (SC-003).

```bash
echo '{"input": "Where are you located?", "output": "Remote only.", "expected": "Remote.", "contexts": ["We are a remote-first team."]}' >> records.jsonl
tna-lab ingest records.jsonl --dataset smoke
```

**Expected**: `smoke` now has 3 records at HEAD, but `smoke@v1` still resolves to the original 2 — re-reading it confirms byte-identical content to what was frozen (SC-003).

## 3. Run an evaluator against the frozen snapshot

```bash
tna-lab run smoke@v1 --evaluator tna.ragas.faithfulness --live
```

**Expected**: a run record is written to `.tna-lab/runs/<run_id>.json`, carrying one `EvalResult` per record in `smoke@v1` for `tna.ragas.faithfulness` — status, score, judge model, fingerprint, token counts, all exactly as trust-no-agent's `evaluate()` returned them (SC-004). The run's own `run_id` is printed, and each judge call is saved under `.tna-lab/cache/`.

> `tna.ragas.faithfulness`, not `tna.ragas.response_relevancy`: scoring response relevancy live needs local embeddings (`sentence-transformers`), which trust-no-agent keeps in a dependency group of its own and tna-lab does not install — more ML tooling than a quickstart should require (Article VI). It is the only one of trust-no-agent's four `tna.ragas.*` metrics that builds embeddings, so any of the other three works here unchanged.

Now run the identical command a second time:

```bash
tna-lab run smoke@v1 --evaluator tna.ragas.faithfulness --live
```

**Expected**: a second, distinct run record with a new `run_id`, scored against the identical `smoke@v1` snapshot — every score, fingerprint and token count identical to the first run's, served from `.tna-lab/cache/` instead of billed again. The command returns in a fraction of the first run's time and `.tna-lab/cache/` gains no new entries.

This is re-scoring, not re-generating. A snapshot's records have fixed outputs — `record_id` is a hash over all five record fields, `output` among them (research R1) — so running one snapshot again always scores the same input/output pairs. What a second run can legitimately differ on is the *judging*: a different `JUDGE_MODEL`, a different evaluator id, an edited rubric. Comparing two different sets of outputs for the same inputs — whether an agent's answers got better — is out of scope for v1 and deferred explicitly in CONSTITUTION.md Article VIII.

## 4. Compare the two runs

```bash
tna-lab compare <run_id_1> <run_id_2> --evaluator tna.ragas.faithfulness
```

**Expected**: a per-record table, each row naming one record and showing both runs' status and score, the delta, a classification (`improved`/`regressed`/`unchanged`) and both runs' judge fingerprints, plus a summary line with counts and the mean-score delta (SC-007).

Every row here reads `unchanged` with a zero delta, and each record's two fingerprints match. That is the result this step demonstrates, not a shortcoming of the walkthrough: two runs of one frozen snapshot under one judge configuration must score identical content identically, and a comparison that claimed otherwise would be reporting noise. A non-zero delta means something about the judging moved, and the fingerprint columns are what say which side moved (Article V) — so this all-`unchanged` table is the baseline that makes a later non-zero one meaningful.

Comparing a run to itself:

```bash
tna-lab compare <run_id_1> <run_id_1> --evaluator tna.ragas.faithfulness
```

**Expected**: every record reports `unchanged`, zero delta.

## 5. Every failure class survives the round trip

Run an evaluator id trust-no-agent doesn't recognize:

```bash
tna-lab run smoke@v1 --evaluator tna.does.not.exist --live
```

**Expected**: the run record is still written — every record's result has status `error`, naming the unknown id, exactly as trust-no-agent's own `evaluate()` returns it (SC-005). The command does not crash.

## 6. Mismatched comparisons fail loudly

```bash
tna-lab freeze smoke v2   # a second, distinct snapshot of the same 3-record HEAD
tna-lab run smoke@v2 --evaluator tna.ragas.faithfulness --live
tna-lab compare <run_against_v1> <run_against_v2> --evaluator tna.ragas.faithfulness
```

**Expected**: the command fails, naming the snapshot mismatch — it never silently produces a comparison across different data (SC-006).
