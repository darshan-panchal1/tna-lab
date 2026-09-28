"""Constitution Article III ("nothing leaves without being told to") applies to
tna-lab's dependency tree too: ragas and deepeval, pulled in transitively through
trust-no-agent's evaluate(), phone home on import unless opted out.

Run in a subprocess: `tna_lab` is very likely already imported by the time this test
module runs (other test files import it first in the same pytest session), and
os.environ.setdefault only has an effect on the first import per interpreter.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _env_after_import(evaluate_fn: str) -> str:
    return subprocess.run(
        [sys.executable, "-c", f"import tna_lab, os; print(os.environ.get({evaluate_fn!r}, ''))"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_importing_tna_lab_opts_deepeval_out_of_telemetry() -> None:
    assert _env_after_import("DEEPEVAL_TELEMETRY_OPT_OUT") == "YES"


def test_importing_tna_lab_opts_ragas_out_of_telemetry() -> None:
    assert _env_after_import("RAGAS_DO_NOT_TRACK") == "true"


def test_importing_tna_lab_never_overrides_a_caller_s_own_choice() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import tna_lab, os; print(os.environ['DEEPEVAL_TELEMETRY_OPT_OUT'])"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "DEEPEVAL_TELEMETRY_OPT_OUT": "NO"},
    )
    assert result.stdout.strip() == "NO"
