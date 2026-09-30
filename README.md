# tna-lab

**Freeze a dataset, score it through [trust-no-agent](https://github.com/darshan-panchal1/trust-no-agent), and diff two runs record by record — or two versions of your agent case by case — locally, with no server and no database.**

[![PyPI version](https://img.shields.io/pypi/v/tna-lab.svg)](https://pypi.org/project/tna-lab/)
[![Python](https://img.shields.io/pypi/pyversions/tna-lab.svg)](https://pypi.org/project/tna-lab/)
[![License](https://img.shields.io/pypi/l/tna-lab.svg)](https://github.com/darshan-panchal1/tna-lab/blob/main/LICENSE)
[![ci](https://github.com/darshan-panchal1/tna-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/darshan-panchal1/tna-lab/actions/workflows/ci.yml)

trust-no-agent answers "does this one record pass?". tna-lab answers "across a frozen dataset, under a given judge, what changed?" — it ingests records content-addressed and idempotently, freezes immutable named snapshots, scores them by calling trust-no-agent's `evaluate()` once per (record, evaluator) pair, and compares two runs into a per-record diff that names every improvement and regression individually instead of reporting an aggregate that can hide one. It can also compare two *agent versions*: the outputs each gave for the same questions, paired case by case across two datasets, under one fixed judge. It computes no score of its own: trust-no-agent is the only scorer, and every `EvalResult` is persisted exactly as returned, status, fingerprint, token counts and all. Storage is a directory of JSON files under `.tna-lab/`.

v0.2.0 is the v1 slice plus the one item its constitution deferred and this release took up: comparing two sets of outputs for the same inputs. The reasoning behind every rule it follows — one scorer, library-first, no provider abstraction, append-only versioning — is in [CONSTITUTION.md](https://github.com/darshan-panchal1/tna-lab/blob/main/CONSTITUTION.md). The spec, design-decision log and task breakdown behind each feature are in [specs/001-dataset-run-compare/](https://github.com/darshan-panchal1/tna-lab/tree/main/specs/001-dataset-run-compare) and [specs/002-compare-outputs/](https://github.com/darshan-panchal1/tna-lab/tree/main/specs/002-compare-outputs).

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
record        status  a       b       delta    class      fingerprint a → b            tokens a → b
569cddb2252c  ok      1.0000  1.0000  +0.0000  unchanged  0659fb5515c9 → 0659fb5515c9  1919/582 → 1919/582
5c8fa5fd7f4f  ok      1.0000  1.0000  +0.0000  unchanged  e13108284261 → e13108284261  1915/710 → 1915/710
summary: improved=0 regressed=0 unchanged=2 mean_score_delta=+0.0000 pass_rate_delta=-
```

Both runs' judge fingerprints and token counts travel with the diff, so a score that moved because the judge moved is visible as such, and so is what each score cost.

The walkthrough in full, including the failure paths, is [specs/001-dataset-run-compare/quickstart.md](https://github.com/darshan-panchal1/tna-lab/blob/main/specs/001-dataset-run-compare/quickstart.md).

## Compare two agent versions by case

`compare` holds the records fixed and lets the judging differ: *did my judge change move my scores?*. `compare-cases` holds the judging fixed and lets the outputs differ: *did my agent get better?*

Ingest each version's outputs into **its own dataset**. A dataset's record set only ever grows, so two versions in one dataset would put every case in the run twice. Then freeze each, and score both with the same evaluator and judge:

```bash
tna-lab ingest agent-v1.jsonl --dataset agent-v1 && tna-lab freeze agent-v1 base
tna-lab ingest agent-v2.jsonl --dataset agent-v2 && tna-lab freeze agent-v2 base
tna-lab run agent-v1@base --evaluator tna.ragas.faithfulness --live    # prints <run_v1>
tna-lab run agent-v2@base --evaluator tna.ragas.faithfulness --live    # prints <run_v2>

tna-lab compare-cases <run_v1> <run_v2> --evaluator tna.ragas.faithfulness
```

A *case* is a record's `input` plus its `expected`. The output is free to differ, since that is what is being compared, and so are the retrieved `contexts`, which in trust-no-agent's own model are agent output too. The report opens by saying so, so it can never be mistaken for `compare`'s:

```
matched by case (input + expected) across snapshots — no same-snapshot guarantee
```

Then it shows one row per paired case, with the same columns `compare` shows plus `ctx` and `out` flags for a changed context or output. It then accounts for everything it could not pair, each record listed individually: `unmatched in a (n):`, `unmatched in b (n):` and `ambiguous (n):`. A case present on only one side is unmatched. A case carried by more than one record in a run is ambiguous, and it is listed, never guessed at. The summary line counts all of it, so "3 improved" can never quietly mean "3 improved, and 40 were not looked at".

Two runs scored under different judge or generator models are refused, with an error naming both. There is no override: a delta across two judges would credit the agent with the judge's variance.

The full walkthrough, including the ambiguity and judge-mismatch paths, is [specs/002-compare-outputs/quickstart.md](https://github.com/darshan-panchal1/tna-lab/blob/main/specs/002-compare-outputs/quickstart.md).

## Commands

| Command | Does |
|---|---|
| `tna-lab ingest <file.jsonl> --dataset <name>` | Add records to a dataset, deduplicating by content identity |
| `tna-lab freeze <dataset> <tag>` | Freeze the current record set as an immutable `<dataset>@<tag>` snapshot |
| `tna-lab run <dataset>@<tag> --evaluator <id> [--evaluator <id> ...] [--live]` | Score every record via trust-no-agent, persisting each result unmodified |
| `tna-lab compare <run_a> <run_b> --evaluator <id>` | Per-record diff of two runs of **one** snapshot: delta, classification, status change, both fingerprints and token counts |
| `tna-lab compare-cases <run_a> <run_b> --evaluator <id>` | Per-case diff of two runs of **any two** snapshots, same judge required: everything `compare` shows, plus changed-context and changed-output flags, and every case it could not pair |

Every command takes `--workspace <path>` (default `./.tna-lab`, never an environment variable) and `--json` to print the full result as JSON.

## As a library

The CLI is argument parsing over these functions; nothing is reachable from one surface only, and no server or UI is involved on any path.

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

Comparing two agent versions by case takes the workspace too, because it reads the records each run scored:

```python
from tna_lab import compare_cases

by_case = compare_cases(workspace, load_run(workspace, "<run_v1>"), load_run(workspace, "<run_v2>"),
                        "tna.ragas.faithfulness")

print(by_case.summary.paired, by_case.summary.improved, by_case.summary.regressed)
for unmatched in by_case.unmatched_a:  # in v1 only: record id, reason, and its own result
    print(unmatched.record_id, unmatched.reason, unmatched.status, unmatched.score)
```

`run()` also takes `judge` (a trust-no-agent `JudgeConfig` — pass `JudgeConfig.from_env(mode="live")` for what `--live` does) and `cache_dir`, which defaults to `<workspace>/cache`.

## What v0.2.0 deliberately does not do

- **Compare across different judges.** `compare-cases` refuses two runs scored by different judge or generator models, and has no override. The raw run records in `.tna-lab/runs/` stay readable for anyone who wants to look at such a pair by hand.
- **Match cases loosely.** `"What is X?"` and `"What is X? "` are different cases. So are two questions with different reference answers: a corrected `expected` leaves that case unmatched on both sides instead of comparing scores against two different yardsticks.
- **Trace/OTel ingestion, or any hosted or shared view.** Both stay deferred under Article VIII of [CONSTITUTION.md](https://github.com/darshan-panchal1/tna-lab/blob/main/CONSTITUTION.md). tna-lab ingests already-structured records and runs no server.

Scoring `tna.ragas.response_relevancy` live additionally needs `sentence-transformers`, which trust-no-agent keeps in a dependency group of its own; the other three `tna.ragas.*` metrics need no extra.

## License

MIT — see [LICENSE](https://github.com/darshan-panchal1/tna-lab/blob/main/LICENSE).
