"""Constitution Article I, by import graph (T030): no module under tna_lab/ imports ragas
or deepeval — tna-lab reaches a scorer only through trust-no-agent's evaluate().

This passes by construction today; it exists so a future change that violates Article I
fails CI rather than depending on code review. The checker is itself tested against
known-bad source below, so a guard that silently matches nothing cannot pass.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "tna_lab"
FRAMEWORKS = ("ragas", "deepeval")
_DYNAMIC_IMPORTERS = {"import_module", "__import__"}


def _is_framework(module: str) -> bool:
    return module.split(".")[0] in FRAMEWORKS


def framework_imports(source: str) -> list[str]:
    """Every ragas/deepeval module `source` imports: `import x`, `from x import y`, and
    `importlib.import_module("x")`/`__import__("x")` with a literal name."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names if _is_framework(alias.name)]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if _is_framework(node.module):
                found.append(node.module)
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            first = node.args[0]
            if (
                name in _DYNAMIC_IMPORTERS
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and _is_framework(first.value)
            ):
                found.append(first.value)
    return found


def _package_modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def test_the_walk_covers_the_whole_package() -> None:
    names = {path.name for path in _package_modules()}
    assert {"__init__.py", "runs.py", "compare.py", "cli.py"} <= names


def test_no_tna_lab_module_imports_ragas_or_deepeval() -> None:
    offenders = {
        str(path.relative_to(PACKAGE.parent)): found
        for path in _package_modules()
        if (found := framework_imports(path.read_text()))
    }
    assert offenders == {}


@pytest.mark.parametrize(
    "source",
    [
        "import ragas",
        "import deepeval.metrics",
        "import os, ragas.metrics as m",
        "from ragas import evaluate",
        "from deepeval.metrics import GEval",
        "def f():\n    from ragas.llms import llm_factory",
        "import importlib\nimportlib.import_module('deepeval')",
        "__import__('ragas.metrics')",
    ],
)
def test_the_checker_catches_every_import_form(source: str) -> None:
    assert framework_imports(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "import trustnoagent",
        "from trustnoagent.evaluators import evaluate",
        "import ragasx",  # a different top-level package that merely shares a prefix
        "from . import ragas",  # a relative import is first-party, not the framework
        "x = 'ragas'",
    ],
)
def test_the_checker_ignores_what_is_not_a_framework_import(source: str) -> None:
    assert framework_imports(source) == []
