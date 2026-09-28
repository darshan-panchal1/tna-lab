"""`tna-lab`: one argparse parser, four subcommands, each calling the library function of
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

from tna_lab.compare import Comparison, compare
from tna_lab.datasets import ingest, load_jsonl
from tna_lab.runs import EvaluateFn, load_run, run
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
            "call the real judge/generator models instead of trust-no-agent's offline "
            "mode (which needs a repo-checkout fixture cache and produces no scores "
            "when installed as a package). Reads NVIDIA_API_KEY, same as trust-no-agent "
            "itself; JUDGE_MODEL/GENERATOR_MODEL are read either way (Article IV: this "
            "flag only selects JudgeConfig.from_env()'s own `mode`, never a second "
            "config path)."
        ),
    )

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


def _comparison_table(result: Comparison) -> str:
    rows = [("record", "status", "a", "b", "delta", "class", "fingerprint a → b")]
    for d in result.records:
        status = f"{d.status_a} → {d.status_b}" if d.status_changed else d.status_a
        rows.append((
            _short(d.record_id),
            status,
            _value(d.score_a, d.label_a),
            _value(d.score_b, d.label_b),
            d.transition or _signed(d.delta),
            d.classification,
            f"{_short(d.fingerprint_a)} → {_short(d.fingerprint_b)}",
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
    lines = ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=False)) + "  " + row[-1]
             for row in rows]
    s = result.summary
    lines.append(
        f"summary: improved={s.improved} regressed={s.regressed} unchanged={s.unchanged} "
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
    result = compare(load_run(workspace, args.run_a), load_run(workspace, args.run_b), args.evaluator)
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
