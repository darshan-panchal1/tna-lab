# Quickstart: Compare Outputs by Case

**Feature**: [spec.md](spec.md) · **API**: [contracts/public-api.md](contracts/public-api.md) · **Types**: [data-model.md](data-model.md)

**This walkthrough is self-contained.** It starts in an empty directory and never reads anything [spec 001's quickstart](../001-dataset-run-compare/quickstart.md) created. If you ran that one, run this one in a new directory: its `.tna-lab/` workspace, `smoke` dataset and runs are not used here, and nothing here depends on their state. Every dataset, snapshot and run below is created by a step on this page.

Steps 3 and 5 pass `--live` to `tna-lab run`, so `NVIDIA_API_KEY` is required. Steps 6 and 7 deliberately run *without* `--live`: they re-score records this walkthrough has already scored, and those are served from the workspace cache at no cost (spec 001 research R6).

## Prerequisites

```bash
mkdir compare-cases-demo && cd compare-cases-demo
uv add tna-lab          # or: pip install tna-lab   (v0.2.0 or later)
export JUDGE_MODEL=<a trust-no-agent-recognized judge model id>
export GENERATOR_MODEL=<a trust-no-agent-recognized generator model id>
export NVIDIA_API_KEY=<your key>
```

## 1. Two output sets for the same questions

Version 1 and version 2 of an agent, answering overlapping questions. Each case below shows one thing the comparison must handle:

- **Refunds.** The same answer in both versions, but v2's retriever returned an extra chunk, so `contexts` differ.
- **Shipping.** v1's answer contradicts its own context and v2's is fixed, so `output` differs.
- **Location.** Only v1 has this case: v2 dropped it.
- **Hours.** Only v2 has this case: it is new.

```bash
cat > agent-v1.jsonl <<'EOF'
{"input": "What is the refund window?", "output": "30 days from delivery.", "expected": "30 days.", "contexts": ["Refunds: 30 days from delivery, unopened."]}
{"input": "Do you ship internationally?", "output": "Yes, we ship worldwide.", "expected": "US only.", "contexts": ["Shipping: currently US only."]}
{"input": "Where are you located?", "output": "Remote only.", "expected": "Remote.", "contexts": ["We are a remote-first team."]}
EOF

cat > agent-v2.jsonl <<'EOF'
{"input": "What is the refund window?", "output": "30 days from delivery.", "expected": "30 days.", "contexts": ["Refunds: 30 days from delivery, unopened.", "Opened items: store credit only."]}
{"input": "Do you ship internationally?", "output": "No, US only.", "expected": "US only.", "contexts": ["Shipping: currently US only."]}
{"input": "What are your support hours?", "output": "Weekdays, 9am to 5pm ET.", "expected": "Weekdays 9-5 ET.", "contexts": ["Support: weekdays 9am-5pm ET."]}
EOF
```

## 2. One dataset per output set, each frozen

```bash
tna-lab ingest agent-v1.jsonl --dataset agent-v1 && tna-lab freeze agent-v1 base
tna-lab ingest agent-v2.jsonl --dataset agent-v2 && tna-lab freeze agent-v2 base
```

**Expected**: two datasets, each with three records, each frozen as `@base`. They are separate datasets on purpose. A dataset's record set only grows (spec 001), so ingesting v2's outputs into `agent-v1` would leave both versions' records in one snapshot. Step 7 shows what the comparison does then.

## 3. Score both under the same judge

```bash
tna-lab run agent-v1@base --evaluator tna.ragas.faithfulness --live    # prints <run_v1>
tna-lab run agent-v2@base --evaluator tna.ragas.faithfulness --live    # prints <run_v2>
```

**Expected**: two run ids printed, one per run. Both runs record the same `JUDGE_MODEL` and `GENERATOR_MODEL`, which step 4 requires.

## 4. Compare by case

```bash
tna-lab compare-cases <run_v1> <run_v2> --evaluator tna.ragas.faithfulness
```

**Expected**, in this order:

1. **A first line stating the matching basis**: `matched by case (input + expected) across snapshots — no same-snapshot guarantee` (spec FR-026).
2. **Two paired cases**:
   - *Refunds*: `ctx` set (contexts changed) and `out` not set (same answer). Still classified and counted in the summary (spec FR-017).
   - *Shipping*: `out` set. Its v1 answer contradicts its own context, so it is expected to be classified `improved`. The exact scores come from the live judge.
3. **`unmatched in a (1)`**: *Location*, reason `no_counterpart`, with its own v1 status, score and fingerprint.
4. **`unmatched in b (1)`**: *Hours*, reason `no_counterpart`, with its own v2 status, score and fingerprint.
5. **`ambiguous (0)`**.
6. **A summary line**: `paired=2`, `contexts_changed=1`, `output_changed=1`, `unmatched_a=1`, `unmatched_b=1`, `ambiguous=0`, the improved, regressed and unchanged counts over the two pairs, and `mean_score_delta` over both pairs.

On each side, paired + unmatched + ambiguous record ids = 3, the number of records each run scored (spec SC-002). Nothing was dropped.

```bash
tna-lab compare-cases <run_v1> <run_v2> --evaluator tna.ragas.faithfulness --json
```

**Expected**: the same comparison as JSON, identical to what `tna_lab.compare_cases()` returns (spec FR-025).

## 5. The same-snapshot comparison still refuses

```bash
tna-lab compare <run_v1> <run_v2> --evaluator tna.ragas.faithfulness
```

**Expected**: this fails, naming the snapshot mismatch. `compare` still requires one shared snapshot (spec 001 FR-021), and `compare-cases` did not change that (spec FR-006). The two commands answer different questions: `compare` asks whether the judging changed the scores, `compare-cases` whether the outputs got better.

## 6. Different judging is refused, with no way around it

Re-run v2 under a different `JUDGE_MODEL`, offline. Its results will be cache-miss errors, since nothing was ever scored under that judge. That doesn't matter: the comparison refuses before it reads any score.

```bash
JUDGE_MODEL=some-other-judge-model tna-lab run agent-v2@base --evaluator tna.ragas.faithfulness    # prints <run_v2_other>
tna-lab compare-cases <run_v1> <run_v2_other> --evaluator tna.ragas.faithfulness
```

**Expected**: this fails, naming both judge models (spec FR-009). There is no flag to override it. Both run files remain readable in `.tna-lab/runs/` for anyone who wants to inspect them by hand.

## 7. Two output sets in one dataset are ambiguous, not guessed

Ingest v2's outputs into v1's dataset, freeze that mixed state, and score it offline. Every record in it was already scored under this judge in step 3, so this costs nothing.

```bash
tna-lab ingest agent-v2.jsonl --dataset agent-v1 && tna-lab freeze agent-v1 mixed
tna-lab run agent-v1@mixed --evaluator tna.ragas.faithfulness                     # prints <run_mixed>
tna-lab compare-cases <run_mixed> <run_v2> --evaluator tna.ragas.faithfulness
```

**Expected**:

- `ambiguous (2)`: *Refunds* and *Shipping*. Each is carried by two records in `<run_mixed>`, its v1 and v2 versions, and one in `<run_v2>`. Every record id is listed, and no delta is computed for either case (spec FR-014).
- *Hours* pairs once, because it appears once on each side.
- *Location* is `unmatched in a`, reason `no_counterpart`.

The comparison never picks which version of an ambiguous case to use. That is the loud outcome of not following step 2's one-dataset-per-output-set workflow.
