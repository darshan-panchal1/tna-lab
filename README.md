# tna-lab

**Freeze a dataset, score it through [trust-no-agent](https://github.com/darshan-panchal1/trust-no-agent), and diff two runs record by record — locally, with no server and no database.**

[![PyPI version](https://img.shields.io/pypi/v/tna-lab.svg)](https://pypi.org/project/tna-lab/)
[![Python](https://img.shields.io/pypi/pyversions/tna-lab.svg)](https://pypi.org/project/tna-lab/)
[![License](https://img.shields.io/pypi/l/tna-lab.svg)](https://github.com/darshan-panchal1/tna-lab/blob/main/LICENSE)
[![ci](https://github.com/darshan-panchal1/tna-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/darshan-panchal1/tna-lab/actions/workflows/ci.yml)

trust-no-agent answers "does this one record pass?". tna-lab answers "across a frozen dataset, under a given judge, what changed?" — it ingests records content-addressed and idempotently, freezes immutable named snapshots, scores them by calling trust-no-agent's `evaluate()` once per (record, evaluator) pair, and compares two runs into a per-record diff that names every improvement and regression individually instead of reporting an aggregate that can hide one. It computes no score of its own: trust-no-agent is the only scorer, and every `EvalResult` is persisted exactly as returned, status, fingerprint, token counts and all. Storage is a directory of JSON files under `.tna-lab/`.

v0.1.0 is the whole of the v1 slice and nothing else. The reasoning behind every rule it follows — one scorer, library-first, no provider abstraction, append-only versioning — is in [CONSTITUTION.md](https://github.com/darshan-panchal1/tna-lab/blob/main/CONSTITUTION.md); the spec, design-decision log and task breakdown that produced this code are in [specs/001-dataset-run-compare/](https://github.com/darshan-panchal1/tna-lab/tree/main/specs/001-dataset-run-compare).

## Install

```bash
uv add tna-lab      # or: pip install tna-lab
```

Python 3.12 exactly. The only runtime dependency is `trust-no-agent`.

## Quickstart

Scoring needs the same two model variables trust-no-agent itself reads, plus `NVIDIA_API_KEY` for `--live`:

```bash
export JUDGE_MODEL=nvidia/nemotron-3-super-120b-a12b
export GENERATOR_MODEL=nvidia/nemotron-3-super-120b-a12b
export NVIDIA_API_KEY=...
```

**1. Ingest records.** Identity is a hash of a record's content, so re-ingesting the same file is a no-op:

```bash
cat > records.jsonl <<'EOF'
{"input": "What is the refund window?", "output": "30 days from delivery.", "expected": "30 days.", "contexts": ["Refunds: 30 days from delivery, unopened."]}
{"input": "Do you ship internationally?", "output": "No, US only.", "expected": "US only.", "contexts": ["Shipping: currently US only."]}
EOF

tna-lab ingest records.jsonl --dataset smoke     # added=2, already_present=0
tna-lab ingest records.jsonl --dataset smoke     # added=0, already_present=2
```

**2. Freeze a snapshot.** Immutable and independently addressable as `smoke@v1`; later ingestion cannot change it, and re-freezing an existing tag is an error, never an overwrite:

```bash
tna-lab freeze smoke v1
# smoke@v1 snapshot_id=9a6d995b0cc5... records=2
```

**3. Score it.** One trust-no-agent `evaluate()` call per (record, evaluator) pair. Judge calls are cached under `.tna-lab/cache/`, so a repeat is served from disk instead of billed again:

```bash
tna-lab run smoke@v1 --evaluator tna.ragas.faithfulness --live
# 20260928T193652Z-c79e0f03
```

Every result is persisted whatever its status — an `error`, `skipped` or `invalid_output` result is kept as returned, never dropped or coerced to a number.

**4. Compare two runs.** Both must have scored the same snapshot with the same evaluator; a mismatch is a named error, never a silent diff across different data:

```bash
tna-lab compare <run_id_1> <run_id_2> --evaluator tna.ragas.faithfulness
```

```
record        status  a       b       delta    class      fingerprint a → b
569cddb2252c  ok      1.0000  1.0000  +0.0000  unchanged  0659fb5515c9 → 0659fb5515c9
5c8fa5fd7f4f  ok      1.0000  1.0000  +0.0000  unchanged  e13108284261 → e13108284261
summary: improved=0 regressed=0 unchanged=2 mean_score_delta=+0.0000 pass_rate_delta=-
```

Both runs' judge fingerprints travel with the diff, so a score that moved because the judge moved is visible as such.

The walkthrough in full, including the failure paths, is [specs/001-dataset-run-compare/quickstart.md](https://github.com/darshan-panchal1/tna-lab/blob/main/specs/001-dataset-run-compare/quickstart.md).

## Commands

| Command | Does |
|---|---|
| `tna-lab ingest <file.jsonl> --dataset <name>` | Add records to a dataset, deduplicating by content identity |
| `tna-lab freeze <dataset> <tag>` | Freeze the current record set as an immutable `<dataset>@<tag>` snapshot |
| `tna-lab run <dataset>@<tag> --evaluator <id> [--evaluator <id> ...] [--live]` | Score every record via trust-no-agent, persisting each result unmodified |
| `tna-lab compare <run_a> <run_b> --evaluator <id>` | Per-record diff of two runs: delta, classification, status change, both fingerprints |

Every command takes `--workspace <path>` (default `./.tna-lab`, never an environment variable) and `--json` to print the full result as JSON.

## As a library

The CLI is argument parsing over these four functions; nothing is reachable from one surface only, and no server or UI is involved on any path.

```python
from pathlib import Path

from tna_lab import compare, freeze, ingest, load_run, run
from tna_lab.datasets import load_jsonl

workspace = Path(".tna-lab")

ingest(workspace, "smoke", load_jsonl(Path("records.jsonl")))
snapshot = freeze(workspace, "smoke", "v1")

record = run(workspace, snapshot, ["tna.ragas.faithfulness"])
diff = compare(record, load_run(workspace, "<earlier_run_id>"), "tna.ragas.faithfulness")

print(diff.summary.improved, diff.summary.regressed, diff.summary.mean_score_delta)
```

`run()` also takes `judge` (a trust-no-agent `JudgeConfig` — pass `JudgeConfig.from_env(mode="live")` for what `--live` does) and `cache_dir`, which defaults to `<workspace>/cache`.

## What v0.1.0 deliberately does not do

`compare()` diffs two *judgings* of one frozen set of input/output pairs — a different judge model, evaluator or rubric. It cannot answer "same inputs, before and after my agent changed": a record's identity includes its `output`, so a different output is a different record in a different snapshot, and comparison requires one shared snapshot. That is the question most teams want answered, and it is deferred explicitly rather than accidentally — see Article VIII of [CONSTITUTION.md](https://github.com/darshan-panchal1/tna-lab/blob/main/CONSTITUTION.md), which names both routes a later spec can take. Trace/OTel ingestion and any hosted or shared view are deferred there too.

Scoring `tna.ragas.response_relevancy` live additionally needs `sentence-transformers`, which trust-no-agent keeps in a dependency group of its own; the other three `tna.ragas.*` metrics need no extra.

## License

MIT — see [LICENSE](https://github.com/darshan-panchal1/tna-lab/blob/main/LICENSE).
