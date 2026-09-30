"""Tests for tna_lab.cli (T027): every subcommand, called through main(argv), produces
what the equivalent library call produces (Article II, SC-008).

`run` reaches the same evaluate_fn seam test_runs.py uses (research R6) via main()'s
keyword-only `evaluate_fn`; the console script never passes it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from tna_lab.cli import main
from tna_lab.compare import compare
from tna_lab.datasets import ingest, load_jsonl
from tna_lab.runs import load_run, run
from tna_lab.snapshots import freeze, resolve
from tna_lab.storage import read_json

EVALUATOR = "tna.fake.score"

RECORDS = [
    {"input": "What is the refund window?", "output": "30 days.", "contexts": ["Refunds: 30 days."]},
    {"input": "Do you ship internationally?", "output": "US only.", "expected": "US only."},
]


@dataclass(frozen=True)
class FakeResult:
    evaluator_id: str
    status: str
    score: float | None
    judge_fingerprint: str = "fp-test"


@dataclass
class FakeEvaluate:
    """Scores every record `score`, except inputs listed in `overrides`."""

    score: float = 0.5
    overrides: dict[str, float] = field(default_factory=dict)

    def __call__(self, evaluator_id: str, record: Any, judge: Any, cache_dir: Path) -> Any:
        return FakeResult(evaluator_id, "ok", self.overrides.get(record.input, self.score))


@pytest.fixture(autouse=True)
def _models_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_MODEL", "test-judge")
    monkeypatch.setenv("GENERATOR_MODEL", "test-generator")


@pytest.fixture
def records_file(tmp_path: Path) -> Path:
    path = tmp_path / "records.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in RECORDS))
    return path


def _cli(capsys: pytest.CaptureFixture[str], *argv: str | Path, **kw: Any) -> tuple[int, str, str]:
    code = main([str(a) for a in argv], **kw)
    out, err = capsys.readouterr()
    return code, out, err


def _plain(obj: Any) -> Any:
    """A dataclass as it looks after a JSON round trip (tuples become lists)."""
    return json.loads(json.dumps(asdict(obj)))


def _prepared(
    capsys: pytest.CaptureFixture[str], workspace: Path, records_file: Path, tag: str = "v1"
) -> None:
    assert _cli(capsys, "ingest", records_file, "--dataset", "smoke", "--workspace", workspace)[0] == 0
    assert _cli(capsys, "freeze", "smoke", tag, "--workspace", workspace)[0] == 0


# ingest


def test_ingest_matches_the_library_call(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_ws, lib_ws = tmp_path / "cli", tmp_path / "lib"
    code, out, _ = _cli(
        capsys, "ingest", records_file, "--dataset", "smoke", "--workspace", cli_ws, "--json"
    )
    expected = ingest(lib_ws, "smoke", load_jsonl(records_file))

    assert code == 0
    assert json.loads(out) == asdict(expected)
    head = Path("datasets/smoke/head.json")
    assert read_json(cli_ws / head) == read_json(lib_ws / head)


def test_reingest_reports_everything_already_present(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ("ingest", records_file, "--dataset", "smoke", "--workspace", tmp_path / "ws")
    assert _cli(capsys, *args)[1].strip() == "added=2, already_present=0"
    assert _cli(capsys, *args)[1].strip() == "added=0, already_present=2"


def test_ingest_rejects_an_unknown_field_naming_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"input": "q", "answer": "a"}\n')
    code, out, err = _cli(capsys, "ingest", bad, "--dataset", "smoke", "--workspace", tmp_path)
    assert code == 1
    assert out == ""
    assert "answer" in err


# freeze


def test_freeze_matches_the_library_snapshot(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cli(capsys, "ingest", records_file, "--dataset", "smoke", "--workspace", tmp_path)
    code, out, _ = _cli(capsys, "freeze", "smoke", "v1", "--workspace", tmp_path, "--json")
    assert code == 0
    assert json.loads(out) == _plain(resolve(tmp_path, "smoke@v1"))


def test_freeze_reports_the_snapshot_id(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _cli(capsys, "ingest", records_file, "--dataset", "smoke", "--workspace", tmp_path)
    _, out, _ = _cli(capsys, "freeze", "smoke", "v1", "--workspace", tmp_path)
    assert resolve(tmp_path, "smoke@v1").snapshot_id in out


def test_freezing_an_existing_tag_fails_naming_it(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepared(capsys, tmp_path, records_file)
    code, _, err = _cli(capsys, "freeze", "smoke", "v1", "--workspace", tmp_path)
    assert code == 1
    assert "'v1'" in err


# run


def test_run_prints_its_run_id_and_matches_the_library_run(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepared(capsys, tmp_path, records_file)
    fake = FakeEvaluate()
    code, out, _ = _cli(
        capsys, "run", "smoke@v1", "--evaluator", EVALUATOR, "--workspace", tmp_path,
        evaluate_fn=fake,
    )
    assert code == 0
    from_cli = load_run(tmp_path, out.strip())
    from_lib = run(tmp_path, "smoke@v1", [EVALUATOR], evaluate_fn=fake)
    # Two runs are two distinct records (research R3); everything else must be identical.
    assert from_cli == replace(from_lib, run_id=from_cli.run_id, created_at=from_cli.created_at)


def test_run_json_is_the_persisted_run_record(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepared(capsys, tmp_path, records_file)
    code, out, _ = _cli(
        capsys, "run", "smoke@v1", "--evaluator", EVALUATOR, "--evaluator", "tna.fake.other",
        "--workspace", tmp_path, "--json", evaluate_fn=FakeEvaluate(),
    )
    assert code == 0
    printed = json.loads(out)
    assert printed["evaluator_ids"] == [EVALUATOR, "tna.fake.other"]
    assert printed == _plain(load_run(tmp_path, printed["run_id"]))


def test_run_without_live_uses_offline_mode(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepared(capsys, tmp_path, records_file)
    seen_modes: list[str] = []

    def spy(evaluator_id: str, record: Any, judge: Any, cache_dir: Path) -> FakeResult:
        seen_modes.append(judge.mode)
        return FakeResult(evaluator_id, "ok", 0.5)

    code, _, _ = _cli(
        capsys, "run", "smoke@v1", "--evaluator", EVALUATOR, "--workspace", tmp_path,
        evaluate_fn=spy,
    )
    assert code == 0
    assert seen_modes == ["offline"] * len(RECORDS)


def test_run_with_live_flag_requests_live_mode(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepared(capsys, tmp_path, records_file)
    seen_modes: list[str] = []

    def spy(evaluator_id: str, record: Any, judge: Any, cache_dir: Path) -> FakeResult:
        seen_modes.append(judge.mode)
        return FakeResult(evaluator_id, "ok", 0.5)

    code, _, _ = _cli(
        capsys, "run", "smoke@v1", "--evaluator", EVALUATOR, "--live", "--workspace", tmp_path,
        evaluate_fn=spy,
    )
    assert code == 0
    assert seen_modes == ["live"] * len(RECORDS)


def test_run_against_an_unknown_tag_fails_naming_it(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepared(capsys, tmp_path, records_file)
    code, out, err = _cli(
        capsys, "run", "smoke@v9", "--evaluator", EVALUATOR, "--workspace", tmp_path,
        evaluate_fn=FakeEvaluate(),
    )
    assert code == 1
    assert out == ""
    assert "'v9'" in err
    assert not (tmp_path / "runs").exists()


def test_run_requires_at_least_one_evaluator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "smoke@v1", "--workspace", str(tmp_path)])
    assert excinfo.value.code == 2


# compare


def _two_runs(
    capsys: pytest.CaptureFixture[str], workspace: Path, records_file: Path
) -> tuple[str, str]:
    _prepared(capsys, workspace, records_file)
    better = FakeEvaluate(overrides={"What is the refund window?": 0.9})
    ids = []
    for fake in (FakeEvaluate(), better):
        args = ("run", "smoke@v1", "--evaluator", EVALUATOR, "--workspace", workspace)
        ids.append(_cli(capsys, *args, evaluate_fn=fake)[1].strip())
    return ids[0], ids[1]


def test_compare_matches_the_library_comparison(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_a, run_b = _two_runs(capsys, tmp_path, records_file)
    code, out, _ = _cli(
        capsys, "compare", run_a, run_b, "--evaluator", EVALUATOR, "--workspace", tmp_path, "--json"
    )
    expected = compare(load_run(tmp_path, run_a), load_run(tmp_path, run_b), EVALUATOR)
    assert code == 0
    assert json.loads(out) == _plain(expected)
    assert expected.summary.improved == 1


def test_compare_table_names_each_record_and_summarizes(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_a, run_b = _two_runs(capsys, tmp_path, records_file)
    _, out, _ = _cli(capsys, "compare", run_a, run_b, "--evaluator", EVALUATOR, "--workspace", tmp_path)
    expected = compare(load_run(tmp_path, run_a), load_run(tmp_path, run_b), EVALUATOR)

    for delta in expected.records:
        (row,) = [line for line in out.splitlines() if line.startswith(delta.record_id[:12])]
        assert delta.classification in row
        assert "fp-test" in row
    assert "improved=1 regressed=0 unchanged=1" in out
    assert "mean_score_delta=+0.2000" in out


def test_comparing_a_run_to_itself_is_all_unchanged(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_a, _ = _two_runs(capsys, tmp_path, records_file)
    code, out, _ = _cli(
        capsys, "compare", run_a, run_a, "--evaluator", EVALUATOR, "--workspace", tmp_path, "--json"
    )
    assert code == 0
    summary = json.loads(out)["summary"]
    assert (summary["improved"], summary["regressed"], summary["unchanged"]) == (0, 0, 2)
    assert summary["mean_score_delta"] == 0.0


def test_compare_across_snapshots_fails_naming_the_mismatch(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_a, _ = _two_runs(capsys, tmp_path, records_file)
    assert _cli(capsys, "freeze", "smoke", "v2", "--workspace", tmp_path)[0] == 0
    run_v2 = _cli(
        capsys, "run", "smoke@v2", "--evaluator", EVALUATOR, "--workspace", tmp_path,
        evaluate_fn=FakeEvaluate(),
    )[1].strip()

    code, out, err = _cli(
        capsys, "compare", run_a, run_v2, "--evaluator", EVALUATOR, "--workspace", tmp_path
    )
    assert code == 1
    assert out == ""
    assert "different snapshots" in err and "smoke@v1" in err and "smoke@v2" in err


def test_compare_with_an_unknown_run_id_fails_naming_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _cli(
        capsys, "compare", "nope-a", "nope-b", "--evaluator", EVALUATOR, "--workspace", tmp_path
    )
    assert code == 1
    assert "'nope-a'" in err


# --workspace


def test_every_subcommand_writes_only_under_workspace(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    workspace = tmp_path / "elsewhere"

    run_a, run_b = _two_runs(capsys, workspace, records_file)
    assert _cli(capsys, "compare", run_a, run_b, "--evaluator", EVALUATOR, "--workspace", workspace)[0] == 0

    assert (workspace / "datasets" / "smoke" / "snapshots" / "v1.json").exists()
    assert (workspace / "runs" / f"{run_a}.json").exists()
    assert list(cwd.iterdir()) == []


def test_without_workspace_the_default_is_cwd_and_no_env_var_is_read(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("TNA_LAB_WORKSPACE", "TNA_LAB_HOME", "TNA_WORKSPACE"):
        monkeypatch.setenv(name, str(tmp_path / "from-env"))

    assert _cli(capsys, "ingest", records_file, "--dataset", "smoke")[0] == 0
    assert _cli(capsys, "freeze", "smoke", "v1")[0] == 0
    run_id = _cli(capsys, "run", "smoke@v1", "--evaluator", EVALUATOR, evaluate_fn=FakeEvaluate())[1]
    assert _cli(capsys, "compare", run_id.strip(), run_id.strip(), "--evaluator", EVALUATOR)[0] == 0

    assert (tmp_path / ".tna-lab" / "runs" / f"{run_id.strip()}.json").exists()
    assert not (tmp_path / "from-env").exists()


def test_freeze_via_the_library_and_the_cli_agree_on_content(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_ws, lib_ws = tmp_path / "cli", tmp_path / "lib"
    _prepared(capsys, cli_ws, records_file)
    ingest(lib_ws, "smoke", load_jsonl(records_file))
    lib = freeze(lib_ws, "smoke", "v1")
    cli = resolve(cli_ws, "smoke@v1")
    # snapshot_id and frozen_at are per freeze event by design (research R2).
    assert (cli.dataset, cli.tag, cli.record_ids) == (lib.dataset, lib.tag, lib.record_ids)


# T000 (spec 002): `tna-lab compare` shows token counts, closing v0.1.0's Article V gap.


@dataclass(frozen=True)
class FakeTokenResult:
    evaluator_id: str
    status: str
    score: float | None
    judge_fingerprint: str = "fp-test"
    tokens_in: int | None = 1200
    tokens_out: int | None = 340


def _token_evaluate(evaluator_id: str, record: Any, judge: Any, cache_dir: Path) -> Any:
    return FakeTokenResult(evaluator_id, "ok", 0.5)


def test_compare_table_shows_both_sides_token_counts(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepared(capsys, tmp_path, records_file)
    args = ("run", "smoke@v1", "--evaluator", EVALUATOR, "--workspace", tmp_path)
    run_a = _cli(capsys, *args, evaluate_fn=_token_evaluate)[1].strip()
    run_b = _cli(capsys, *args, evaluate_fn=FakeEvaluate())[1].strip()  # no token counts

    _, out, _ = _cli(capsys, "compare", run_a, run_b, "--evaluator", EVALUATOR, "--workspace", tmp_path)
    header, *rows = out.splitlines()
    assert "tokens a → b" in header
    record_rows = [r for r in rows if not r.startswith("summary:")]
    assert record_rows and all("1200/340 → -" in r for r in record_rows)


def test_compare_json_carries_token_counts(
    tmp_path: Path, records_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepared(capsys, tmp_path, records_file)
    args = ("run", "smoke@v1", "--evaluator", EVALUATOR, "--workspace", tmp_path)
    run_a = _cli(capsys, *args, evaluate_fn=_token_evaluate)[1].strip()
    run_b = _cli(capsys, *args, evaluate_fn=_token_evaluate)[1].strip()

    _, out, _ = _cli(
        capsys, "compare", run_a, run_b, "--evaluator", EVALUATOR, "--workspace", tmp_path, "--json"
    )
    for record in json.loads(out)["records"]:
        assert (record["tokens_in_a"], record["tokens_out_a"]) == (1200, 340)
        assert (record["tokens_in_b"], record["tokens_out_b"]) == (1200, 340)
