"""`tna-lab`: one argparse parser, five subcommands, each calling the library function of
the same name (Article II). Nothing here but argument parsing and result formatting —
every rule lives in the library, so the CLI can never disagree with it.

`--workspace` is a flag only; no environment variable is ever read for it (research R4).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from trustnoagent import JudgeConfig

from tna_lab.compare import (
    CaseComparison,
    CaseDelta,
    Comparison,
    RecordDelta,
    compare,
    compare_cases,
)
from tna_lab.datasets import ingest, load_jsonl
from tna_lab.runs import EvaluateFn, RunRecord, load_run, run
from tna_lab.snapshots import freeze
from tna_lab.storage import workspace_root


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--workspace", type=Path, default=None, help="workspace root (default: ./.tna-lab)"
    )
    common.add_argument("--json", action="store_true", help="print the full result as JSON")

    parser = argparse.ArgumentParser(prog="tna-lab", description="Dataset, run, compare — built on trust-no-agent.")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("ingest", parents=[common], help="add JSONL records to a dataset")
    p.add_argument("file", type=Path)
    p.add_argument("--dataset", required=True)

    p = commands.add_parser("freeze", parents=[common], help="freeze a dataset as <dataset>@<tag>")
    p.add_argument("dataset")
    p.add_argument("tag")

    p = commands.add_parser("run", parents=[common], help="score a snapshot via trust-no-agent")
    p.add_argument("snapshot", metavar="<dataset>@<tag>")
    p.add_argument("--evaluator", action="append", required=True, dest="evaluators")
    p.add_argument(
        "--live",
        action="store_true",
        help=(
            "call the real judge/generator models on a cache miss and save the result "
            "to <workspace>/cache, so a repeat is served from disk. Without it, run "
            "replays only what that cache already holds; anything else is a cache-miss "
            "error. Reads NVIDIA_API_KEY, same as trust-no-agent itself; "
            "JUDGE_MODEL/GENERATOR_MODEL are read either way (Article IV: this flag only "
            "selects JudgeConfig.from_env()'s own `mode`, never a second config path)."
        ),
    )

    p = commands.add_parser(
        "compare-cases",
        parents=[common],
        help="diff two runs by case (same input + expected) across snapshots — no "
        "same-snapshot guarantee; judge and generator must match",
    )
    p.add_argument("run_a")
    p.add_argument("run_b")
    p.add_argument("--evaluator", required=True)

    p = commands.add_parser("compare", parents=[common], help="diff two runs for one evaluator")
    p.add_argument("run_a")
    p.add_argument("run_b")
    p.add_argument("--evaluator", required=True)
    return parser


def _short(value: str | None) -> str:
    return "-" if value is None else value[:12]


def _value(score: float | None, label: str | None) -> str:
    return label if label is not None else "-" if score is None else f"{score:.4f}"


def _signed(value: float | None) -> str:
    return "-" if value is None else f"{value:+.4f}"


def _tokens(tokens_in: int | None, tokens_out: int | None) -> str:
    if tokens_in is None and tokens_out is None:
        return "-"
    return f"{'-' if tokens_in is None else tokens_in}/{'-' if tokens_out is None else tokens_out}"


def _align(rows: Sequence[tuple[str, ...]]) -> list[str]:
    """Left-align every column but the last, two spaces apart."""
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
    return ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=False)) + "  " + row[-1]
            for row in rows]


def _pair_cells(d: RecordDelta | CaseDelta) -> tuple[str, str, str, str, str]:
    """Status, a, b, delta and class — formatted once for both comparisons' tables."""
    status = f"{d.status_a} → {d.status_b}" if d.status_changed else d.status_a
    a, b = _value(d.score_a, d.label_a), _value(d.score_b, d.label_b)
    return status, a, b, d.transition or _signed(d.delta), d.classification


def _cost_cells(d: RecordDelta | CaseDelta) -> tuple[str, str]:
    """Both fingerprints and both token counts (Article V), formatted once for both tables."""
    return (
        f"{_short(d.fingerprint_a)} → {_short(d.fingerprint_b)}",
        f"{_tokens(d.tokens_in_a, d.tokens_out_a)} → {_tokens(d.tokens_in_b, d.tokens_out_b)}",
    )


def _comparison_table(result: Comparison) -> str:
    rows = [("record", "status", "a", "b", "delta", "class", "fingerprint a → b", "tokens a → b")]
    rows += [(_short(d.record_id), *_pair_cells(d), *_cost_cells(d)) for d in result.records]
    lines = _align(rows)
    s = result.summary
    lines.append(
        f"summary: improved={s.improved} regressed={s.regressed} unchanged={s.unchanged} "
        f"mean_score_delta={_signed(s.mean_score_delta)} "
        f"pass_rate_delta={_signed(s.pass_rate_delta)}"
    )
    return "\n".join(lines)


