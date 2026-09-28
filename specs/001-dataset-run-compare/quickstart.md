# Quickstart: Dataset, Run, Compare

**Feature**: [spec.md](spec.md) · **API**: [contracts/public-api.md](contracts/public-api.md) · **Types**: [data-model.md](data-model.md)

This walks the CLI path end to end; every library call has the identical shape (Article II). No step here needs `NVIDIA_API_KEY` unless the evaluator requested is run in live mode.

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
tna-lab run smoke@v1 --evaluator tna.ragas.response_relevancy
```

**Expected**: a run record is written to `.tna-lab/runs/<run_id>.json`, carrying one `EvalResult` per record in `smoke@v1` for `tna.ragas.response_relevancy` — status, score, judge model, fingerprint, token counts, all exactly as trust-no-agent's `evaluate()` returned them (SC-004). The run's own `run_id` is printed.

Run it again, against a (hypothetically) improved generator:

```bash
tna-lab run smoke@v1 --evaluator tna.ragas.response_relevancy
```

**Expected**: a second, distinct run record with a new `run_id`, scored against the identical `smoke@v1` snapshot.

## 4. Compare the two runs

```bash
tna-lab compare <run_id_1> <run_id_2> --evaluator tna.ragas.response_relevancy
```

**Expected**: a per-record table, each row showing both runs' score, the delta, and a classification (`improved`/`regressed`/`unchanged`), plus a summary line with counts and the mean-score delta (SC-007). Comparing a run to itself:

```bash
tna-lab compare <run_id_1> <run_id_1> --evaluator tna.ragas.response_relevancy
```

**Expected**: every record reports `unchanged`, zero delta.

## 5. Every failure class survives the round trip

Run an evaluator id trust-no-agent doesn't recognize:

```bash
tna-lab run smoke@v1 --evaluator tna.does.not.exist
```

**Expected**: the run record is still written — every record's result has status `error`, naming the unknown id, exactly as trust-no-agent's own `evaluate()` returns it (SC-005). The command does not crash.

## 6. Mismatched comparisons fail loudly

```bash
tna-lab freeze smoke v2   # a second, distinct snapshot of the same 3-record HEAD
tna-lab run smoke@v2 --evaluator tna.ragas.response_relevancy
tna-lab compare <run_against_v1> <run_against_v2> --evaluator tna.ragas.response_relevancy
```

**Expected**: the command fails, naming the snapshot mismatch — it never silently produces a comparison across different data (SC-006).