MATCH_BASIS = "matched by case (input + expected) across snapshots — no same-snapshot guarantee"


def _flag(value: bool) -> str:
    return "yes" if value else "-"


def _case_table(result: CaseComparison, run_a: RunRecord, run_b: RunRecord) -> str:
    """Spec 002 FR-026: the matching basis comes first, so a pasted table can never be
    mistaken for `compare`'s; every section prints, even empty, so absence is stated."""
    lines = [
        MATCH_BASIS,
        (
            f"run a: {run_a.run_id} ({run_a.snapshot_ref})  run b: {run_b.run_id} "
            f"({run_b.snapshot_ref})  judge: {run_a.judge_model}"
        ),
    ]
    header = ("case", "status", "a", "b", "delta", "class", "ctx", "out", "fingerprint a → b",
              "tokens a → b")
    rows: list[tuple[str, ...]] = [header]
    rows += [
        (_short(d.case_id), *_pair_cells(d), _flag(d.contexts_changed), _flag(d.output_changed),
         *_cost_cells(d))
        for d in result.cases
    ]
    lines += _align(rows)
    for side, unmatched in (("a", result.unmatched_a), ("b", result.unmatched_b)):
        lines.append(f"unmatched in {side} ({len(unmatched)}):")
        lines += [
            f"  {_short(u.record_id)}  {u.reason}  {u.status}  {_value(u.score, u.label)}  "
            f"fingerprint {_short(u.fingerprint)}  tokens {_tokens(u.tokens_in, u.tokens_out)}"
            for u in unmatched
        ]
    lines.append(f"ambiguous ({len(result.ambiguous)}):")
    lines += [
        f"  {_short(a.case_id)}  a: {', '.join(map(_short, a.record_ids_a)) or '-'}  "
        f"b: {', '.join(map(_short, a.record_ids_b)) or '-'}"
        for a in result.ambiguous
    ]
    s = result.summary
    lines.append(
        f"summary: paired={s.paired} improved={s.improved} regressed={s.regressed} "
        f"unchanged={s.unchanged} contexts_changed={s.contexts_changed} "
        f"output_changed={s.output_changed} unmatched_a={s.unmatched_a} "
        f"unmatched_b={s.unmatched_b} ambiguous={s.ambiguous} "
        f"mean_score_delta={_signed(s.mean_score_delta)} "
        f"pass_rate_delta={_signed(s.pass_rate_delta)}"
    )
    return "\n".join(lines)


def _dispatch(args: argparse.Namespace, evaluate_fn: EvaluateFn | None) -> tuple[Any, str]:
    """Call the one library function the subcommand names; return it and its text form."""
    workspace = workspace_root(args.workspace)
    if args.command == "ingest":
        counts = ingest(workspace, args.dataset, load_jsonl(args.file))
        return counts, f"added={counts.added}, already_present={counts.already_present}"
    if args.command == "freeze":
        ref = freeze(workspace, args.dataset, args.tag)
        text = f"{ref.dataset}@{ref.tag} snapshot_id={ref.snapshot_id} records={len(ref.record_ids)}"
        return ref, text
    if args.command == "run":
        judge = JudgeConfig.from_env(mode="live") if args.live else None
        kwargs: dict[str, Any] = {"judge": judge}
        if evaluate_fn is not None:
            kwargs["evaluate_fn"] = evaluate_fn
        record = run(workspace, args.snapshot, args.evaluators, **kwargs)
        return record, record.run_id
    run_a, run_b = load_run(workspace, args.run_a), load_run(workspace, args.run_b)
    if args.command == "compare-cases":
        cases = compare_cases(workspace, run_a, run_b, args.evaluator)
        return cases, _case_table(cases, run_a, run_b)
    result = compare(run_a, run_b, args.evaluator)
    return result, _comparison_table(result)


def main(argv: Sequence[str] | None = None, *, evaluate_fn: EvaluateFn | None = None) -> int:
    """Entry point for the `tna-lab` console script. `evaluate_fn` is the research R6 test
    seam, passed straight to run(); the console script never sets it."""
    args = _parser().parse_args(argv)
    try:
        result, text = _dispatch(args, evaluate_fn)
    except (ValueError, OSError) as exc:
        print(f"tna-lab: error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False) if args.json else text)
    return 0
